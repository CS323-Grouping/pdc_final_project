extends Node

## Control WebSocket connection to the Go backend.
##
## Phase 1.3 implementation: opens a plain WebSocketPeer to /ws?token=<jwt>,
## awaits the server's "hello" envelope, then keeps the connection alive for
## future control messages (room lifecycle, lobby browser updates, etc.).
##
## NOT the MultiplayerPeer for gameplay HLM — that's a separate
## WebSocketMultiplayerPeer instance opened in Phase 4 when matches start.
## See vault: Networking - Overview.md.
##
## Wire format (matches server/internal/ws/handler.go):
##   {"t": "<msg_type>", "id": "<opt correlation>", "d": { <payload> }}

const SERVER_WS_URL := "ws://localhost:8080/ws"
const HELLO_TIMEOUT_SEC := 10.0
const REQUEST_TIMEOUT_SEC := 10.0
const RECONNECT_DELAYS_SEC := [1.0, 2.0, 5.0, 10.0, 10.0]
const LOG_HIGH_FREQUENCY_MESSAGES := false
const HIGH_FREQUENCY_MESSAGE_TYPES := {
	"peer_state_update": true,
}

signal control_connected
signal control_disconnected
signal control_message(envelope: Dictionary)
signal hello_received(payload: Dictionary)
signal reconnecting(attempt: int, delay_sec: float)
signal reconnect_succeeded
signal reconnect_failed

var control_socket: WebSocketPeer
var hello_payload: Dictionary = {}
var last_error_message: String = ""
var last_close_code: int = 0
var last_close_reason: String = ""

var _hello_seen: bool = false
var _last_state: int = -1
var _next_request_id: int = 0
var _pending_replies: Dictionary = {}
var _auto_reconnect_enabled := false
var _reconnect_loop_running := false
var _awaiting_hello := false
var _status_layer: CanvasLayer
var _status_label: Label
var _status_hide_generation := 0

func _ready() -> void:
	_ensure_status_layer()

func is_control_connected() -> bool:
	return control_socket != null and control_socket.get_ready_state() == WebSocketPeer.STATE_OPEN

func has_received_hello() -> bool:
	return _hello_seen

## Opens the control WS and awaits the server's hello frame. Returns true on
## success, false on connect error / disconnect / timeout. Caller is responsible
## for surfacing the failure (e.g. login scene shows an error).
func connect_to_server(jwt: String) -> bool:
	_auto_reconnect_enabled = true
	_reconnect_loop_running = false
	var ok := await _open_socket(jwt)
	if ok:
		_hide_connection_status()
	return ok

func _open_socket(jwt: String) -> bool:
	if control_socket != null:
		control_socket.close()
		control_socket = null
	_clear_last_error()
	_pending_replies.clear()
	var url := SERVER_WS_URL + "?token=" + jwt.uri_encode()
	control_socket = WebSocketPeer.new()
	var err := control_socket.connect_to_url(url)
	if err != OK:
		last_error_message = "could not start websocket connection"
		push_error("NetworkBackend: connect_to_url failed (%d)" % err)
		control_socket = null
		return false

	_hello_seen = false
	hello_payload = {}
	_last_state = -1
	_awaiting_hello = true

	# Poll-await loop. _process drives socket I/O; we yield each frame and
	# check for the three exit conditions (hello / disconnect / timeout).
	var deadline := Time.get_ticks_msec() + int(HELLO_TIMEOUT_SEC * 1000.0)
	while control_socket != null:
		if _hello_seen:
			_awaiting_hello = false
			return true
		var state := control_socket.get_ready_state()
		if state == WebSocketPeer.STATE_CLOSED:
			_capture_close_state()
			push_warning("NetworkBackend: socket closed before hello")
			control_socket = null
			_hello_seen = false
			hello_payload = {}
			_awaiting_hello = false
			return false
		if Time.get_ticks_msec() > deadline:
			last_error_message = "timed out waiting for server hello"
			push_warning("NetworkBackend: timeout waiting for hello")
			if control_socket != null:
				control_socket.close()
			control_socket = null
			_hello_seen = false
			hello_payload = {}
			_awaiting_hello = false
			return false
		await get_tree().process_frame
	_awaiting_hello = false
	return false

