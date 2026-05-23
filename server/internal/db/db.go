// Package db owns the Postgres connection pool.
//
// Wraps jackc/pgx/v5/pgxpool with our preferred defaults. Other packages take
// a *pgxpool.Pool by value and do their own queries / transactions on top.
package db

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

// Connect opens a pool against the given URL, pings to confirm reachability,
// and returns it. Callers are responsible for closing the pool at shutdown.
func Connect(ctx context.Context, url string) (*pgxpool.Pool, error) {
	cfg, err := pgxpool.ParseConfig(url)
	if err != nil {
		return nil, fmt.Errorf("parse db config: %w", err)
	}

	// Sized for the $6 DigitalOcean box (1 vCPU). Idle conns kept low; bursts
	// up to MaxConns. Adjust if we see pool-exhaustion errors under load.
	cfg.MaxConns = 10
	cfg.MinConns = 1
	cfg.MaxConnLifetime = time.Hour
	cfg.MaxConnIdleTime = 30 * time.Minute

	pool, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		return nil, fmt.Errorf("create pool: %w", err)
	}

	pingCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	if err := pool.Ping(pingCtx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("ping db: %w", err)
	}
	return pool, nil
}
