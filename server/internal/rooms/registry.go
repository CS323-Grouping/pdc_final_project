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

	"github.com/CS-StudentGroup/pdc_final_project/server/internal/avatars"
	"github.com/oklog/ulid/v2"
)

const (
	TypeSkywardLobby = "skyward_lobby"

	VisibilityPrivate = "private"
	VisibilityPublic  = "public"

	StateWaiting = "waiting"
	StateInMatch = "in_match"
	StateResults = "results"

	DefaultCapacity      = 5
	MaxCapacity          = 5
	MaxLargeRoomCapacity = 10
	DefaultLevel         = 1
	DefaultEnvironment   = "sky"

	MatchFinishY       = 24.0
	ReconnectGraceTime = 30 * time.Second
)

const codeAlphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

var (
	ErrBadRequest = errors.New("bad_request")
	ErrNotFound   = errors.New("not_found")
	ErrFull       = errors.New("full")
	ErrForbidden  = errors.New("forbidden")
)

var knownEnvironmentIDs = map[string]struct{}{
	"default": {},
	"sky":     {},
	"ice":     {},
}

type Sender interface {
	SendEnvelope(ctx context.Context, msgType, id string, payload any) error
}

type Client struct {
	UserID      string
	DisplayName string
	Avatar      avatars.Payload
	Sender      Sender
}

type Registry struct {
	mu          sync.Mutex
	rooms       map[string]*Room
	codes       map[string]string
	userRoom    map[string]string
	clients     map[string]*Client
	reconnects  map[string]*time.Timer
	subscribers map[string]struct{} // user_ids currently watching the public room browser
}

type Room struct {
	ID             string
	Code           string
	Type           string
	Visibility     string
	Name           string
	HostUserID     string
	Players        map[string]*Player
	JoinOrder      []string
	State          string
	Level          int
	EnvironmentID  string
	Capacity       int
	CreatedAt      time.Time
	LastActivity   time.Time
	MatchSeed      int64
	MatchStartAtMS int64
	MatchPositions map[string]MatchPlayerState
	CollectedOrbs  map[string]string
	Placements     []MatchPlacement
}

type Player struct {
	UserID                 string          `json:"user_id"`
	DisplayName            string          `json:"display_name"`
	Ready                  bool            `json:"ready"`
	IsHost                 bool            `json:"is_host"`
	JoinedAt               string          `json:"joined_at"`
	Avatar                 avatars.Payload `json:"avatar"`
	Connected              bool            `json:"connected"`
	ReconnectUntilServerTS int64           `json:"reconnect_until_server_ts,omitempty"`
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

type SetEnvironmentRequest struct {
	EnvironmentID string `json:"environment_id"`
}

type PlayerStateRequest struct {
	Tick     int64   `json:"tick"`
	X        float64 `json:"x"`
	Y        float64 `json:"y"`
	VX       float64 `json:"vx"`
	VY       float64 `json:"vy"`
	Grounded bool    `json:"grounded"`
	Facing   int     `json:"facing"`
}

type MatchPlayerState struct {
	UserID      string  `json:"user_id"`
	DisplayName string  `json:"display_name"`
	Tick        int64   `json:"tick"`
	X           float64 `json:"x"`
	Y           float64 `json:"y"`
	VX          float64 `json:"vx"`
	VY          float64 `json:"vy"`
	Grounded    bool    `json:"grounded"`
	Facing      int     `json:"facing"`
	ServerTS    int64   `json:"server_ts"`
}

type OrbCollectedRequest struct {
	OrbID string `json:"orb_id"`
}

type PlayerEliminatedRequest struct {
	Reason string `json:"reason"`
}

type OrbCollectedPayload struct {
	OrbID       string `json:"orb_id"`
	UserID      string `json:"user_id"`
	DisplayName string `json:"display_name"`
	ServerTS    int64  `json:"server_ts"`
}

type MatchPlacement struct {
	UserID             string `json:"user_id"`
	DisplayName        string `json:"display_name"`
	Place              int    `json:"place"`
	Result             string `json:"result"`
	FinishedAtServerTS int64  `json:"finished_at_server_ts"`
}

type MatchResultsPayload struct {
	Placements []MatchPlacement `json:"placements"`
	Final      bool             `json:"final"`
}

type SessionRejoinedPayload struct {
	RoomID   string   `json:"room_id"`
	State    string   `json:"state"`
	Snapshot Snapshot `json:"snapshot"`
}

type MatchSnapshotPayload struct {
	Level           int                `json:"level"`
	EnvironmentID   string             `json:"environment_id"`
	Seed            int64              `json:"seed"`
	StartAtServerTS int64              `json:"start_at_server_ts"`
	YourPlayerID    string             `json:"your_player_id"`
	RoomID          string             `json:"room_id"`
	RoomState       string             `json:"room_state"`
	CollectedOrbs   []string           `json:"collected_orbs"`
	Placements      []MatchPlacement   `json:"placements"`
	Final           bool               `json:"final"`
	PeerStates      []MatchPlayerState `json:"peer_states"`
	Snapshot        Snapshot           `json:"snapshot"`
}

type AvatarUpdatedPayload struct {
	UserID     string        `json:"user_id"`
	Model      avatars.Model `json:"model"`
	HeadPNGB64 string        `json:"head_png_b64,omitempty"`
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
		reconnects:  make(map[string]*time.Timer),
		subscribers: make(map[string]struct{}),
	}
}