func disconnect_from_server() -> void:
	_auto_reconnect_enabled = false
	_reconnect_loop_running = false
	if control_socket != null:
		control_socket.close()
		control_socket = null
	_hello_seen = false
	hello_payload = {}
	_pending_replies.clear()
	_hide_connection_status()
	control_disconnected.emit()

## Send a JSON envelope. Returns an Error; ERR_UNAVAILABLE if not connected.
func send_envelope(envelope: Dictionary) -> Error:
	if not is_control_connected():
		return ERR_UNAVAILABLE
	var text := JSON.stringify(envelope)
	return control_socket.send_text(text)

## Send a typed control request and wait for the matching reply id.
## Returns:
##   {success=true, data=<payload>, envelope=<full reply>}
##   {success=false, error={code,message}, envelope?=<full reply>}
func send_control_request(msg_type: String, payload: Dictionary = {}, timeout_sec: float = REQUEST_TIMEOUT_SEC) -> Dictionary:
	if not is_control_connected():
		return _request_error("not_connected", "control socket is not connected")

	var request_id := _make_request_id()
	var err := send_envelope({
		"t": msg_type,
		"id": request_id,
		"d": payload,
	})
	if err != OK:
		return _request_error("send_failed", "could not send control request (%d)" % err)

	var deadline := Time.get_ticks_msec() + int(timeout_sec * 1000.0)
	while Time.get_ticks_msec() <= deadline:
		if _pending_replies.has(request_id):
			var reply: Dictionary = _pending_replies[request_id]
			_pending_replies.erase(request_id)
			var reply_type := String(reply.get("t", ""))
			if reply_type == "err" or reply_type.ends_with("_err"):
				var err_payload: Dictionary = reply.get("d", {}) if reply.get("d") is Dictionary else {}
				return {"success": false, "error": err_payload, "envelope": reply}
			return {
				"success": true,
				"data": reply.get("d", {}),
				"envelope": reply,
			}
		if not is_control_connected():
			_pending_replies.erase(request_id)
			return _request_error("disconnected", "control socket disconnected before reply")
		await get_tree().process_frame

	_pending_replies.erase(request_id)
	return _request_error("timeout", "timed out waiting for %s reply" % msg_type)

func _process(_delta: float) -> void:
	if control_socket == null:
		return

	control_socket.poll()
	var state := control_socket.get_ready_state()
	if state != _last_state:
		_last_state = state
		match state:
			WebSocketPeer.STATE_OPEN:
				print("[NetworkBackend] control socket open")
				control_connected.emit()
			WebSocketPeer.STATE_CLOSED:
				_capture_close_state()
				print("[NetworkBackend] control socket closed (code=%d reason=%s)" % [last_close_code, last_close_reason])
				control_socket = null
				_hello_seen = false
				hello_payload = {}
				_pending_replies.clear()
				control_disconnected.emit()
				if not _awaiting_hello and _should_auto_reconnect():
					_start_reconnect_loop()
				return

	while control_socket != null and control_socket.get_available_packet_count() > 0:
		var pkt := control_socket.get_packet()
		var text := pkt.get_string_from_utf8()
		var parsed: Variant = JSON.parse_string(text)
		if not (parsed is Dictionary):
			push_warning("NetworkBackend: non-dict frame ignored: %s" % text)
			continue
		var envelope: Dictionary = parsed
		var msg_type: String = String(envelope.get("t", ""))
		if _should_log_message(msg_type):
			print("[NetworkBackend] recv %s" % msg_type)
		_apply_global_message_state(msg_type, envelope)
		control_message.emit(envelope)
		if envelope.has("id"):
			_pending_replies[String(envelope.get("id"))] = envelope
		if msg_type == "hello":
			hello_payload = envelope.get("d", {}) if envelope.get("d") is Dictionary else {}
			_hello_seen = true
			AvatarCache.apply_hello_payload(hello_payload)
			hello_received.emit(hello_payload)

