// Package rooms owns Phase 2 room state for Skyward Race lobbies.
package rooms

import (
	"context"
	"crypto/rand"
	"encoding/json"
	"errors"
	"fmt"
	"math/big"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/oklog/ulid/v2"
)

const (
	TypeSkywardLobby = "skyward_lobby"

	VisibilityPrivate = "private"
	VisibilityPublic  = "public"

	StateWaiting = "waiting"
	StateInMatch = "in_match"

	DefaultCapacity    = 8
	MaxCapacity        = 8
	DefaultLevel       = 1
	DefaultEnvironment = "default"
)

const codeAlphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

var (
	ErrBadRequest = errors.New("bad_request")
	ErrNotFound   = errors.New("not_found")
	ErrFull       = errors.New("full")
	ErrForbidden  = errors.New("forbidden")
)

type Sender interface {
	SendEnvelope(ctx context.Context, msgType, id string, payload any) error
}

type Client struct {
	UserID      string
	DisplayName string
	Sender      Sender
}

type Registry struct {
	mu          sync.Mutex
	rooms       map[string]*Room
	codes       map[string]string
	userRoom    map[string]string
	clients     map[string]*Client
	subscribers map[string]struct{} // user_ids currently watching the public room browser
}

type Room struct {
	ID            string
	Code          string
	Type          string
	Visibility    string
	Name          string
	HostUserID    string
	Players       map[string]*Player
	JoinOrder     []string
	State         string
	Level         int
	EnvironmentID string
	Capacity      int
	CreatedAt     time.Time
	LastActivity  time.Time
}

type Player struct {
	UserID      string `json:"user_id"`
	DisplayName string `json:"display_name"`
	Ready       bool   `json:"ready"`
	IsHost      bool   `json:"is_host"`
	JoinedAt    string `json:"joined_at"`
}

type Snapshot struct {
	RoomID        string   `json:"room_id"`
	Code          string   `json:"code"`
	Type          string   `json:"type"`
	Visibility    string   `json:"visibility"`
	Name          string   `json:"name"`
	HostUserID    string   `json:"host_user_id"`
	Players       []Player `json:"players"`
	ReadySet      []string `json:"ready_set"`
	Level         int      `json:"level"`
	EnvironmentID string   `json:"environment_id"`
	Capacity      int      `json:"capacity"`
	State         string   `json:"state"`
}

type CreateRoomRequest struct {
	Type          string `json:"type"`
	Name          string `json:"name"`
	Visibility    string `json:"visibility"`
	Level         int    `json:"level"`
	EnvironmentID string `json:"environment_id"`
	Capacity      int    `json:"capacity"`
}

type JoinRoomRequest struct {
	Code string `json:"code"`
}

type SetReadyRequest struct {
	Ready bool `json:"ready"`
}

// BrowserEntry is the per-room shape pushed in room_list_update. Stays small
// on purpose — the browser only needs enough to decide which room to join,
// not the full lobby snapshot.
type BrowserEntry struct {
	Code          string `json:"code"`
	Name          string `json:"name"`
	Players       int    `json:"players"`
	Capacity      int    `json:"capacity"`
	Level         int    `json:"level"`
	EnvironmentID string `json:"environment_id"`
	State         string `json:"state"`
}

func NewRegistry() *Registry {
	return &Registry{
		rooms:       make(map[string]*Room),
		codes:       make(map[string]string),
		userRoom:    make(map[string]string),
		clients:     make(map[string]*Client),
		subscribers: make(map[string]struct{}),
	}
}

func (r *Registry) RegisterClient(client *Client) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.clients[client.UserID] = client
}

func (r *Registry) UnregisterClient(userID string) {
	r.mu.Lock()
	delete(r.subscribers, userID)
	roomID := r.userRoom[userID]
	var sends []sendOp
	if roomID != "" {
		sends = r.leaveLocked(userID)
	}
	delete(r.clients, userID)
	r.mu.Unlock()
	runSends(sends)
}

