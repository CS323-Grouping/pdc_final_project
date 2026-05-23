package auth

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

// Token lifetimes (matches vault: Networking - Transport & Auth.md).
const (
	AccessTokenTTL  = 15 * time.Minute
	RefreshTokenTTL = 30 * 24 * time.Hour
	issuer          = "cssocialgame"
)

// Claims is what we put in the JWT body. The standard registered claims
// (iss, sub, iat, exp) come from RegisteredClaims; we add display_name so
// servers can log it without a DB lookup.
type Claims struct {
	UserID      string `json:"sub"`
	DisplayName string `json:"name"`
	jwt.RegisteredClaims
}

// MintAccessToken signs a short-lived (15 min) HS256 JWT for the user.
func MintAccessToken(secret []byte, userID, displayName string) (string, time.Time, error) {
	expiry := time.Now().Add(AccessTokenTTL)
	claims := Claims{
		UserID:      userID,
		DisplayName: displayName,
		RegisteredClaims: jwt.RegisteredClaims{
			Issuer:    issuer,
			Subject:   userID,
			IssuedAt:  jwt.NewNumericDate(time.Now()),
			ExpiresAt: jwt.NewNumericDate(expiry),
		},
	}
	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	signed, err := tok.SignedString(secret)
	if err != nil {
		return "", time.Time{}, fmt.Errorf("sign access token: %w", err)
	}
	return signed, expiry, nil
}

// VerifyAccessToken parses, validates signature + exp + iss, and returns the
// claims. Returns ErrTokenExpired specifically when exp has passed so the
// client can distinguish "refresh me" from "your token is forged."
func VerifyAccessToken(secret []byte, tokenStr string) (*Claims, error) {
	parsed, err := jwt.ParseWithClaims(
		tokenStr,
		&Claims{},
		func(t *jwt.Token) (interface{}, error) {
			if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
				return nil, fmt.Errorf("unexpected signing method: %v", t.Header["alg"])
			}
			return secret, nil
		},
		jwt.WithIssuer(issuer),
		jwt.WithValidMethods([]string{"HS256"}),
	)
	if err != nil {
		if errors.Is(err, jwt.ErrTokenExpired) {
			return nil, ErrTokenExpired
		}
		return nil, fmt.Errorf("verify access token: %w", err)
	}
	claims, ok := parsed.Claims.(*Claims)
	if !ok || !parsed.Valid {
		return nil, errors.New("invalid token")
	}
	return claims, nil
}

// GenerateRefreshToken returns a 256-bit random token (base64url, 43 chars)
// and its sha256 hex hash. Send the plaintext to the client; store ONLY the
// hash in DB. The plaintext is never persisted server-side — losing the DB
// doesn't leak active sessions.
func GenerateRefreshToken() (plaintext, hashHex string, err error) {
	var b [32]byte
	if _, err := rand.Read(b[:]); err != nil {
		return "", "", fmt.Errorf("read random: %w", err)
	}
	plaintext = base64.RawURLEncoding.EncodeToString(b[:])
	hashHex = HashRefreshToken(plaintext)
	return plaintext, hashHex, nil
}

// HashRefreshToken returns the canonical DB-storage form of a refresh token
// (sha256, hex). Used on /auth/refresh to look up by hash of incoming token.
func HashRefreshToken(plaintext string) string {
	sum := sha256.Sum256([]byte(plaintext))
	return hex.EncodeToString(sum[:])
}
