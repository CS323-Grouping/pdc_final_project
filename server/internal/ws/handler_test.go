package ws_test

import (
	"context"
	"encoding/json"
	"errors"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"

	"github.com/coder/websocket"

	"github.com/CS-StudentGroup/pdc_final_project/server/internal/auth"
	"github.com/CS-StudentGroup/pdc_final_project/server/internal/httpx"
	"github.com/CS-StudentGroup/pdc_final_project/server/internal/ws"
)

func TestHandlerThroughHTTPXMiddlewareSendsHello(t *testing.T) {
	secret := []byte("test-secret")
	token, _, err := auth.MintAccessToken(secret, "user_123", "kurt")
	if err != nil {
		t.Fatalf("mint token: %v", err)
	}

	handler := httpx.Chain(
		ws.New(secret, "test-version"),
		httpx.RequestID,
		httpx.AccessLog,
		httpx.Recover,
	)
	srv := httptest.NewServer(handler)
	defer srv.Close()

	wsURL := "ws" + strings.TrimPrefix(srv.URL, "http") + "/ws?token=" + url.QueryEscape(token)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	conn, _, err := websocket.Dial(ctx, wsURL, nil)
	if err != nil {
		t.Fatalf("dial websocket: %v", err)
	}
	defer conn.Close(websocket.StatusNormalClosure, "")

	typ, data, err := conn.Read(ctx)
	if err != nil {
		t.Fatalf("read hello: %v", err)
	}
	if typ != websocket.MessageText {
		t.Fatalf("message type = %v, want %v", typ, websocket.MessageText)
	}

	var got struct {
		T string `json:"t"`
		D struct {
			ServerVersion   string `json:"server_version"`
			YourUserID      string `json:"your_user_id"`
			YourDisplayName string `json:"your_display_name"`
		} `json:"d"`
	}
	if err := json.Unmarshal(data, &got); err != nil {
		t.Fatalf("decode hello: %v", err)
	}
	if got.T != "hello" {
		t.Fatalf("message type = %q, want hello", got.T)
	}
	if got.D.ServerVersion != "test-version" {
		t.Fatalf("server_version = %q, want test-version", got.D.ServerVersion)
	}
	if got.D.YourUserID != "user_123" {
		t.Fatalf("your_user_id = %q, want user_123", got.D.YourUserID)
	}
	if got.D.YourDisplayName != "kurt" {
		t.Fatalf("your_display_name = %q, want kurt", got.D.YourDisplayName)
	}
}

func TestHandlerRejectsDuplicateActiveSession(t *testing.T) {
	secret := []byte("test-secret")
	token, _, err := auth.MintAccessToken(secret, "user_123", "kurt")
	if err != nil {
		t.Fatalf("mint token: %v", err)
	}

	handler := httpx.Chain(
		ws.New(secret, "test-version"),
		httpx.RequestID,
		httpx.AccessLog,
		httpx.Recover,
	)
	srv := httptest.NewServer(handler)
	defer srv.Close()

	wsURL := "ws" + strings.TrimPrefix(srv.URL, "http") + "/ws?token=" + url.QueryEscape(token)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	first, _, err := websocket.Dial(ctx, wsURL, nil)
	if err != nil {
		t.Fatalf("dial first websocket: %v", err)
	}
	defer first.Close(websocket.StatusNormalClosure, "")
	if _, _, err := first.Read(ctx); err != nil {
		t.Fatalf("read first hello: %v", err)
	}

	second, _, err := websocket.Dial(ctx, wsURL, nil)
	if err != nil {
		t.Fatalf("dial second websocket: %v", err)
	}
	defer second.Close(websocket.StatusNormalClosure, "")

	_, _, err = second.Read(ctx)
	if websocket.CloseStatus(err) != websocket.StatusPolicyViolation {
		t.Fatalf("second read close status = %v, want %v (err=%v)", websocket.CloseStatus(err), websocket.StatusPolicyViolation, err)
	}
	var closeErr websocket.CloseError
	if !errors.As(err, &closeErr) {
		t.Fatalf("second read err = %T, want websocket.CloseError", err)
	}
	if closeErr.Reason != "account_already_connected" {
		t.Fatalf("close reason = %q, want account_already_connected", closeErr.Reason)
	}
}
