package auth

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// Store is the persistence layer for auth. All SQL lives here; service.go
// only talks to this. Swap to sqlc when query count balloons.
type Store struct {
	pool *pgxpool.Pool
}

func NewStore(pool *pgxpool.Pool) *Store {
	return &Store{pool: pool}
}

// User mirrors the users table row-for-row (Verification* nullable).
type User struct {
	ID                         string
	Email                      string
	DisplayName                string
	PasswordHash               string
	Verified                   bool
	VerificationToken          *string
	VerificationTokenExpiresAt *time.Time
	CreatedAt                  time.Time
	UpdatedAt                  time.Time
}

// RefreshToken mirrors refresh_tokens. TokenHash is sha256-hex; never the plaintext.
type RefreshToken struct {
	ID        string
	UserID    string
	TokenHash string
	CreatedAt time.Time
	ExpiresAt time.Time
	RevokedAt *time.Time
}

// CreateUser inserts. Caller must validate uniqueness first; a DB unique
// violation here surfaces as a generic pgx error (we don't translate it).
func (s *Store) CreateUser(ctx context.Context, u *User) error {
	const q = `
		INSERT INTO users (id, email, display_name, password_hash, verification_token, verification_token_expires_at)
		VALUES ($1, $2, $3, $4, $5, $6)
	`
	_, err := s.pool.Exec(ctx, q,
		u.ID, u.Email, u.DisplayName, u.PasswordHash, u.VerificationToken, u.VerificationTokenExpiresAt,
	)
	return err
}

// GetUserByEmail returns (nil, nil) when no row matches — callers must
// check for nil. Email comparison is case-insensitive.
func (s *Store) GetUserByEmail(ctx context.Context, email string) (*User, error) {
	const q = `
		SELECT id, email, display_name, password_hash, verified,
		       verification_token, verification_token_expires_at,
		       created_at, updated_at
		FROM users
		WHERE lower(email) = lower($1)
	`
	u := &User{}
	err := s.pool.QueryRow(ctx, q, email).Scan(
		&u.ID, &u.Email, &u.DisplayName, &u.PasswordHash, &u.Verified,
		&u.VerificationToken, &u.VerificationTokenExpiresAt,
		&u.CreatedAt, &u.UpdatedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	return u, err
}

// GetUserByID returns (nil, nil) when no row matches.
func (s *Store) GetUserByID(ctx context.Context, id string) (*User, error) {
	const q = `
		SELECT id, email, display_name, password_hash, verified,
		       verification_token, verification_token_expires_at,
		       created_at, updated_at
		FROM users
		WHERE id = $1
	`
	u := &User{}
	err := s.pool.QueryRow(ctx, q, id).Scan(
		&u.ID, &u.Email, &u.DisplayName, &u.PasswordHash, &u.Verified,
		&u.VerificationToken, &u.VerificationTokenExpiresAt,
		&u.CreatedAt, &u.UpdatedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	return u, err
}

// DisplayNameExists is a cheap uniqueness probe used during /auth/register.
// Case-insensitive.
func (s *Store) DisplayNameExists(ctx context.Context, name string) (bool, error) {
	const q = `SELECT 1 FROM users WHERE lower(display_name) = lower($1)`
	var x int
	err := s.pool.QueryRow(ctx, q, name).Scan(&x)
	if errors.Is(err, pgx.ErrNoRows) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return true, nil
}

// MarkVerified clears the verification token on a successful verify. Returns
// (true, nil) if a row was matched and updated; (false, nil) if token was
// missing or expired.
func (s *Store) MarkVerified(ctx context.Context, token string) (bool, error) {
	const q = `
		UPDATE users
		SET verified = true,
		    verification_token = NULL,
		    verification_token_expires_at = NULL
		WHERE verification_token = $1
		  AND verification_token_expires_at > now()
		RETURNING id
	`
	var id string
	err := s.pool.QueryRow(ctx, q, token).Scan(&id)
	if errors.Is(err, pgx.ErrNoRows) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return true, nil
}

// CreateRefreshToken inserts a new refresh token row.
func (s *Store) CreateRefreshToken(ctx context.Context, rt *RefreshToken) error {
	const q = `
		INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at)
		VALUES ($1, $2, $3, $4)
	`
	_, err := s.pool.Exec(ctx, q, rt.ID, rt.UserID, rt.TokenHash, rt.ExpiresAt)
	return err
}

// FindRefreshTokenByHash returns (nil, nil) when no row matches.
func (s *Store) FindRefreshTokenByHash(ctx context.Context, hash string) (*RefreshToken, error) {
	const q = `
		SELECT id, user_id, token_hash, created_at, expires_at, revoked_at
		FROM refresh_tokens
		WHERE token_hash = $1
	`
	rt := &RefreshToken{}
	err := s.pool.QueryRow(ctx, q, hash).Scan(
		&rt.ID, &rt.UserID, &rt.TokenHash, &rt.CreatedAt, &rt.ExpiresAt, &rt.RevokedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	return rt, err
}

// RevokeRefreshToken marks a token revoked. Idempotent — re-revoking a
// revoked token is a no-op.
func (s *Store) RevokeRefreshToken(ctx context.Context, hash string) error {
	const q = `
		UPDATE refresh_tokens
		SET revoked_at = now()
		WHERE token_hash = $1 AND revoked_at IS NULL
	`
	_, err := s.pool.Exec(ctx, q, hash)
	return err
}

// RotateRefreshToken atomically revokes the old token and inserts the new one.
// Refresh tokens are one-shot — using a refresh issues a new pair AND
// invalidates the old refresh. If an attacker steals a refresh token and uses
// it, the legitimate user's next refresh fails (already revoked), which is
// the standard detection signal for token theft.
func (s *Store) RotateRefreshToken(ctx context.Context, oldHash string, newToken *RefreshToken) error {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("begin tx: %w", err)
	}
	defer tx.Rollback(ctx)

	tag, err := tx.Exec(ctx, `
		UPDATE refresh_tokens SET revoked_at = now()
		WHERE token_hash = $1 AND revoked_at IS NULL
	`, oldHash)
	if err != nil {
		return fmt.Errorf("revoke old: %w", err)
	}
	if tag.RowsAffected() != 1 {
		return ErrRefreshInvalid
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at)
		VALUES ($1, $2, $3, $4)
	`, newToken.ID, newToken.UserID, newToken.TokenHash, newToken.ExpiresAt); err != nil {
		return fmt.Errorf("insert new: %w", err)
	}
	return tx.Commit(ctx)
}
