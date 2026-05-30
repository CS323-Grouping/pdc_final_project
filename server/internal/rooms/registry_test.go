package rooms

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/CS-StudentGroup/pdc_final_project/server/internal/avatars"
)

type sentEnvelope struct {
	T  string
	ID string
	D  any
}

type fakeSender struct {
	messages []sentEnvelope
}

func (s *fakeSender) SendEnvelope(_ context.Context, msgType, id string, payload any) error {
	s.messages = append(s.messages, sentEnvelope{T: msgType, ID: id, D: payload})
	return nil
}

func TestRegistryCreateJoinReadyAndHostPromotion(t *testing.T) {
	reg := NewRegistry()
	hostSender := &fakeSender{}
	joinerSender := &fakeSender{}
	host := &Client{UserID: "host_user", DisplayName: "host", Sender: hostSender}
	joiner := &Client{UserID: "join_user", DisplayName: "joiner", Sender: joinerSender}
	reg.RegisterClient(host)
	reg.RegisterClient(joiner)

	reg.Handle(context.Background(), host, "create_room", "req-1", mustJSON(t, map[string]any{
		"type":       TypeSkywardLobby,
		"name":       "Test Room",
		"visibility": VisibilityPrivate,
		"level":      4,
		"capacity":   5,
	}))

	created := findMessage(t, hostSender.messages, "room_created")
	payload := created.D.(map[string]any)
	code := payload["code"].(string)
	if len(code) != 6 {
		t.Fatalf("code = %q, want 6 characters", code)
	}
	if created.ID != "req-1" {
		t.Fatalf("reply id = %q, want req-1", created.ID)
	}

	reg.Handle(context.Background(), joiner, "join_room", "req-2", mustJSON(t, map[string]string{"code": code}))
	joined := findMessage(t, joinerSender.messages, "join_ok")
	if joined.ID != "req-2" {
		t.Fatalf("join reply id = %q, want req-2", joined.ID)
	}
	hostLobby := lastMessage(t, hostSender.messages, "lobby_state")
	hostSnapshot := hostLobby.D.(Snapshot)
	if len(hostSnapshot.Players) != 2 {
		t.Fatalf("host lobby players = %d, want 2", len(hostSnapshot.Players))
	}
	if hostSnapshot.EnvironmentID != DefaultEnvironment {
		t.Fatalf("environment = %q, want %q", hostSnapshot.EnvironmentID, DefaultEnvironment)
	}
	if hostSnapshot.Capacity != DefaultCapacity {
		t.Fatalf("capacity = %d, want %d", hostSnapshot.Capacity, DefaultCapacity)
	}

	reg.Handle(context.Background(), joiner, "set_ready", "req-3", mustJSON(t, map[string]bool{"ready": true}))
	ready := findMessage(t, joinerSender.messages, "ready_ok")
	if ready.ID != "req-3" {
		t.Fatalf("ready reply id = %q, want req-3", ready.ID)
	}
	readySnapshot := lastMessage(t, hostSender.messages, "lobby_state").D.(Snapshot)
	if len(readySnapshot.ReadySet) != 1 || readySnapshot.ReadySet[0] != "join_user" {
		t.Fatalf("ready_set = %#v, want join_user", readySnapshot.ReadySet)
	}

	reg.UnregisterClient(host.UserID)
	reg.finalizeReconnectTimeout(host.UserID)
	hostChanged := findMessage(t, joinerSender.messages, "host_changed")
	hostPayload := hostChanged.D.(map[string]string)
	if hostPayload["new_host_player_id"] != "join_user" {
		t.Fatalf("new host = %q, want join_user", hostPayload["new_host_player_id"])
	}
	promotedSnapshot := lastMessage(t, joinerSender.messages, "lobby_state").D.(Snapshot)
	if promotedSnapshot.HostUserID != "join_user" {
		t.Fatalf("snapshot host = %q, want join_user", promotedSnapshot.HostUserID)
	}
}