func (r *Registry) Handle(ctx context.Context, client *Client, msgType, requestID string, raw json.RawMessage) {
	var sends []sendOp

	r.mu.Lock()
	switch msgType {
	case "create_room":
		sends = r.handleCreateLocked(client, requestID, raw)
	case "join_room":
		sends = r.handleJoinLocked(client, requestID, raw)
	case "leave_room":
		sends = r.handleLeaveLocked(client, requestID)
	case "set_ready":
		sends = r.handleSetReadyLocked(client, requestID, raw)
	case "start_match":
		sends = r.handleStartMatchLocked(client, requestID)
	case "subscribe_room_list":
		sends = r.handleSubscribeRoomListLocked(client, requestID)
	case "unsubscribe_room_list":
		sends = r.handleUnsubscribeRoomListLocked(client, requestID)
	default:
		sends = []sendOp{reply(client, "err", requestID, errorPayload("unknown_message", "unknown control message: "+msgType))}
	}
	r.mu.Unlock()

	runSendsWithContext(ctx, sends)
}

func (r *Registry) handleCreateLocked(client *Client, requestID string, raw json.RawMessage) []sendOp {
	var req CreateRoomRequest
	if err := decodePayload(raw, &req); err != nil {
		return []sendOp{reply(client, "err", requestID, errorPayload("bad_request", err.Error()))}
	}
	req = normalizeCreateRequest(req, client)
	if req.Type != TypeSkywardLobby {
		return []sendOp{reply(client, "err", requestID, errorPayload("bad_request", "type must be skyward_lobby"))}
	}
	if req.Visibility != VisibilityPrivate && req.Visibility != VisibilityPublic {
		return []sendOp{reply(client, "err", requestID, errorPayload("bad_request", "visibility must be private or public"))}
	}

	sends := r.leaveLocked(client.UserID)
	code, err := r.uniqueCodeLocked()
	if err != nil {
		return append(sends, reply(client, "err", requestID, errorPayload("internal", "could not allocate room code")))
	}

	now := time.Now().UTC()
	room := &Room{
		ID:            ulid.Make().String(),
		Code:          code,
		Type:          req.Type,
		Visibility:    req.Visibility,
		Name:          req.Name,
		HostUserID:    client.UserID,
		Players:       make(map[string]*Player),
		State:         StateWaiting,
		Level:         req.Level,
		EnvironmentID: req.EnvironmentID,
		Capacity:      req.Capacity,
		CreatedAt:     now,
		LastActivity:  now,
	}
	r.rooms[room.ID] = room
	r.codes[room.Code] = room.ID
	r.addPlayerLocked(room, client)
	snapshot := room.snapshot()

	sends = append(sends,
		reply(client, "room_created", requestID, map[string]any{
			"code":     room.Code,
			"room_id":  room.ID,
			"snapshot": snapshot,
		}),
	)
	sends = append(sends, r.broadcastLobbyStateLocked(room)...)
	sends = append(sends, r.broadcastRoomListUpdateLocked()...)
	return sends
}

func (r *Registry) handleJoinLocked(client *Client, requestID string, raw json.RawMessage) []sendOp {
	var req JoinRoomRequest
	if err := decodePayload(raw, &req); err != nil {
		return []sendOp{reply(client, "join_err", requestID, map[string]string{"reason": "bad_request"})}
	}
	code := normalizeCode(req.Code)
	roomID := r.codes[code]
	room := r.rooms[roomID]
	if room == nil {
		return []sendOp{reply(client, "join_err", requestID, map[string]string{"reason": "not_found"})}
	}
	if room.State != StateWaiting {
		return []sendOp{reply(client, "join_err", requestID, map[string]string{"reason": "in_progress"})}
	}
	if _, exists := room.Players[client.UserID]; !exists && len(room.Players) >= room.Capacity {
		return []sendOp{reply(client, "join_err", requestID, map[string]string{"reason": "full"})}
	}

	sends := r.leaveLocked(client.UserID)
	r.addPlayerLocked(room, client)
	snapshot := room.snapshot()
	sends = append(sends,
		reply(client, "join_ok", requestID, map[string]any{
			"room_id":        room.ID,
			"your_player_id": client.UserID,
			"snapshot":       snapshot,
		}),
	)
	sends = append(sends, r.broadcastLobbyStateLocked(room)...)
	sends = append(sends, r.broadcastRoomListUpdateLocked()...)
	return sends
}

