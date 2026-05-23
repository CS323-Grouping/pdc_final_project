package auth

import (
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"time"
)

// Handlers wires the auth service to net/http. JSON in, JSON out. All errors
// surface as {"error": {code, message, details?}}.
type Handlers struct {
	svc *Service
}

func NewHandlers(svc *Service) *Handlers {
	return &Handlers{svc: svc}
}

// MountPublic registers the unauthenticated /auth/* endpoints on the given mux.
// Caller is responsible for any wrapping middleware (rate limiting, CORS, etc.).
func (h *Handlers) MountPublic(mux *http.ServeMux) {
	mux.HandleFunc("POST /auth/register", h.register)
	mux.HandleFunc("POST /auth/verify", h.verify)
	mux.HandleFunc("POST /auth/login", h.login)
	mux.HandleFunc("POST /auth/refresh", h.refresh)
	mux.HandleFunc("POST /auth/logout", h.logout)
}

// Me returns the bare handler for GET /me. Caller wraps with BearerMiddleware
// before mounting.
func (h *Handlers) Me() http.HandlerFunc {
	return h.me
}

// ----------------- request / response types -----------------

type registerReq struct {
	Email       string `json:"email"`
	Password    string `json:"password"`
	DisplayName string `json:"display_name"`
}

type registerResp struct {
	UserID string `json:"user_id"`
}

type verifyReq struct {
	Token string `json:"token"`
}

type loginReq struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

type refreshReq struct {
	RefreshToken string `json:"refresh_token"`
}

type logoutReq struct {
	RefreshToken string `json:"refresh_token"`
}

type tokenResp struct {
	AccessToken      string    `json:"access_token"`
	AccessExpiresAt  time.Time `json:"access_expires_at"`
	RefreshToken     string    `json:"refresh_token"`
	RefreshExpiresAt time.Time `json:"refresh_expires_at"`
	User             userResp  `json:"user"`
}

type userResp struct {
	ID          string    `json:"id"`
	Email       string    `json:"email"`
	DisplayName string    `json:"display_name"`
	Verified    bool      `json:"verified"`
	CreatedAt   time.Time `json:"created_at"`
}

func toUserResp(u *User) userResp {
	return userResp{
		ID:          u.ID,
		Email:       u.Email,
		DisplayName: u.DisplayName,
		Verified:    u.Verified,
		CreatedAt:   u.CreatedAt,
	}
}

func toTokenResp(r *LoginResult) tokenResp {
	return tokenResp{
		AccessToken:      r.AccessToken,
		AccessExpiresAt:  r.AccessExpiresAt,
		RefreshToken:     r.RefreshToken,
		RefreshExpiresAt: r.RefreshExpiresAt,
		User:             toUserResp(r.User),
	}
}

// ----------------- handlers -----------------

func (h *Handlers) register(w http.ResponseWriter, r *http.Request) {
	var req registerReq
	if !decodeJSON(w, r, &req) {
		return
	}
	userID, err := h.svc.Register(r.Context(), req.Email, req.Password, req.DisplayName)
	if err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, http.StatusCreated, registerResp{UserID: userID})
}

func (h *Handlers) verify(w http.ResponseWriter, r *http.Request) {
	var req verifyReq
	if !decodeJSON(w, r, &req) {
		return
	}
	if err := h.svc.Verify(r.Context(), req.Token); err != nil {
		writeError(w, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (h *Handlers) login(w http.ResponseWriter, r *http.Request) {
	var req loginReq
	if !decodeJSON(w, r, &req) {
		return
	}
	result, err := h.svc.Login(r.Context(), req.Email, req.Password)
	if err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, toTokenResp(result))
}

func (h *Handlers) refresh(w http.ResponseWriter, r *http.Request) {
	var req refreshReq
	if !decodeJSON(w, r, &req) {
		return
	}
	if req.RefreshToken == "" {
		writeError(w, ErrRefreshInvalid)
		return
	}
	result, err := h.svc.Refresh(r.Context(), req.RefreshToken)
	if err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, toTokenResp(result))
}

func (h *Handlers) logout(w http.ResponseWriter, r *http.Request) {
	var req logoutReq
	if !decodeJSON(w, r, &req) {
		return
	}
	// Idempotent — empty/missing/invalid token still returns 204.
	if err := h.svc.Logout(r.Context(), req.RefreshToken); err != nil {
		slog.Error("logout: revoke failed", "err", err)
	}
	w.WriteHeader(http.StatusNoContent)
}

func (h *Handlers) me(w http.ResponseWriter, r *http.Request) {
	claims, ok := ClaimsFrom(r.Context())
	if !ok {
		writeError(w, ErrNotAuthenticated)
		return
	}
	user, err := h.svc.Me(r.Context(), claims.UserID)
	if err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, toUserResp(user))
}

// ----------------- helpers -----------------

// decodeJSON reads + decodes the request body into dst. On any parse error,
// writes a 400 response and returns false (handler should return).
func decodeJSON(w http.ResponseWriter, r *http.Request, dst any) bool {
	r.Body = http.MaxBytesReader(w, r.Body, 1<<20) // 1 MiB cap
	dec := json.NewDecoder(r.Body)
	dec.DisallowUnknownFields()
	if err := dec.Decode(dst); err != nil {
		writeError(w, &Error{
			Code:    "bad_request",
			Message: "malformed JSON: " + err.Error(),
			Status:  http.StatusBadRequest,
		})
		return false
	}
	if err := dec.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		writeError(w, &Error{
			Code:    "bad_request",
			Message: "malformed JSON: request body must contain a single JSON object",
			Status:  http.StatusBadRequest,
		})
		return false
	}
	return true
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if body != nil {
		_ = json.NewEncoder(w).Encode(body)
	}
}

// writeError converts an error into the standard JSON envelope and writes it.
// Unknown errors (non-*Error) become 500s; the original is logged but not
// surfaced to the client.
func writeError(w http.ResponseWriter, err error) {
	e := asAuthError(err)
	if e == nil {
		slog.Error("internal auth error", "err", err)
		e = &Error{
			Code:    "internal",
			Message: "internal server error",
			Status:  http.StatusInternalServerError,
		}
	}
	type envelope struct {
		Error struct {
			Code    string `json:"code"`
			Message string `json:"message"`
			Details any    `json:"details,omitempty"`
		} `json:"error"`
	}
	var env envelope
	env.Error.Code = e.Code
	env.Error.Message = e.Message
	env.Error.Details = e.Details
	writeJSON(w, e.Status, env)
}
