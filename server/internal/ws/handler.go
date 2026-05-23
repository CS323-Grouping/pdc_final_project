// Package ws hosts the single control WebSocket endpoint clients connect to
// after successful auth. Phase 1.3 only proves the handshake — JWT validated
// from the query string, "hello" envelope sent to the client, read loop logs
// incoming frames. Real message dispatch (room lifecycle, lobby browser,
// etc.) lands in Phase 2.
//
// Wire format: every frame is a JSON object with shape
//
//	{ "t": "<msg_type>", "id": "<opt correlation>", "d": { <payload> } }
//
// See vault: Networking - Message Contract.md.
package ws

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"time"

	"github.com/coder/websocket"

	"github.com/CS-StudentGroup/pdc_final_project/server/internal/auth"
)

// Handler handles WebSocket upgrade at GET /ws?token=<jwt>.
type Handler struct {
	jwtSecret []byte
	version   string
	sessions  *SessionRegistry
}

func New(jwtSecret []byte, version string) *Handler {
	return &Handler{
		jwtSecret: jwtSecret,
		version:   version,
		sessions:  NewSessionRegistry(),
	}
}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	// JWT from query string (Godot's WebSocketPeer can't easily set custom
	// headers; query string is the simplest path. Mitigation: short token
	// TTL + access logs scrub `?token=` — see vault Transport & Auth.)
	token := r.URL.Query().Get("token")
	if token == "" {
		http.Error(w, "missing token", http.StatusUnauthorized)
		return
	}
	claims, err := auth.VerifyAccessToken(h.jwtSecret, token)
	if err != nil {
		http.Error(w, "invalid token", http.StatusUnauthorized)
		return
	}
	if !h.sessions.TryReserve(claims.UserID) {
		h.rejectDuplicateSession(w, r, claims)
		return
	}
	defer h.sessions.Release(claims.UserID)

	conn, err := websocket.Accept(w, r, &websocket.AcceptOptions{
		// Local dev: any origin. Lock down before public deploy with
		// OriginPatterns (e.g. ["hub.example.com"]).
		InsecureSkipVerify: true,
	})
	if err != nil {
		slog.Error("ws accept failed", "err", err)
		return
	}
	defer conn.CloseNow()

	slog.Info("ws connected",
		"user_id", claims.UserID,
		"display_name", claims.DisplayName,
		"remote", r.RemoteAddr,
	)

	// Send hello with a short write deadline. The client awaits this before
	// considering the connection "live."
	if err := h.sendHello(r.Context(), conn, claims); err != nil {
		slog.Error("ws hello write failed", "err", err, "user_id", claims.UserID)
		return
	}

	// Read loop. Phase 1.3 just logs incoming frames; future phases dispatch
	// by envelope.t.
	//
	// TODO Phase 7: track open connections so srv.Shutdown can close them
	// proactively. Right now srv.Shutdown blocks until clients disconnect.
	for {
		msgType, data, err := conn.Read(r.Context())
		if err != nil {
			// Includes normal close (status 1000/1001), network blip, and
			// context cancellation on server shutdown.
			slog.Info("ws disconnected",
				"user_id", claims.UserID,
				"err", err,
			)
			return
		}
		slog.Debug("ws frame received",
			"user_id", claims.UserID,
			"msg_type", msgType,
			"len", len(data),
		)
	}
}

func (h *Handler) rejectDuplicateSession(w http.ResponseWriter, r *http.Request, claims *auth.Claims) {
	conn, err := websocket.Accept(w, r, &websocket.AcceptOptions{
		InsecureSkipVerify: true,
	})
	if err != nil {
		slog.Error("ws duplicate accept failed", "err", err, "user_id", claims.UserID)
		return
	}
	slog.Warn("ws duplicate session rejected",
		"user_id", claims.UserID,
		"display_name", claims.DisplayName,
		"remote", r.RemoteAddr,
	)
	_ = conn.Close(websocket.StatusPolicyViolation, "account_already_connected")
}

type envelope struct {
	T string `json:"t"`
	D any    `json:"d,omitempty"`
}

type helloPayload struct {
	ServerVersion   string `json:"server_version"`
	YourUserID      string `json:"your_user_id"`
	YourDisplayName string `json:"your_display_name"`
}

func (h *Handler) sendHello(parent context.Context, conn *websocket.Conn, claims *auth.Claims) error {
	body, err := json.Marshal(envelope{
		T: "hello",
		D: helloPayload{
			ServerVersion:   h.version,
			YourUserID:      claims.UserID,
			YourDisplayName: claims.DisplayName,
		},
	})
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(parent, 5*time.Second)
	defer cancel()
	return conn.Write(ctx, websocket.MessageText, body)
}