func (r *Registry) handleLeaveLocked(client *Client, requestID string) []sendOp {
	sends := r.leaveLocked(client.UserID)
	sends = append(sends, reply(client, "leave_ok", requestID, map[string]any{}))
	sends = append(sends, r.broadcastRoomListUpdateLocked()...)
	return sends
}

// handleStartMatchLocked transitions a waiting room to in_match and pushes
// match_started to every player. Host-only; all non-host players must be
// ready. Each recipient gets a payload customized with their own user_id
// under `your_player_id` so clients don't need to look it up separately.
//
// Phase 4a.2: state goes Waiting → InMatch with a 1.5s countdown via
// start_at_server_ts. The room stays in the registry; future end-of-match
// flow (Phase 5) will return it to Waiting or destroy it.
func (r *Registry) handleStartMatchLocked(client *Client, requestID string) []sendOp {
	room := r.rooms[r.userRoom[client.UserID]]
	if room == nil {
		return []sendOp{reply(client, "err", requestID, errorPayload("not_in_room", "user is not in a room"))}
	}
	if room.HostUserID != client.UserID {
		return []sendOp{reply(client, "err", requestID, errorPayload("forbidden", "only the host can start the match"))}
	}
	if room.State != StateWaiting {
		return []sendOp{reply(client, "err", requestID, errorPayload("already_started", "match is already in progress"))}
	}
	for _, p := range room.Players {
		if p.UserID == room.HostUserID {
			continue
		}
		if !p.Ready {
			return []sendOp{reply(client, "err", requestID, errorPayload("not_all_ready", "all non-host players must be ready"))}
		}
	}

	room.State = StateInMatch
	room.LastActivity = time.Now().UTC()
	seed := generateMatchSeed()
	startAt := time.Now().UnixMilli() + 1500 // 1.5s countdown until match logic begins

	sends := []sendOp{}
	if requestID != "" {
		sends = append(sends, reply(client, "start_match_ok", requestID, map[string]any{}))
	}
	for userID := range room.Players {
		recipient := r.clients[userID]
		if recipient == nil {
			continue
		}
		sends = append(sends, sendOp{
			client:  recipient,
			msgType: "match_started",
			id:      "",
			payload: map[string]any{
				"level":              room.Level,
				"environment_id":     room.EnvironmentID,
				"seed":               seed,
				"start_at_server_ts": startAt,
				"your_player_id":     userID,
				"room_id":            room.ID,
			},
		})
	}
	// Browser entries care about state — re-broadcast so public rooms move
	// from "waiting" → "in_match" in subscribers' views.
	sends = append(sends, r.broadcastRoomListUpdateLocked()...)
	return sends
}

// generateMatchSeed returns a positive int64 from crypto/rand. Used as the
// seed for LevelGenerator on every client + server, so it MUST be the same
// across recipients (we only generate it once per match_started).
func generateMatchSeed() int64 {
	n, err := rand.Int(rand.Reader, big.NewInt(1<<62))
	if err != nil {
		return time.Now().UnixNano()
	}
	return n.Int64()
}

// handleSubscribeRoomListLocked enrolls the client and immediately pushes the
// current public-room list. The optional subscribe_ok reply is only sent when
// the client provided a request id (i.e. used send_control_request).
func (r *Registry) handleSubscribeRoomListLocked(client *Client, requestID string) []sendOp {
	r.subscribers[client.UserID] = struct{}{}
	sends := []sendOp{
		{
			client:  client,
			msgType: "room_list_update",
			id:      "",
			payload: map[string]any{"rooms": r.publicRoomListLocked()},
		},
	}
	if requestID != "" {
		sends = append(sends, reply(client, "subscribe_ok", requestID, map[string]any{}))
	}
	return sends
}

// handleUnsubscribeRoomListLocked removes the client's subscription. Idempotent.
func (r *Registry) handleUnsubscribeRoomListLocked(client *Client, requestID string) []sendOp {
	delete(r.subscribers, client.UserID)
	if requestID != "" {
		return []sendOp{reply(client, "unsubscribe_ok", requestID, map[string]any{})}
	}
	return nil
}