func TestRegistryHostCanSetEnvironmentAndResetReady(t *testing.T) {
	reg := NewRegistry()
	hostSender := &fakeSender{}
	joinerSender := &fakeSender{}
	host := &Client{UserID: "host_user", DisplayName: "host", Sender: hostSender}
	joiner := &Client{UserID: "join_user", DisplayName: "joiner", Sender: joinerSender}
	reg.RegisterClient(host)
	reg.RegisterClient(joiner)

	reg.Handle(context.Background(), host, "create_room", "create", mustJSON(t, map[string]any{
		"type":       TypeSkywardLobby,
		"name":       "Test Room",
		"visibility": VisibilityPublic,
		"level":      4,
		"capacity":   5,
	}))
	code := findMessage(t, hostSender.messages, "room_created").D.(map[string]any)["code"].(string)
	reg.Handle(context.Background(), joiner, "join_room", "join", mustJSON(t, map[string]string{"code": code}))
	reg.Handle(context.Background(), joiner, "set_ready", "ready", mustJSON(t, map[string]bool{"ready": true}))

	hostSender.messages = nil
	joinerSender.messages = nil
	reg.Handle(context.Background(), host, "set_environment", "env", mustJSON(t, map[string]string{"environment_id": "ice"}))

	ok := findMessage(t, hostSender.messages, "environment_ok")
	payload := ok.D.(map[string]string)
	if payload["environment_id"] != "ice" {
		t.Fatalf("environment_ok = %#v, want ice", payload)
	}
	snapshot := lastMessage(t, joinerSender.messages, "lobby_state").D.(Snapshot)
	if snapshot.EnvironmentID != "ice" {
		t.Fatalf("snapshot environment = %q, want ice", snapshot.EnvironmentID)
	}
	if len(snapshot.ReadySet) != 0 {
		t.Fatalf("ready_set = %#v, want empty after environment change", snapshot.ReadySet)
	}
}

func TestRegistryAvatarUpdateCachesAndBroadcastsToRoom(t *testing.T) {
	reg := NewRegistry()
	hostSender := &fakeSender{}
	joinerSender := &fakeSender{}
	host := &Client{UserID: "host_user", DisplayName: "host", Sender: hostSender}
	joiner := &Client{UserID: "join_user", DisplayName: "joiner", Sender: joinerSender}
	reg.RegisterClient(host)
	reg.RegisterClient(joiner)

	reg.Handle(context.Background(), host, "create_room", "create", mustJSON(t, map[string]any{
		"type":       TypeSkywardLobby,
		"name":       "Avatar Room",
		"visibility": VisibilityPrivate,
		"level":      1,
		"capacity":   5,
	}))
	code := findMessage(t, hostSender.messages, "room_created").D.(map[string]any)["code"].(string)
	reg.Handle(context.Background(), joiner, "join_room", "join", mustJSON(t, map[string]string{"code": code}))

	hostSender.messages = nil
	joinerSender.messages = nil
	avatar := avatars.Payload{
		Model: avatars.Model{ModelType: avatars.DefaultModelType, ModelColor: "Red"},
	}
	reg.SetAvatarForClient(context.Background(), joiner.UserID, avatar)

	update := findMessage(t, hostSender.messages, "avatar_updated")
	payload := update.D.(AvatarUpdatedPayload)
	if payload.UserID != joiner.UserID || payload.Model.ModelColor != "Red" {
		t.Fatalf("avatar_updated = %#v, want join_user Red", payload)
	}
	snapshot := lastMessage(t, hostSender.messages, "lobby_state").D.(Snapshot)
	if len(snapshot.Players) != 2 || snapshot.Players[1].Avatar.Model.ModelColor != "Red" {
		t.Fatalf("snapshot avatars = %#v, want joiner Red", snapshot.Players)
	}
	if optionalMessage(joinerSender.messages, "avatar_updated") == nil {
		t.Fatalf("updated player did not receive avatar_updated: %#v", joinerSender.messages)
	}
}

