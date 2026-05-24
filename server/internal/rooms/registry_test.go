package rooms

import (
	"context"
	"encoding/json"
	"testing"
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
		"capacity":   8,
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