func (r *Registry) RegisterClient(client *Client) {
	r.mu.Lock()
	defer r.mu.Unlock()
	client.Avatar = avatars.NormalizeOrDefault(client.Avatar)
	r.clients[client.UserID] = client
	r.stopReconnectTimerLocked(client.UserID)
	if room := r.rooms[r.userRoom[client.UserID]]; room != nil {
		if player := room.Players[client.UserID]; player != nil {
			player.DisplayName = client.DisplayName
			player.Avatar = client.Avatar
			player.Connected = true
			player.ReconnectUntilServerTS = 0
			room.LastActivity = time.Now().UTC()
		}
	}
}

func (r *Registry) UnregisterClient(userID string) {
	r.mu.Lock()
	delete(r.subscribers, userID)
	roomID := r.userRoom[userID]
	var sends []sendOp
	if roomID != "" {
		sends = r.markDisconnectedLocked(userID)
	}
	delete(r.clients, userID)
	r.mu.Unlock()
	runSends(sends)
}

func (r *Registry) ReplaySession(ctx context.Context, userID string) {
	var sends []sendOp

	r.mu.Lock()
	client := r.clients[userID]
	room := r.rooms[r.userRoom[userID]]
	if client != nil && room != nil && room.Players[userID] != nil {
		snapshot := room.snapshot()
		sends = append(sends, reply(client, "session_rejoined", "", SessionRejoinedPayload{
			RoomID:   room.ID,
			State:    room.State,
			Snapshot: snapshot,
		}))
		sends = append(sends, reply(client, "lobby_state", "", snapshot))
		if room.State == StateInMatch || room.State == StateResults {
			sends = append(sends, reply(client, "match_snapshot", "", room.matchSnapshotFor(userID, snapshot)))
		}
		sends = append(sends, r.broadcastLockedExcept(room, "lobby_state", "", snapshot, userID)...)
	}
	r.mu.Unlock()

	runSendsWithContext(ctx, sends)
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
	case "set_environment":
		sends = r.handleSetEnvironmentLocked(client, requestID, raw)
	case "start_match":
		sends = r.handleStartMatchLocked(client, requestID)
	case "player_state":
		sends = r.handlePlayerStateLocked(client, requestID, raw)
	case "orb_collected":
		sends = r.handleOrbCollectedLocked(client, requestID, raw)
	case "player_eliminated":
		sends = r.handlePlayerEliminatedLocked(client, requestID, raw)
	case "request_rematch":
		sends = r.handleRequestRematchLocked(client, requestID)
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

func (r *Registry) SetAvatarForClient(ctx context.Context, userID string, avatar avatars.Payload) {
	avatar = avatars.NormalizeOrDefault(avatar)
	var sends []sendOp

	r.mu.Lock()
	if client := r.clients[userID]; client != nil {
		client.Avatar = avatar
	}
	room := r.rooms[r.userRoom[userID]]
	if room != nil {
		if player := room.Players[userID]; player != nil {
			player.Avatar = avatar
			room.LastActivity = time.Now().UTC()
			payload := AvatarUpdatedPayload{
				UserID:     userID,
				Model:      avatar.Model,
				HeadPNGB64: avatar.HeadPNGB64,
			}
			sends = append(sends, r.broadcastLocked(room, "avatar_updated", "", payload)...)
			sends = append(sends, r.broadcastLobbyStateLocked(room)...)
		}
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
	if !isKnownEnvironmentID(req.EnvironmentID) {
		return []sendOp{reply(client, "err", requestID, errorPayload("unknown_environment", "environment is not available"))}
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
	room.MatchSeed = seed
	startAt := time.Now().UnixMilli() + 1500 // 1.5s countdown until match logic begins
	room.MatchStartAtMS = startAt
	room.MatchPositions = make(map[string]MatchPlayerState, len(room.Players))
	room.CollectedOrbs = make(map[string]string)
	room.Placements = nil

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

func (r *Registry) handlePlayerStateLocked(client *Client, requestID string, raw json.RawMessage) []sendOp {
	var req PlayerStateRequest
	if err := decodePayload(raw, &req); err != nil {
		return []sendOp{reply(client, "err", requestID, errorPayload("bad_request", err.Error()))}
	}
	room := r.rooms[r.userRoom[client.UserID]]
	if room == nil || room.Players[client.UserID] == nil {
		return []sendOp{reply(client, "err", requestID, errorPayload("not_in_room", "user is not in a room"))}
	}
	if room.State != StateInMatch {
		return []sendOp{reply(client, "err", requestID, errorPayload("not_in_match", "room is not in an active match"))}
	}

	now := time.Now().UTC()
	player := room.Players[client.UserID]
	state := MatchPlayerState{
		UserID:      client.UserID,
		DisplayName: player.DisplayName,
		Tick:        req.Tick,
		X:           req.X,
		Y:           req.Y,
		VX:          req.VX,
		VY:          req.VY,
		Grounded:    req.Grounded,
		Facing:      normalizeFacing(req.Facing),
		ServerTS:    now.UnixMilli(),
	}
	if room.MatchPositions == nil {
		room.MatchPositions = make(map[string]MatchPlayerState, len(room.Players))
	}
	room.MatchPositions[client.UserID] = state
	room.LastActivity = now

	sends := r.broadcastLockedExcept(room, "peer_state_update", "", state, client.UserID)
	if state.Y <= MatchFinishY {
		sends = append(sends, r.recordPlacementLocked(room, player, "finished", now)...)
	}
	return sends
}

func (r *Registry) handleOrbCollectedLocked(client *Client, requestID string, raw json.RawMessage) []sendOp {
	var req OrbCollectedRequest
	if err := decodePayload(raw, &req); err != nil {
		return []sendOp{reply(client, "err", requestID, errorPayload("bad_request", err.Error()))}
	}
	req.OrbID = strings.TrimSpace(req.OrbID)
	if req.OrbID == "" || len(req.OrbID) > 80 {
		return []sendOp{reply(client, "err", requestID, errorPayload("bad_request", "orb_id is required"))}
	}
	room := r.rooms[r.userRoom[client.UserID]]
	if room == nil || room.Players[client.UserID] == nil {
		return []sendOp{reply(client, "err", requestID, errorPayload("not_in_room", "user is not in a room"))}
	}
	if room.State != StateInMatch {
		return []sendOp{reply(client, "err", requestID, errorPayload("not_in_match", "room is not in an active match"))}
	}
	if room.CollectedOrbs == nil {
		room.CollectedOrbs = make(map[string]string)
	}
	if collectorID := room.CollectedOrbs[req.OrbID]; collectorID != "" {
		if requestID != "" {
			return []sendOp{reply(client, "orb_collect_ok", requestID, map[string]string{"orb_id": req.OrbID})}
		}
		return nil
	}

	now := time.Now().UTC()
	player := room.Players[client.UserID]
	room.CollectedOrbs[req.OrbID] = client.UserID
	room.LastActivity = now

	payload := OrbCollectedPayload{
		OrbID:       req.OrbID,
		UserID:      client.UserID,
		DisplayName: player.DisplayName,
		ServerTS:    now.UnixMilli(),
	}
	sends := r.broadcastLocked(room, "orb_collected", "", payload)
	if requestID != "" {
		sends = append(sends, reply(client, "orb_collect_ok", requestID, map[string]string{"orb_id": req.OrbID}))
	}
	return sends
}

func (r *Registry) handlePlayerEliminatedLocked(client *Client, requestID string, raw json.RawMessage) []sendOp {
	var req PlayerEliminatedRequest
	if err := decodePayload(raw, &req); err != nil {
		return []sendOp{reply(client, "err", requestID, errorPayload("bad_request", err.Error()))}
	}
	room := r.rooms[r.userRoom[client.UserID]]
	if room == nil || room.Players[client.UserID] == nil {
		return []sendOp{reply(client, "err", requestID, errorPayload("not_in_room", "user is not in a room"))}
	}
	if room.State != StateInMatch {
		return []sendOp{reply(client, "err", requestID, errorPayload("not_in_match", "room is not in an active match"))}
	}
	now := time.Now().UTC()
	player := room.Players[client.UserID]
	sends := r.recordPlacementLocked(room, player, "eliminated", now)
	if requestID != "" {
		sends = append(sends, reply(client, "eliminated_ok", requestID, map[string]any{}))
	}
	return sends
}

func (r *Registry) handleRequestRematchLocked(client *Client, requestID string) []sendOp {
	room := r.rooms[r.userRoom[client.UserID]]
	if room == nil {
		return []sendOp{reply(client, "err", requestID, errorPayload("not_in_room", "user is not in a room"))}
	}
	if room.HostUserID != client.UserID {
		return []sendOp{reply(client, "err", requestID, errorPayload("forbidden", "only the host can request a rematch"))}
	}
	if room.State != StateResults {
		return []sendOp{reply(client, "err", requestID, errorPayload("not_in_results", "rematch is only available after results"))}
	}

	room.State = StateWaiting
	room.MatchSeed = 0
	room.MatchStartAtMS = 0
	room.MatchPositions = nil
	room.CollectedOrbs = nil
	room.Placements = nil
	for _, player := range room.Players {
		player.Ready = false
	}
	room.LastActivity = time.Now().UTC()
	snapshot := room.snapshot()

	sends := []sendOp{reply(client, "rematch_ok", requestID, map[string]any{"snapshot": snapshot})}
	sends = append(sends, r.broadcastLobbyStateLocked(room)...)
	sends = append(sends, r.broadcastRoomListUpdateLocked()...)
	return sends
}

func (r *Registry) recordPlacementLocked(room *Room, player *Player, result string, finishedAt time.Time) []sendOp {
	for _, placement := range room.Placements {
		if placement.UserID == player.UserID {
			return nil
		}
	}
	room.Placements = append(room.Placements, MatchPlacement{
		UserID:             player.UserID,
		DisplayName:        player.DisplayName,
		Place:              len(room.Placements) + 1,
		Result:             result,
		FinishedAtServerTS: finishedAt.UnixMilli(),
	})
	room.LastActivity = finishedAt
	final := len(room.Placements) >= len(room.Players)
	if final {
		room.State = StateResults
	}
	sends := r.broadcastLocked(room, "match_results", "", MatchResultsPayload{
		Placements: append([]MatchPlacement(nil), room.Placements...),
		Final:      final,
	})
	if final {
		sends = append(sends, r.broadcastRoomListUpdateLocked()...)
	}
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

func (r *Registry) handleSetEnvironmentLocked(client *Client, requestID string, raw json.RawMessage) []sendOp {
	var req SetEnvironmentRequest
	if err := decodePayload(raw, &req); err != nil {
		return []sendOp{reply(client, "err", requestID, errorPayload("bad_request", err.Error()))}
	}
	environmentID := normalizeEnvironmentID(req.EnvironmentID)
	if !isKnownEnvironmentID(environmentID) {
		return []sendOp{reply(client, "err", requestID, errorPayload("unknown_environment", "environment is not available"))}
	}

	room := r.rooms[r.userRoom[client.UserID]]
	if room == nil {
		return []sendOp{reply(client, "err", requestID, errorPayload("not_in_room", "user is not in a room"))}
	}
	if room.HostUserID != client.UserID {
		return []sendOp{reply(client, "err", requestID, errorPayload("forbidden", "only the host can change the environment"))}
	}
	if room.State != StateWaiting {
		return []sendOp{reply(client, "err", requestID, errorPayload("already_started", "environment cannot change after the match starts"))}
	}

	room.EnvironmentID = environmentID
	for _, player := range room.Players {
		player.Ready = false
	}
	room.LastActivity = time.Now().UTC()

	sends := []sendOp{reply(client, "environment_ok", requestID, map[string]string{"environment_id": environmentID})}
	sends = append(sends, r.broadcastLobbyStateLocked(room)...)
	sends = append(sends, r.broadcastRoomListUpdateLocked()...)
	return sends
}

func (r *Registry) addPlayerLocked(room *Room, client *Client) {
	if existing := room.Players[client.UserID]; existing != nil {
		existing.DisplayName = client.DisplayName
		existing.IsHost = client.UserID == room.HostUserID
		existing.Avatar = avatars.NormalizeOrDefault(client.Avatar)
		existing.Connected = true
		existing.ReconnectUntilServerTS = 0
		r.stopReconnectTimerLocked(client.UserID)
		r.userRoom[client.UserID] = room.ID
		return
	}
	player := &Player{
		UserID:      client.UserID,
		DisplayName: client.DisplayName,
		IsHost:      client.UserID == room.HostUserID,
		JoinedAt:    time.Now().UTC().Format(time.RFC3339),
		Avatar:      avatars.NormalizeOrDefault(client.Avatar),
		Connected:   true,
	}
	room.Players[client.UserID] = player
	room.JoinOrder = append(room.JoinOrder, client.UserID)
	room.LastActivity = time.Now().UTC()
	r.userRoom[client.UserID] = room.ID
}

func (r *Registry) leaveLocked(userID string) []sendOp {
	r.stopReconnectTimerLocked(userID)
	roomID := r.userRoom[userID]
	if roomID == "" {
		return nil
	}
	delete(r.userRoom, userID)

	room := r.rooms[roomID]
	if room == nil {
		return nil
	}
	wasMatch := room.State == StateInMatch || room.State == StateResults
	displayName := ""
	if player := room.Players[userID]; player != nil {
		displayName = player.DisplayName
	}
	delete(room.Players, userID)
	room.JoinOrder = removeUser(room.JoinOrder, userID)
	if room.MatchPositions != nil {
		delete(room.MatchPositions, userID)
	}
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
	if wasMatch {
		sends = append(sends, r.broadcastLocked(room, "peer_left", "", map[string]string{
			"user_id":      userID,
			"display_name": displayName,
		})...)
	}
	sends = append(sends, r.broadcastLobbyStateLocked(room)...)
	return sends
}

func (r *Registry) markDisconnectedLocked(userID string) []sendOp {
	room := r.rooms[r.userRoom[userID]]
	if room == nil {
		return nil
	}
	player := room.Players[userID]
	if player == nil {
		return nil
	}
	deadline := time.Now().UTC().Add(ReconnectGraceTime)
	player.Connected = false
	player.ReconnectUntilServerTS = deadline.UnixMilli()
	room.LastActivity = time.Now().UTC()
	r.stopReconnectTimerLocked(userID)
	r.reconnects[userID] = time.AfterFunc(ReconnectGraceTime, func() {
		r.finalizeReconnectTimeout(userID)
	})
	return r.broadcastLobbyStateLocked(room)
}

func (r *Registry) stopReconnectTimerLocked(userID string) {
	timer := r.reconnects[userID]
	if timer != nil {
		timer.Stop()
		delete(r.reconnects, userID)
	}
}

func (r *Registry) finalizeReconnectTimeout(userID string) {
	var sends []sendOp

	r.mu.Lock()
	if client := r.clients[userID]; client == nil {
		room := r.rooms[r.userRoom[userID]]
		player := (*Player)(nil)
		if room != nil {
			player = room.Players[userID]
		}
		if room != nil && player != nil && !player.Connected {
			sends = append(sends, r.leaveLocked(userID)...)
			sends = append(sends, r.broadcastRoomListUpdateLocked()...)
		} else {
			delete(r.reconnects, userID)
		}
	} else {
		delete(r.reconnects, userID)
	}
	r.mu.Unlock()

	runSends(sends)
}

func (r *Registry) broadcastLobbyStateLocked(room *Room) []sendOp {
	return r.broadcastLocked(room, "lobby_state", "", room.snapshot())
}

// broadcastRoomListUpdateLocked fans the current public-room list out to every
// subscriber. Called after any state change that could affect what the browser
// shows (create / join / leave / environment / match state). set_ready and
// host_changed don't fire it — those don't change browser-visible fields.
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

func (r *Registry) broadcastLockedExcept(room *Room, msgType, id string, payload any, excludedUserID string) []sendOp {
	out := make([]sendOp, 0, len(room.Players))
	for userID := range room.Players {
		if userID == excludedUserID {
			continue
		}
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

func (room *Room) matchSnapshotFor(userID string, snapshot Snapshot) MatchSnapshotPayload {
	collected := make([]string, 0, len(room.CollectedOrbs))
	for orbID := range room.CollectedOrbs {
		collected = append(collected, orbID)
	}
	sort.Strings(collected)

	peerStates := make([]MatchPlayerState, 0, len(room.MatchPositions))
	for peerID, state := range room.MatchPositions {
		if peerID == userID {
			continue
		}
		peerStates = append(peerStates, state)
	}
	sort.Slice(peerStates, func(i, j int) bool {
		return peerStates[i].UserID < peerStates[j].UserID
	})

	return MatchSnapshotPayload{
		Level:           room.Level,
		EnvironmentID:   room.EnvironmentID,
		Seed:            room.MatchSeed,
		StartAtServerTS: room.MatchStartAtMS,
		YourPlayerID:    userID,
		RoomID:          room.ID,
		RoomState:       room.State,
		CollectedOrbs:   collected,
		Placements:      append([]MatchPlacement(nil), room.Placements...),
		Final:           room.State == StateResults,
		PeerStates:      peerStates,
		Snapshot:        snapshot,
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
	req.EnvironmentID = normalizeEnvironmentID(req.EnvironmentID)
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

func normalizeEnvironmentID(environmentID string) string {
	return strings.TrimSpace(strings.ToLower(environmentID))
}

func isKnownEnvironmentID(environmentID string) bool {
	_, ok := knownEnvironmentIDs[environmentID]
	return ok
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

func normalizeFacing(facing int) int {
	if facing < 0 {
		return -1
	}
	return 1
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
