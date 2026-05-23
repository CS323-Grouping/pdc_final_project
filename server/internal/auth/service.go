package auth

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"fmt"
	"log/slog"
	"regexp"
	"strings"
	"time"

	"github.com/oklog/ulid/v2"
)

// Input validation rules. Tighten/loosen here; handlers don't duplicate.
const (
	PasswordMinLen       = 8
	PasswordMaxLen       = 128
	DisplayNameMinLen    = 2
	DisplayNameMaxLen    = 32
	VerificationTokenTTL = 24 * time.Hour
)

var (
	// Permissive email regex — RFC 5321 is unenforceable in regex anyway.
	// We accept anything with `local@domain.tld` shape; the real validation
	// is "did they confirm via the verification email."
	emailRe       = regexp.MustCompile(`^[^@\s]+@[^@\s]+\.[^@\s]+$`)
	displayNameRe = regexp.MustCompile(`^[A-Za-z0-9_-]+$`)
)

// Service owns the auth business logic. Pure orchestration — all SQL is in
// Store, all crypto in password.go / jwt.go.
type Service struct {
	store     *Store
	jwtSecret []byte
}

func NewService(store *Store, jwtSecret []byte) *Service {
	return &Service{store: store, jwtSecret: jwtSecret}
}

// LoginResult is what Login and Refresh return — a fresh token pair plus the
// user record (handlers shape it for the wire).
type LoginResult struct {
	AccessToken      string
	AccessExpiresAt  time.Time
	RefreshToken     string
	RefreshExpiresAt time.Time
	User             *User
}

// Register validates input, checks uniqueness, hashes password, creates the
// user with a verification token, and (currently) logs the verification URL
// to stdout instead of emailing it. Returns the new user id.
func (s *Service) Register(ctx context.Context, email, password, displayName string) (string, error) {
	email = strings.TrimSpace(strings.ToLower(email))
	displayName = strings.TrimSpace(displayName)

	var details []ValidationDetail
	if !emailRe.MatchString(email) {
		details = append(details, ValidationDetail{Field: "email", Reason: "must be a valid email address"})
	}
	if len(password) < PasswordMinLen || len(password) > PasswordMaxLen {
		details = append(details, ValidationDetail{
			Field:  "password",
			Reason: fmt.Sprintf("must be %d-%d characters", PasswordMinLen, PasswordMaxLen),
		})
	}
	if len(displayName) < DisplayNameMinLen || len(displayName) > DisplayNameMaxLen {
		details = append(details, ValidationDetail{
			Field:  "display_name",
			Reason: fmt.Sprintf("must be %d-%d characters", DisplayNameMinLen, DisplayNameMaxLen),
		})
	} else if !displayNameRe.MatchString(displayName) {
		details = append(details, ValidationDetail{
			Field:  "display_name",
			Reason: "must contain only letters, numbers, underscore, or hyphen",
		})
	}
	if len(details) > 0 {
		return "", validationErr(details...)
	}

	if existing, err := s.store.GetUserByEmail(ctx, email); err != nil {
		return "", fmt.Errorf("check email: %w", err)
	} else if existing != nil {
		return "", ErrEmailTaken
	}

	if exists, err := s.store.DisplayNameExists(ctx, displayName); err != nil {
		return "", fmt.Errorf("check display name: %w", err)
	} else if exists {
		return "", ErrDisplayNameTaken
	}

	hash, err := HashPassword(password)
	if err != nil {
		return "", fmt.Errorf("hash password: %w", err)
	}
	verifyToken, err := generateVerificationToken()
	if err != nil {
		return "", fmt.Errorf("gen verify token: %w", err)
	}
	expiry := time.Now().Add(VerificationTokenTTL)

	user := &User{
		ID:                         newULID(),
		Email:                      email,
		DisplayName:                displayName,
		PasswordHash:               hash,
		VerificationToken:          &verifyToken,
		VerificationTokenExpiresAt: &expiry,
	}
	if err := s.store.CreateUser(ctx, user); err != nil {
		return "", fmt.Errorf("create user: %w", err)
	}

	// Stub email delivery — Phase 1 ships no SMTP yet. Log the token so
	// dev can copy it and POST /auth/verify manually. Real Gmail SMTP
	// later; tracked in [[Roadmap]] Phase 8.
	slog.Info("verification token issued (stub email delivery)",
		"user_id", user.ID,
		"email", user.Email,
		"verify_token", verifyToken,
		"expires_at", expiry.Format(time.RFC3339),
		"hint", `POST /auth/verify {"token":"<above>"}`,
	)
	return user.ID, nil
}

