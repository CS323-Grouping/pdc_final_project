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
	"net/netip"
	"os"
	"strings"
)

type Config struct {
	Addr              string // ":8080"
	DatabaseURL       string // "postgres://user:pass@host:port/db?sslmode=disable"
	JWTSecret         []byte // HMAC-SHA256 signing key; >= 32 bytes
	LogLevel          slog.Level
	WSOriginPatterns  []string
	TrustedProxyCIDRs []netip.Prefix
}

// Load reads the environment and returns a validated Config. Returns an error
// describing every problem found (not just the first) so a single boot dump
// shows all the work needed.
func Load() (*Config, error) {
	cfg := &Config{
		Addr:             envOr("ADDR", ":8080"),
		DatabaseURL:      os.Getenv("DATABASE_URL"),
		JWTSecret:        []byte(os.Getenv("JWT_SECRET")),
		LogLevel:         parseLogLevel(envOr("LOG_LEVEL", "info")),
		WSOriginPatterns: splitCSV(os.Getenv("WS_ALLOWED_ORIGINS")),
	}
	var proxyProblems []string
	cfg.TrustedProxyCIDRs, proxyProblems = parseCIDRList(os.Getenv("TRUSTED_PROXY_CIDRS"))

	var problems []string
	if cfg.DatabaseURL == "" {
		problems = append(problems, "DATABASE_URL is required")
	}
	if len(cfg.JWTSecret) < 32 {
		problems = append(problems, fmt.Sprintf("JWT_SECRET must be >= 32 bytes (got %d)", len(cfg.JWTSecret)))
	}
	problems = append(problems, proxyProblems...)
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

func splitCSV(s string) []string {
	parts := strings.Split(s, ",")
	out := make([]string, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part != "" {
			out = append(out, part)
		}
	}
	return out
}

func parseCIDRList(s string) ([]netip.Prefix, []string) {
	parts := splitCSV(s)
	out := make([]netip.Prefix, 0, len(parts))
	var problems []string
	for _, part := range parts {
		prefix, err := netip.ParsePrefix(part)
		if err != nil {
			problems = append(problems, fmt.Sprintf("TRUSTED_PROXY_CIDRS contains invalid CIDR %q", part))
			continue
		}
		out = append(out, prefix)
	}
	return out, problems
}