func TestRegistryReconnectReplaysLobbyAndMatchSnapshot(t *testing.T) {
	reg := NewRegistry()
	hostSender := &fakeSender{}
	joinerSender := &fakeSender{}
	host := &Client{UserID: "host_user", DisplayName: "host", Sender: hostSender}
	joiner := &Client{UserID: "join_user", DisplayName: "joiner", Sender: joinerSender}
	reg.RegisterClient(host)
	reg.RegisterClient(joiner)

	reg.Handle(context.Background(), host, "create_room", "create", mustJSON(t, map[string]any{
		"type":       TypeSkywardLobby,
		"name":       "Reconnect Room",
		"visibility": VisibilityPrivate,
		"level":      3,
		"capacity":   5,
	}))
	code := findMessage(t, hostSender.messages, "room_created").D.(map[string]any)["code"].(string)
	reg.Handle(context.Background(), joiner, "join_room", "join", mustJSON(t, map[string]string{"code": code}))
	reg.Handle(context.Background(), joiner, "set_ready", "ready", mustJSON(t, map[string]bool{"ready": true}))
	reg.Handle(context.Background(), host, "start_match", "start", mustJSON(t, map[string]any{}))
	reg.Handle(context.Background(), host, "orb_collected", "", mustJSON(t, map[string]string{"orb_id": "orb:1"}))

	hostSender.messages = nil
	joinerSender.messages = nil
	reg.UnregisterClient(joiner.UserID)
	disconnectedSnapshot := lastMessage(t, hostSender.messages, "lobby_state").D.(Snapshot)
	if disconnectedSnapshot.Players[1].Connected {
		t.Fatalf("joiner connected = true after disconnect, want false")
	}
	if optionalMessage(hostSender.messages, "peer_left") != nil {
		t.Fatalf("peer_left sent during reconnect grace: %#v", hostSender.messages)
	}

	rejoinSender := &fakeSender{}
	rejoiner := &Client{UserID: "join_user", DisplayName: "joiner", Sender: rejoinSender}
	reg.RegisterClient(rejoiner)
	reg.ReplaySession(context.Background(), rejoiner.UserID)

	rejoined := findMessage(t, rejoinSender.messages, "session_rejoined")
	if rejoined.D.(SessionRejoinedPayload).State != StateInMatch {
		t.Fatalf("session_rejoined = %#v, want in_match", rejoined.D)
	}
	matchSnapshot := findMessage(t, rejoinSender.messages, "match_snapshot").D.(MatchSnapshotPayload)
	if matchSnapshot.Seed == 0 || matchSnapshot.YourPlayerID != "join_user" {
		t.Fatalf("match snapshot = %#v, want seed and join_user id", matchSnapshot)
	}
	if len(matchSnapshot.CollectedOrbs) != 1 || matchSnapshot.CollectedOrbs[0] != "orb:1" {
		t.Fatalf("collected_orbs = %#v, want orb:1", matchSnapshot.CollectedOrbs)
	}
}

func TestRegistryRegularRoomCapsCapacityAtFive(t *testing.T) {
	reg := NewRegistry()
	hostSender := &fakeSender{}
	host := &Client{UserID: "host_user", DisplayName: "host", Sender: hostSender}
	reg.RegisterClient(host)

	reg.Handle(context.Background(), host, "create_room", "create", mustJSON(t, map[string]any{
		"type":       TypeSkywardLobby,
		"name":       "Oversized Room",
		"visibility": VisibilityPrivate,
		"level":      1,
		"capacity":   MaxLargeRoomCapacity,
	}))

	created := findMessage(t, hostSender.messages, "room_created")
	snapshot := created.D.(map[string]any)["snapshot"].(Snapshot)
	if snapshot.Capacity != DefaultCapacity {
		t.Fatalf("capacity = %d, want regular room cap %d", snapshot.Capacity, DefaultCapacity)
	}
}

func TestRegistryRejectsInvalidEnvironmentChanges(t *testing.T) {
	reg := NewRegistry()
	hostSender := &fakeSender{}
	joinerSender := &fakeSender{}
	host := &Client{UserID: "host_user", DisplayName: "host", Sender: hostSender}
	joiner := &Client{UserID: "join_user", DisplayName: "joiner", Sender: joinerSender}
	reg.RegisterClient(host)
	reg.RegisterClient(joiner)

	reg.Handle(context.Background(), host, "create_room", "create", mustJSON(t, map[string]any{
		"type":       TypeSkywardLobby,
		"name":       "Test Room",
		"visibility": VisibilityPrivate,
		"level":      4,
		"capacity":   5,
	}))
	code := findMessage(t, hostSender.messages, "room_created").D.(map[string]any)["code"].(string)
	reg.Handle(context.Background(), joiner, "join_room", "join", mustJSON(t, map[string]string{"code": code}))

	reg.Handle(context.Background(), joiner, "set_environment", "non-host", mustJSON(t, map[string]string{"environment_id": "ice"}))
	nonHostErr := lastMessage(t, joinerSender.messages, "err").D.(map[string]string)
	if nonHostErr["code"] != "forbidden" {
		t.Fatalf("non-host err = %#v, want forbidden", nonHostErr)
	}

	reg.Handle(context.Background(), host, "set_environment", "unknown", mustJSON(t, map[string]string{"environment_id": "lava"}))
	unknownErr := lastMessage(t, hostSender.messages, "err").D.(map[string]string)
	if unknownErr["code"] != "unknown_environment" {
		t.Fatalf("unknown err = %#v, want unknown_environment", unknownErr)
	}
}