// Login validates credentials and issues a new token pair.
func (s *Service) Login(ctx context.Context, email, password string) (*LoginResult, error) {
	email = strings.TrimSpace(strings.ToLower(email))
	user, err := s.store.GetUserByEmail(ctx, email)
	if err != nil {
		return nil, fmt.Errorf("get user: %w", err)
	}
	// Same error for both "no such user" and "bad password" — no
	// account-enumeration leak. Burn a dummy bcrypt comparison for missing
	// users so timing stays close to the bad-password path.
	if user == nil {
		BurnPasswordCheck(password)
		return nil, ErrInvalidCredentials
	}
	if !VerifyPassword(user.PasswordHash, password) {
		return nil, ErrInvalidCredentials
	}
	return s.issueTokens(ctx, user)
}

// Refresh validates the refresh token, rotates it (revoke + insert new), and
// returns a fresh pair.
func (s *Service) Refresh(ctx context.Context, refreshToken string) (*LoginResult, error) {
	hash := HashRefreshToken(refreshToken)
	rt, err := s.store.FindRefreshTokenByHash(ctx, hash)
	if err != nil {
		return nil, fmt.Errorf("find refresh: %w", err)
	}
	if rt == nil || rt.RevokedAt != nil || time.Now().After(rt.ExpiresAt) {
		return nil, ErrRefreshInvalid
	}
	user, err := s.store.GetUserByID(ctx, rt.UserID)
	if err != nil {
		return nil, fmt.Errorf("get user: %w", err)
	}
	if user == nil {
		// User deleted — treat as invalid refresh.
		return nil, ErrRefreshInvalid
	}

	access, accessExp, err := MintAccessToken(s.jwtSecret, user.ID, user.DisplayName)
	if err != nil {
		return nil, fmt.Errorf("mint access: %w", err)
	}
	newPlaintext, newHash, err := GenerateRefreshToken()
	if err != nil {
		return nil, fmt.Errorf("gen refresh: %w", err)
	}
	newRt := &RefreshToken{
		ID:        newULID(),
		UserID:    user.ID,
		TokenHash: newHash,
		ExpiresAt: time.Now().Add(RefreshTokenTTL),
	}
	if err := s.store.RotateRefreshToken(ctx, hash, newRt); err != nil {
		return nil, fmt.Errorf("rotate: %w", err)
	}
	return &LoginResult{
		AccessToken:      access,
		AccessExpiresAt:  accessExp,
		RefreshToken:     newPlaintext,
		RefreshExpiresAt: newRt.ExpiresAt,
		User:             user,
	}, nil
}

// Logout revokes the refresh token. Idempotent — never returns an error to
// the caller about "no such token"; that would leak whether a token exists.
func (s *Service) Logout(ctx context.Context, refreshToken string) error {
	if refreshToken == "" {
		return nil
	}
	return s.store.RevokeRefreshToken(ctx, HashRefreshToken(refreshToken))
}

// Verify accepts a verification token, marks the user verified if found
// and unexpired, clears the token. Returns ErrVerificationBad otherwise.
func (s *Service) Verify(ctx context.Context, token string) error {
	if token == "" {
		return ErrVerificationBad
	}
	ok, err := s.store.MarkVerified(ctx, token)
	if err != nil {
		return fmt.Errorf("mark verified: %w", err)
	}
	if !ok {
		return ErrVerificationBad
	}
	return nil
}

// Me returns the user record for a given user_id (typically the sub from a
// validated JWT). Returns ErrNotAuthenticated if the user has been deleted.
func (s *Service) Me(ctx context.Context, userID string) (*User, error) {
	user, err := s.store.GetUserByID(ctx, userID)
	if err != nil {
		return nil, fmt.Errorf("get user: %w", err)
	}
	if user == nil {
		return nil, ErrNotAuthenticated
	}
	return user, nil
}

// issueTokens mints + persists a fresh access/refresh pair for the user.
func (s *Service) issueTokens(ctx context.Context, user *User) (*LoginResult, error) {
	access, accessExp, err := MintAccessToken(s.jwtSecret, user.ID, user.DisplayName)
	if err != nil {
		return nil, fmt.Errorf("mint access: %w", err)
	}
	plaintext, hash, err := GenerateRefreshToken()
	if err != nil {
		return nil, fmt.Errorf("gen refresh: %w", err)
	}
	rt := &RefreshToken{
		ID:        newULID(),
		UserID:    user.ID,
		TokenHash: hash,
		ExpiresAt: time.Now().Add(RefreshTokenTTL),
	}
	if err := s.store.CreateRefreshToken(ctx, rt); err != nil {
		return nil, fmt.Errorf("create refresh: %w", err)
	}
	return &LoginResult{
		AccessToken:      access,
		AccessExpiresAt:  accessExp,
		RefreshToken:     plaintext,
		RefreshExpiresAt: rt.ExpiresAt,
		User:             user,
	}, nil
}

func newULID() string {
	return ulid.Make().String()
}

func generateVerificationToken() (string, error) {
	var b [24]byte
	if _, err := rand.Read(b[:]); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(b[:]), nil
}
