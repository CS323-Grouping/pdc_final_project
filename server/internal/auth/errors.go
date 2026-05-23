package auth

import (
	"errors"
	"net/http"
)

// Error is the canonical auth error type — every failure mode the service
// surfaces is one of these. Handlers turn it into a JSON response with the
// matching HTTP status. Internal errors (db down, etc.) are NOT this type;
// they bubble up as plain errors and become 500s.
type Error struct {
	Code    string // stable machine identifier; clients pattern-match on this
	Message string // human-readable
	Status  int    // HTTP status to send
	Details any    // optional; e.g. per-field validation reasons
}

func (e *Error) Error() string { return e.Code + ": " + e.Message }

// Sentinel errors. Use these via errors.Is / errors.As (or just return
// directly).
var (
	ErrEmailTaken         = &Error{Code: "email_taken", Message: "email already registered", Status: http.StatusConflict}
	ErrDisplayNameTaken   = &Error{Code: "display_name_taken", Message: "display name already taken", Status: http.StatusConflict}
	ErrInvalidCredentials = &Error{Code: "invalid_credentials", Message: "invalid email or password", Status: http.StatusUnauthorized}
	ErrTokenExpired       = &Error{Code: "token_expired", Message: "access token expired", Status: http.StatusUnauthorized}
	ErrNotAuthenticated   = &Error{Code: "not_authenticated", Message: "missing or invalid bearer token", Status: http.StatusUnauthorized}
	ErrRefreshInvalid     = &Error{Code: "refresh_invalid", Message: "refresh token invalid, expired, or revoked", Status: http.StatusUnauthorized}
	ErrVerificationBad    = &Error{Code: "verification_invalid", Message: "verification token invalid or expired", Status: http.StatusGone}
	ErrRateLimited        = &Error{Code: "rate_limited", Message: "too many requests", Status: http.StatusTooManyRequests}
)

// ValidationDetail describes one field-level validation failure. Multiple are
// returned together so a client can show all errors at once instead of
// fix-one-resubmit-fix-next.
type ValidationDetail struct {
	Field  string `json:"field"`
	Reason string `json:"reason"`
}

// validationErr builds a *Error with code=validation_failed and the per-field
// detail payload. Status is 400.
func validationErr(details ...ValidationDetail) *Error {
	return &Error{
		Code:    "validation_failed",
		Message: "input validation failed",
		Status:  http.StatusBadRequest,
		Details: details,
	}
}

// asAuthError unwraps an *Error from an error chain, or returns nil if there
// isn't one. Handlers use this to decide between writeError(authErr) (typed
// response) and writeError(unknown) (500).
func asAuthError(err error) *Error {
	var e *Error
	if errors.As(err, &e) {
		return e
	}
	return nil
}