func TestRegistryMatchStateRelayOrbAndCleanup(t *testing.T) {
	reg := NewRegistry()
	hostSender := &fakeSender{}
	joinerSender := &fakeSender{}
	host := &Client{UserID: "host_user", DisplayName: "host", Sender: hostSender}
	joiner := &Client{UserID: "join_user", DisplayName: "joiner", Sender: joinerSender}
	reg.RegisterClient(host)
	reg.RegisterClient(joiner)

	reg.Handle(context.Background(), host, "create_room", "create", mustJSON(t, map[string]any{
		"type":       TypeSkywardLobby,
		"name":       "Test Room",
		"visibility": VisibilityPrivate,
		"level":      4,
		"capacity":   5,
	}))
	code := findMessage(t, hostSender.messages, "room_created").D.(map[string]any)["code"].(string)
	reg.Handle(context.Background(), joiner, "join_room", "join", mustJSON(t, map[string]string{"code": code}))
	reg.Handle(context.Background(), joiner, "set_ready", "ready", mustJSON(t, map[string]bool{"ready": true}))
	reg.Handle(context.Background(), host, "start_match", "start", mustJSON(t, map[string]any{}))

	hostSender.messages = nil
	joinerSender.messages = nil
	reg.Handle(context.Background(), joiner, "player_state", "", mustJSON(t, map[string]any{
		"tick":     7,
		"x":        120.5,
		"y":        340.0,
		"vx":       20.0,
		"vy":       -5.0,
		"grounded": false,
		"facing":   -1,
	}))

	relay := findMessage(t, hostSender.messages, "peer_state_update")
	state := relay.D.(MatchPlayerState)
	if state.UserID != "join_user" || state.Tick != 7 || state.Facing != -1 {
		t.Fatalf("relay state = %#v, want join_user tick 7 facing -1", state)
	}
	if optionalMessage(joinerSender.messages, "peer_state_update") != nil {
		t.Fatalf("sender received its own peer_state_update: %#v", joinerSender.messages)
	}

	reg.Handle(context.Background(), joiner, "orb_collected", "", mustJSON(t, map[string]string{"orb_id": "orb:2"}))
	collected := findMessage(t, hostSender.messages, "orb_collected")
	orbPayload := collected.D.(OrbCollectedPayload)
	if orbPayload.OrbID != "orb:2" || orbPayload.UserID != "join_user" {
		t.Fatalf("orb payload = %#v, want orb:2 by join_user", orbPayload)
	}

	reg.UnregisterClient(joiner.UserID)
	reg.finalizeReconnectTimeout(joiner.UserID)
	left := findMessage(t, hostSender.messages, "peer_left")
	leftPayload := left.D.(map[string]string)
	if leftPayload["user_id"] != "join_user" {
		t.Fatalf("peer_left = %#v, want join_user", leftPayload)
	}
}

func TestRegistryMatchFinishBroadcastsResults(t *testing.T) {
	reg := NewRegistry()
	hostSender := &fakeSender{}
	host := &Client{UserID: "host_user", DisplayName: "host", Sender: hostSender}
	reg.RegisterClient(host)

	reg.Handle(context.Background(), host, "create_room", "create", mustJSON(t, map[string]any{
		"type":       TypeSkywardLobby,
		"name":       "Solo Test",
		"visibility": VisibilityPrivate,
		"level":      1,
		"capacity":   5,
	}))
	reg.Handle(context.Background(), host, "start_match", "start", mustJSON(t, map[string]any{}))

	hostSender.messages = nil
	reg.Handle(context.Background(), host, "player_state", "", mustJSON(t, map[string]any{
		"tick":     2,
		"x":        160.0,
		"y":        10.0,
		"vx":       0.0,
		"vy":       0.0,
		"grounded": true,
		"facing":   1,
	}))

	results := findMessage(t, hostSender.messages, "match_results")
	payload := results.D.(MatchResultsPayload)
	if !payload.Final {
		t.Fatalf("final = false, want true for solo finish")
	}
	if len(payload.Placements) != 1 {
		t.Fatalf("placements = %#v, want one winner", payload.Placements)
	}
	winner := payload.Placements[0]
	if winner.UserID != "host_user" || winner.Place != 1 || winner.Result != "finished" {
		t.Fatalf("winner = %#v, want host_user place 1 finished", winner)
	}
}

