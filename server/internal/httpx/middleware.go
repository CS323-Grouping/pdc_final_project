// Package httpx provides HTTP middleware and helpers shared across handlers.
//
// Conventions:
//   - Every request gets an X-Request-Id (echo incoming or generate one).
//   - Every request is access-logged with method, path, status, duration, request_id.
//   - Panics are recovered, logged with stack, and surface as 500.
//   - Chain middleware via Chain(handler, mw1, mw2, ...). mw1 wraps outermost.
package httpx

import (
	"bufio"
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"runtime/debug"
	"time"
)

type ctxKey string

const requestIDKey ctxKey = "request_id"

// Middleware is the standard "wrap a handler" signature.
type Middleware func(http.Handler) http.Handler

// Chain wraps h with the given middlewares. The first middleware in the list
// becomes the outermost wrapper (runs first on the way in, last on the way out).
func Chain(h http.Handler, m ...Middleware) http.Handler {
	for i := len(m) - 1; i >= 0; i-- {
		h = m[i](h)
	}
	return h
}

// RequestID assigns or echoes an X-Request-Id and stashes it in the request context.
func RequestID(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id := r.Header.Get("X-Request-Id")
		if id == "" {
			var b [12]byte
			_, _ = rand.Read(b[:])
			id = hex.EncodeToString(b[:])
		}
		ctx := context.WithValue(r.Context(), requestIDKey, id)
		w.Header().Set("X-Request-Id", id)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

// RequestIDFrom pulls the request id out of a context (empty if missing).
func RequestIDFrom(ctx context.Context) string {
	v, _ := ctx.Value(requestIDKey).(string)
	return v
}

// AccessLog logs one slog.Info line per request after it completes.
func AccessLog(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		sw := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(sw, r)
		slog.Info("http",
			"method", r.Method,
			"path", r.URL.Path,
			"status", sw.status,
			"dur_ms", time.Since(start).Milliseconds(),
			"request_id", RequestIDFrom(r.Context()),
			"remote", r.RemoteAddr,
		)
	})
}

// Recover converts panics into 500s with a logged stack trace.
func Recover(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer func() {
			if rec := recover(); rec != nil {
				slog.Error("panic recovered",
					"panic", rec,
					"stack", string(debug.Stack()),
					"request_id", RequestIDFrom(r.Context()),
					"path", r.URL.Path,
				)
				http.Error(w, "internal server error", http.StatusInternalServerError)
			}
		}()
		next.ServeHTTP(w, r)
	})
}

// statusRecorder wraps a ResponseWriter so AccessLog can read the status code.
type statusRecorder struct {
	http.ResponseWriter
	status int
	wrote  bool
}

func (sw *statusRecorder) WriteHeader(code int) {
	if sw.wrote {
		return
	}
	sw.wrote = true
	sw.status = code
	sw.ResponseWriter.WriteHeader(code)
}

func (sw *statusRecorder) Hijack() (net.Conn, *bufio.ReadWriter, error) {
	hijacker, ok := sw.ResponseWriter.(http.Hijacker)
	if !ok {
		return nil, nil, fmt.Errorf("response writer %T does not implement http.Hijacker", sw.ResponseWriter)
	}
	sw.status = http.StatusSwitchingProtocols
	return hijacker.Hijack()
}

func (sw *statusRecorder) Unwrap() http.ResponseWriter {
	return sw.ResponseWriter
}
