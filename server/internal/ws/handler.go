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
	"sync"
	"time"

	"github.com/coder/websocket"

	"github.com/CS-StudentGroup/pdc_final_project/server/internal/auth"
	"github.com/CS-StudentGroup/pdc_final_project/server/internal/rooms"
)

const maxControlFrameBytes int64 = 64 * 1024

// Handler handles WebSocket upgrade at GET /ws?token=<jwt>.
type Handler struct {
	jwtSecret      []byte
	version        string
	originPatterns []string
	sessions       *SessionRegistry
	rooms          *rooms.Registry
	connMu         sync.Mutex
	conns          map[*websocket.Conn]struct{}
}

func New(jwtSecret []byte, version string, originPatterns []string, roomRegistry *rooms.Registry) *Handler {
	if roomRegistry == nil {
		roomRegistry = rooms.NewRegistry()
	}
	return &Handler{
		jwtSecret:      jwtSecret,
		version:        version,
		originPatterns: append([]string(nil), originPatterns...),
		sessions:       NewSessionRegistry(),
		rooms:          roomRegistry,
		conns:          make(map[*websocket.Conn]struct{}),
	}
}

// CloseActiveConnections unblocks active read loops before http.Server
// shutdown waits for handlers to return.
func (h *Handler) CloseActiveConnections() {
	h.connMu.Lock()
	conns := make([]*websocket.Conn, 0, len(h.conns))
	for conn := range h.conns {
		conns = append(conns, conn)
	}
	h.connMu.Unlock()

	for _, conn := range conns {
		_ = conn.Close(websocket.StatusGoingAway, "server_shutdown")
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

	conn, err := websocket.Accept(w, r, h.acceptOptions())
	if err != nil {
		slog.Error("ws accept failed", "err", err)
		return
	}
	defer conn.CloseNow()
	conn.SetReadLimit(maxControlFrameBytes)
	h.trackConn(conn)
	defer h.untrackConn(conn)
	sender := &connSender{conn: conn}
	client := &rooms.Client{
		UserID:      claims.UserID,
		DisplayName: claims.DisplayName,
		Sender:      sender,
	}
	h.rooms.RegisterClient(client)
	defer h.rooms.UnregisterClient(claims.UserID)

	slog.Info("ws connected",
		"user_id", claims.UserID,
		"display_name", claims.DisplayName,
		"remote", r.RemoteAddr,
	)

	// Send hello with a short write deadline. The client awaits this before
	// considering the connection "live."
	if err := sender.SendEnvelope(r.Context(), "hello", "", helloPayload{
		ServerVersion:   h.version,
		YourUserID:      claims.UserID,
		YourDisplayName: claims.DisplayName,
	}); err != nil {
		slog.Error("ws hello write failed", "err", err, "user_id", claims.UserID)
		return
	}

	// Read loop. Phase 1.3 just logs incoming frames; future phases dispatch
	// by envelope.t.
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
		if msgType != websocket.MessageText {
			_ = sender.SendEnvelope(r.Context(), "err", "", map[string]string{
				"code":    "bad_request",
				"message": "binary control frames are not supported",
			})
			continue
		}
		var env envelope
		if err := json.Unmarshal(data, &env); err != nil || env.T == "" {
			_ = sender.SendEnvelope(r.Context(), "err", env.ID, map[string]string{
				"code":    "bad_request",
				"message": "invalid envelope",
			})
			continue
		}
		h.rooms.Handle(r.Context(), client, env.T, env.ID, env.D)
	}
}

func (h *Handler) rejectDuplicateSession(w http.ResponseWriter, r *http.Request, claims *auth.Claims) {
	conn, err := websocket.Accept(w, r, h.acceptOptions())
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

func (h *Handler) acceptOptions() *websocket.AcceptOptions {
	return &websocket.AcceptOptions{
		OriginPatterns: h.originPatterns,
	}
}

func (h *Handler) trackConn(conn *websocket.Conn) {
	h.connMu.Lock()
	defer h.connMu.Unlock()
	h.conns[conn] = struct{}{}
}

func (h *Handler) untrackConn(conn *websocket.Conn) {
	h.connMu.Lock()
	defer h.connMu.Unlock()
	delete(h.conns, conn)
}

type envelope struct {
	T  string          `json:"t"`
	ID string          `json:"id,omitempty"`
	D  json.RawMessage `json:"d,omitempty"`
}

type outgoingEnvelope struct {
	T  string `json:"t"`
	ID string `json:"id,omitempty"`
	D  any    `json:"d,omitempty"`
}

type connSender struct {
	conn    *websocket.Conn
	writeMu sync.Mutex
}

type helloPayload struct {
	ServerVersion   string `json:"server_version"`
	YourUserID      string `json:"your_user_id"`
	YourDisplayName string `json:"your_display_name"`
}

func (s *connSender) SendEnvelope(parent context.Context, msgType, id string, payload any) error {
	body, err := json.Marshal(outgoingEnvelope{
		T:  msgType,
		ID: id,
		D:  payload,
	})
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(parent, 5*time.Second)
	defer cancel()
	s.writeMu.Lock()
	defer s.writeMu.Unlock()
	return s.conn.Write(ctx, websocket.MessageText, body)
}