func _apply_global_message_state(msg_type: String, envelope: Dictionary) -> void:
	var payload: Dictionary = envelope.get("d", {}) if envelope.get("d") is Dictionary else {}
	if msg_type == "lobby_state":
		Session.set_lobby_snapshot(payload)
	elif msg_type == "session_rejoined" and payload.get("snapshot") is Dictionary:
		Session.set_lobby_snapshot(payload.get("snapshot"))
	elif msg_type == "avatar_updated":
		var user_id := String(payload.get("user_id", ""))
		if not user_id.is_empty():
			AvatarCache.set_avatar(user_id, payload)

func _clear_last_error() -> void:
	last_error_message = ""
	last_close_code = 0
	last_close_reason = ""

func _capture_close_state() -> void:
	if control_socket == null:
		return
	last_close_code = control_socket.get_close_code()
	last_close_reason = control_socket.get_close_reason()
	if last_close_reason == "account_already_connected":
		last_error_message = "account already logged in on another game instance"
	elif not last_close_reason.is_empty():
		last_error_message = last_close_reason
	elif last_close_code != 0:
		last_error_message = "server closed connection (code %d)" % last_close_code

func _should_auto_reconnect() -> bool:
	if not _auto_reconnect_enabled or Session.jwt.is_empty():
		return false
	if last_close_reason == "account_already_connected" or last_close_reason == "server_shutdown":
		return false
	return true

func _start_reconnect_loop() -> void:
	if _reconnect_loop_running:
		return
	_reconnect_loop_running = true
	call_deferred("_run_reconnect_loop")

func _run_reconnect_loop() -> void:
	for i in range(RECONNECT_DELAYS_SEC.size()):
		if not _auto_reconnect_enabled or Session.jwt.is_empty():
			break
		var delay_sec: float = RECONNECT_DELAYS_SEC[i]
		reconnecting.emit(i + 1, delay_sec)
		_show_connection_status("Connection lost. Reconnecting in %.0fs..." % delay_sec)
		await get_tree().create_timer(delay_sec).timeout
		if not _auto_reconnect_enabled or Session.jwt.is_empty():
			break
		_show_connection_status("Reconnecting... %d/%d" % [i + 1, RECONNECT_DELAYS_SEC.size()])
		var ok := await _open_socket(Session.jwt)
		if ok:
			_reconnect_loop_running = false
			reconnect_succeeded.emit()
			_show_connection_status("Reconnected.", 1.5)
			return
	_reconnect_loop_running = false
	if _auto_reconnect_enabled:
		_auto_reconnect_enabled = false
		reconnect_failed.emit()
		_show_connection_status("Connection lost. Please log in again.")

func _ensure_status_layer() -> void:
	if _status_layer != null:
		return
	_status_layer = CanvasLayer.new()
	_status_layer.layer = 100
	add_child(_status_layer)
	var panel := Panel.new()
	panel.name = "ReconnectToast"
	panel.position = Vector2(54, 6)
	panel.size = Vector2(212, 18)
	panel.visible = false
	_status_layer.add_child(panel)
	_status_label = Label.new()
	_status_label.theme_type_variation = &"BodyTiny"
	_status_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_status_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_status_label.position = Vector2(4, 2)
	_status_label.size = Vector2(204, 14)
	panel.add_child(_status_label)

func _show_connection_status(text: String, hide_after_sec: float = 0.0) -> void:
	_ensure_status_layer()
	var panel := _status_label.get_parent() as Control
	panel.visible = true
	_status_label.text = text
	_status_hide_generation += 1
	if hide_after_sec > 0.0:
		var generation := _status_hide_generation
		await get_tree().create_timer(hide_after_sec).timeout
		if generation == _status_hide_generation:
			panel.visible = false

func _hide_connection_status() -> void:
	if _status_label == null:
		return
	_status_hide_generation += 1
	var panel := _status_label.get_parent() as Control
	panel.visible = false

func _should_log_message(msg_type: String) -> bool:
	if LOG_HIGH_FREQUENCY_MESSAGES:
		return true
	return not HIGH_FREQUENCY_MESSAGE_TYPES.has(msg_type)

func _make_request_id() -> String:
	_next_request_id += 1
	return "%d-%d" % [Time.get_ticks_msec(), _next_request_id]

func _request_error(code: String, message: String) -> Dictionary:
	return {
		"success": false,
		"error": {
			"code": code,
			"message": message,
		},
	}