func (r *Registry) handleSetReadyLocked(client *Client, requestID string, raw json.RawMessage) []sendOp {
	var req SetReadyRequest
	if err := decodePayload(raw, &req); err != nil {
		return []sendOp{reply(client, "err", requestID, errorPayload("bad_request", err.Error()))}
	}
	room := r.rooms[r.userRoom[client.UserID]]
	if room == nil {
		return []sendOp{reply(client, "err", requestID, errorPayload("not_in_room", "user is not in a room"))}
	}
	player := room.Players[client.UserID]
	if player == nil {
		return []sendOp{reply(client, "err", requestID, errorPayload("not_in_room", "user is not in a room"))}
	}
	player.Ready = req.Ready
	room.LastActivity = time.Now().UTC()

	sends := []sendOp{reply(client, "ready_ok", requestID, map[string]bool{"ready": req.Ready})}
	sends = append(sends, r.broadcastLobbyStateLocked(room)...)
	return sends
}

func (r *Registry) addPlayerLocked(room *Room, client *Client) {
	if existing := room.Players[client.UserID]; existing != nil {
		existing.DisplayName = client.DisplayName
		existing.IsHost = client.UserID == room.HostUserID
		r.userRoom[client.UserID] = room.ID
		return
	}
	player := &Player{
		UserID:      client.UserID,
		DisplayName: client.DisplayName,
		IsHost:      client.UserID == room.HostUserID,
		JoinedAt:    time.Now().UTC().Format(time.RFC3339),
	}
	room.Players[client.UserID] = player
	room.JoinOrder = append(room.JoinOrder, client.UserID)
	room.LastActivity = time.Now().UTC()
	r.userRoom[client.UserID] = room.ID
}

func (r *Registry) leaveLocked(userID string) []sendOp {
	roomID := r.userRoom[userID]
	if roomID == "" {
		return nil
	}
	delete(r.userRoom, userID)

	room := r.rooms[roomID]
	if room == nil {
		return nil
	}
	delete(room.Players, userID)
	room.JoinOrder = removeUser(room.JoinOrder, userID)
	room.LastActivity = time.Now().UTC()

	var sends []sendOp
	if len(room.Players) == 0 {
		delete(r.codes, room.Code)
		delete(r.rooms, room.ID)
		return nil
	}
	if room.HostUserID == userID {
		room.HostUserID = room.JoinOrder[0]
		for id, player := range room.Players {
			player.IsHost = id == room.HostUserID
		}
		sends = append(sends, r.broadcastLocked(room, "host_changed", "", map[string]string{
			"new_host_player_id": room.HostUserID,
		})...)
	}
	sends = append(sends, r.broadcastLobbyStateLocked(room)...)
	return sends
}

func (r *Registry) broadcastLobbyStateLocked(room *Room) []sendOp {
	return r.broadcastLocked(room, "lobby_state", "", room.snapshot())
}

// broadcastRoomListUpdateLocked fans the current public-room list out to every
// subscriber. Called after any state change that could affect what the browser
// shows (create / join / leave). set_ready and host_changed don't fire it —
// those don't change browser-visible fields.
func (r *Registry) broadcastRoomListUpdateLocked() []sendOp {
	if len(r.subscribers) == 0 {
		return nil
	}
	payload := map[string]any{"rooms": r.publicRoomListLocked()}
	out := make([]sendOp, 0, len(r.subscribers))
	for userID := range r.subscribers {
		client := r.clients[userID]
		if client == nil {
			continue
		}
		out = append(out, sendOp{
			client:  client,
			msgType: "room_list_update",
			id:      "",
			payload: payload,
		})
	}
	return out
}

// publicRoomListLocked builds the browser-visible slice. Sorted by code for
// stable client-side ordering.
func (r *Registry) publicRoomListLocked() []BrowserEntry {
	out := make([]BrowserEntry, 0)
	for _, room := range r.rooms {
		if room.Visibility != VisibilityPublic {
			continue
		}
		out = append(out, BrowserEntry{
			Code:          room.Code,
			Name:          room.Name,
			Players:       len(room.Players),
			Capacity:      room.Capacity,
			Level:         room.Level,
			EnvironmentID: room.EnvironmentID,
			State:         room.State,
		})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Code < out[j].Code })
	return out
}

func (r *Registry) broadcastLocked(room *Room, msgType, id string, payload any) []sendOp {
	out := make([]sendOp, 0, len(room.Players))
	for userID := range room.Players {
		client := r.clients[userID]
		if client != nil {
			out = append(out, sendOp{client: client, msgType: msgType, id: id, payload: payload})
		}
	}
	return out
}

