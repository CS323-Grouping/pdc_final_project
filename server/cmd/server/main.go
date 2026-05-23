// Command server is the CSSocialGame backend.
//
// Phase 1.1: GET /health.
// Phase 1.2 (this turn): POST /auth/{register,verify,login,refresh,logout}, GET /me.
// Phase 1.3: WebSocket at /ws?token=<jwt> with hello round-trip.
package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/joho/godotenv"
	"golang.org/x/time/rate"

	"github.com/CS-StudentGroup/pdc_final_project/server/internal/auth"
	"github.com/CS-StudentGroup/pdc_final_project/server/internal/config"
	"github.com/CS-StudentGroup/pdc_final_project/server/internal/db"
	"github.com/CS-StudentGroup/pdc_final_project/server/internal/httpx"
	"github.com/CS-StudentGroup/pdc_final_project/server/internal/ws"
)

const serverVersion = "0.1.0-phase1.3"

func main() {
	if err := run(); err != nil {
		slog.Error("fatal", "err", err)
		os.Exit(1)
	}
}

func run() error {
	// Auto-load .env for local dev. Missing file is fine — production reads
	// from real OS env (systemd / docker / shell). Real env vars always win
	// over .env entries (godotenv default).
	if err := godotenv.Load(); err != nil && !errors.Is(err, os.ErrNotExist) {
		return fmt.Errorf(".env load: %w", err)
	}

	cfg, err := config.Load()
	if err != nil {
		return err
	}

	slog.SetDefault(slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{
		Level: cfg.LogLevel,
	})))

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	pool, err := db.Connect(ctx, cfg.DatabaseURL)
	if err != nil {
		return fmt.Errorf("db connect: %w", err)
	}
	defer pool.Close()
	slog.Info("db connected")

	// Wire auth.
	authStore := auth.NewStore(pool)
	authSvc := auth.NewService(authStore, cfg.JWTSecret)
	authHandlers := auth.NewHandlers(authSvc)
	bearer := auth.NewBearerMiddleware(cfg.JWTSecret)
	// 5 burst, then 1 every 12s = ~5 requests/minute sustained per IP. Applied
	// across all /auth/* endpoints as a single bucket per IP.
	authRL := auth.NewRateLimiter(rate.Every(12*time.Second), 5)

	mux := http.NewServeMux()

	// Public health probe.
	mux.HandleFunc("GET /health", healthHandler(pool))

	// Public auth endpoints under one rate limiter.
	authMux := http.NewServeMux()
	authHandlers.MountPublic(authMux)
	mux.Handle("/auth/", authRL.Wrap(authMux))

	// Authenticated endpoints.
	mux.Handle("GET /me", bearer.Wrap(authHandlers.Me()))

	// WebSocket control channel. JWT validated by the handler itself
	// (from ?token=...) since Godot's WebSocketPeer can't easily set
	// Authorization headers on connect. Bearer middleware isn't applied.
	wsHandler := ws.New(cfg.JWTSecret, serverVersion)
	mux.Handle("GET /ws", wsHandler)

	handler := httpx.Chain(mux, httpx.RequestID, httpx.AccessLog, httpx.Recover)

	srv := &http.Server{
		Addr:              cfg.Addr,
		Handler:           handler,
		ReadHeaderTimeout: 5 * time.Second,
	}

	serverErr := make(chan error, 1)
	go func() {
		slog.Info("server listening", "addr", cfg.Addr)
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			serverErr <- err
		}
		close(serverErr)
	}()

	select {
	case <-ctx.Done():
		slog.Info("shutdown signal received")
	case err := <-serverErr:
		return fmt.Errorf("http listen: %w", err)
	}

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := srv.Shutdown(shutdownCtx); err != nil {
		return fmt.Errorf("shutdown: %w", err)
	}
	slog.Info("shutdown clean")
	return nil
}

// healthHandler returns 200 "ok" when the database is reachable, 503 otherwise.
func healthHandler(pool *pgxpool.Pool) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		pingCtx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
		defer cancel()
		if err := pool.Ping(pingCtx); err != nil {
			slog.Warn("health: db ping failed", "err", err, "request_id", httpx.RequestIDFrom(r.Context()))
			http.Error(w, "db unreachable", http.StatusServiceUnavailable)
			return
		}
		fmt.Fprintln(w, "ok")
	}
}
