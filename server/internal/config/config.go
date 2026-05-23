// Package config loads runtime configuration from environment variables.
//
// All config lives in env vars (12-factor). For local dev, populate .env (see
// .env.example) and source it before running. Production reads from systemd
// environment, docker-compose, or the host shell.
package config

import (
	"errors"
	"fmt"
	"log/slog"
	"os"
	"strings"
)

type Config struct {
	Addr        string // ":8080"
	DatabaseURL string // "postgres://user:pass@host:port/db?sslmode=disable"
	JWTSecret   []byte // HMAC-SHA256 signing key; >= 32 bytes
	LogLevel    slog.Level
}

// Load reads the environment and returns a validated Config. Returns an error
// describing every problem found (not just the first) so a single boot dump
// shows all the work needed.
func Load() (*Config, error) {
	cfg := &Config{
		Addr:        envOr("ADDR", ":8080"),
		DatabaseURL: os.Getenv("DATABASE_URL"),
		JWTSecret:   []byte(os.Getenv("JWT_SECRET")),
		LogLevel:    parseLogLevel(envOr("LOG_LEVEL", "info")),
	}

	var problems []string
	if cfg.DatabaseURL == "" {
		problems = append(problems, "DATABASE_URL is required")
	}
	if len(cfg.JWTSecret) < 32 {
		problems = append(problems, fmt.Sprintf("JWT_SECRET must be >= 32 bytes (got %d)", len(cfg.JWTSecret)))
	}
	if len(problems) > 0 {
		return nil, errors.New("config invalid: " + strings.Join(problems, "; "))
	}
	return cfg, nil
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func parseLogLevel(s string) slog.Level {
	switch strings.ToLower(s) {
	case "debug":
		return slog.LevelDebug
	case "warn", "warning":
		return slog.LevelWarn
	case "error":
		return slog.LevelError
	default:
		return slog.LevelInfo
	}
}