func (r *Registry) uniqueCodeLocked() (string, error) {
	for i := 0; i < 5; i++ {
		code, err := generateCode()
		if err != nil {
			return "", err
		}
		if _, exists := r.codes[code]; !exists {
			return code, nil
		}
	}
	return "", fmt.Errorf("room code collision after retries")
}

func (room *Room) snapshot() Snapshot {
	players := make([]Player, 0, len(room.Players))
	readySet := make([]string, 0, len(room.Players))
	for _, userID := range room.JoinOrder {
		p := room.Players[userID]
		if p == nil {
			continue
		}
		cp := *p
		cp.IsHost = p.UserID == room.HostUserID
		players = append(players, cp)
		if p.Ready {
			readySet = append(readySet, p.UserID)
		}
	}
	sort.Strings(readySet)
	return Snapshot{
		RoomID:        room.ID,
		Code:          room.Code,
		Type:          room.Type,
		Visibility:    room.Visibility,
		Name:          room.Name,
		HostUserID:    room.HostUserID,
		Players:       players,
		ReadySet:      readySet,
		Level:         room.Level,
		EnvironmentID: room.EnvironmentID,
		Capacity:      room.Capacity,
		State:         room.State,
	}
}

func normalizeCreateRequest(req CreateRoomRequest, client *Client) CreateRoomRequest {
	req.Type = strings.TrimSpace(req.Type)
	if req.Type == "" {
		req.Type = TypeSkywardLobby
	}
	req.Visibility = strings.TrimSpace(strings.ToLower(req.Visibility))
	if req.Visibility == "" {
		req.Visibility = VisibilityPrivate
	}
	req.Name = strings.TrimSpace(req.Name)
	if req.Name == "" {
		req.Name = client.DisplayName + "'s room"
	}
	if len(req.Name) > 32 {
		req.Name = req.Name[:32]
	}
	if req.Level < 1 || req.Level > 10 {
		req.Level = DefaultLevel
	}
	req.EnvironmentID = strings.TrimSpace(req.EnvironmentID)
	if req.EnvironmentID == "" {
		req.EnvironmentID = DefaultEnvironment
	}
	if req.Capacity <= 0 || req.Capacity > MaxCapacity {
		req.Capacity = DefaultCapacity
	}
	return req
}

func normalizeCode(code string) string {
	code = strings.TrimSpace(strings.ToUpper(code))
	var b strings.Builder
	for _, ch := range code {
		if strings.ContainsRune(codeAlphabet, ch) {
			b.WriteRune(ch)
		}
	}
	return b.String()
}

func generateCode() (string, error) {
	var b strings.Builder
	max := big.NewInt(int64(len(codeAlphabet)))
	for i := 0; i < 6; i++ {
		n, err := rand.Int(rand.Reader, max)
		if err != nil {
			return "", err
		}
		b.WriteByte(codeAlphabet[n.Int64()])
	}
	return b.String(), nil
}

func decodePayload(raw json.RawMessage, dst any) error {
	if len(raw) == 0 || string(raw) == "null" {
		raw = []byte("{}")
	}
	if err := json.Unmarshal(raw, dst); err != nil {
		return fmt.Errorf("invalid payload: %w", err)
	}
	return nil
}

func removeUser(ids []string, userID string) []string {
	out := ids[:0]
	for _, id := range ids {
		if id != userID {
			out = append(out, id)
		}
	}
	return out
}

type sendOp struct {
	client  *Client
	msgType string
	id      string
	payload any
}

func reply(client *Client, msgType, id string, payload any) sendOp {
	return sendOp{client: client, msgType: msgType, id: id, payload: payload}
}

func errorPayload(code, message string) map[string]string {
	return map[string]string{
		"code":    code,
		"message": message,
	}
}

func runSends(sends []sendOp) {
	runSendsWithContext(context.Background(), sends)
}

func runSendsWithContext(ctx context.Context, sends []sendOp) {
	for _, send := range sends {
		if send.client == nil || send.client.Sender == nil {
			continue
		}
		_ = send.client.Sender.SendEnvelope(ctx, send.msgType, send.id, send.payload)
	}
}