func TestRegistryMatchResultsWaitForAllPlayersAndRematch(t *testing.T) {
	reg := NewRegistry()
	hostSender := &fakeSender{}
	joinerSender := &fakeSender{}
	host := &Client{UserID: "host_user", DisplayName: "host", Sender: hostSender}
	joiner := &Client{UserID: "join_user", DisplayName: "joiner", Sender: joinerSender}
	reg.RegisterClient(host)
	reg.RegisterClient(joiner)

	reg.Handle(context.Background(), host, "create_room", "create", mustJSON(t, map[string]any{
		"type":       TypeSkywardLobby,
		"name":       "Two Player",
		"visibility": VisibilityPrivate,
		"level":      1,
		"capacity":   5,
	}))
	code := findMessage(t, hostSender.messages, "room_created").D.(map[string]any)["code"].(string)
	reg.Handle(context.Background(), joiner, "join_room", "join", mustJSON(t, map[string]string{"code": code}))
	reg.Handle(context.Background(), joiner, "set_ready", "ready", mustJSON(t, map[string]bool{"ready": true}))
	reg.Handle(context.Background(), host, "start_match", "start", mustJSON(t, map[string]any{}))

	hostSender.messages = nil
	joinerSender.messages = nil
	reg.Handle(context.Background(), host, "player_state", "", mustJSON(t, map[string]any{
		"tick":     1,
		"x":        160.0,
		"y":        10.0,
		"vx":       0.0,
		"vy":       0.0,
		"grounded": true,
		"facing":   1,
	}))
	partial := findMessage(t, joinerSender.messages, "match_results").D.(MatchResultsPayload)
	if partial.Final {
		t.Fatalf("partial final = true, want false until every player is placed")
	}
	if len(partial.Placements) != 1 || partial.Placements[0].UserID != "host_user" {
		t.Fatalf("partial placements = %#v, want host only", partial.Placements)
	}

	reg.Handle(context.Background(), joiner, "player_eliminated", "elim", mustJSON(t, map[string]string{"reason": "fell"}))
	final := lastMessage(t, hostSender.messages, "match_results").D.(MatchResultsPayload)
	if !final.Final {
		t.Fatalf("final = false, want true after all players placed")
	}
	if len(final.Placements) != 2 || final.Placements[1].Result != "eliminated" {
		t.Fatalf("final placements = %#v, want joiner eliminated second", final.Placements)
	}

	reg.Handle(context.Background(), host, "request_rematch", "rematch", mustJSON(t, map[string]any{}))
	rematch := findMessage(t, hostSender.messages, "rematch_ok")
	snapshot := rematch.D.(map[string]any)["snapshot"].(Snapshot)
	if snapshot.State != StateWaiting || len(snapshot.ReadySet) != 0 {
		t.Fatalf("rematch snapshot = %#v, want waiting with no ready players", snapshot)
	}
}

func mustJSON(t *testing.T, v any) json.RawMessage {
	t.Helper()
	b, err := json.Marshal(v)
	if err != nil {
		t.Fatalf("marshal payload: %v", err)
	}
	return b
}

func findMessage(t *testing.T, messages []sentEnvelope, msgType string) sentEnvelope {
	t.Helper()
	for _, msg := range messages {
		if msg.T == msgType {
			return msg
		}
	}
	t.Fatalf("message %q not found in %#v", msgType, messages)
	return sentEnvelope{}
}

func lastMessage(t *testing.T, messages []sentEnvelope, msgType string) sentEnvelope {
	t.Helper()
	for i := len(messages) - 1; i >= 0; i-- {
		if messages[i].T == msgType {
			return messages[i]
		}
	}
	t.Fatalf("message %q not found in %#v", msgType, messages)
	return sentEnvelope{}
}

func optionalMessage(messages []sentEnvelope, msgType string) *sentEnvelope {
	for _, msg := range messages {
		if msg.T == msgType {
			return &msg
		}
	}
	return nil
}
