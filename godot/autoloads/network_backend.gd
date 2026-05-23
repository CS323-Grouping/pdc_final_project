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

signal control_connected
signal control_disconnected
signal control_message(envelope: Dictionary)
signal hello_received(payload: Dictionary)

var control_socket: WebSocketPeer
var hello_payload: Dictionary = {}
var last_error_message: String = ""
var last_close_code: int = 0
var last_close_reason: String = ""

var _hello_seen: bool = false
var _last_state: int = -1

func is_control_connected() -> bool:
	return control_socket != null and control_socket.get_ready_state() == WebSocketPeer.STATE_OPEN

func has_received_hello() -> bool:
	return _hello_seen

## Opens the control WS and awaits the server's hello frame. Returns true on
## success, false on connect error / disconnect / timeout. Caller is responsible
## for surfacing the failure (e.g. login scene shows an error).
func connect_to_server(jwt: String) -> bool:
	if control_socket != null:
		disconnect_from_server()
	_clear_last_error()
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

	# Poll-await loop. _process drives socket I/O; we yield each frame and
	# check for the three exit conditions (hello / disconnect / timeout).
	var deadline := Time.get_ticks_msec() + int(HELLO_TIMEOUT_SEC * 1000.0)
	while control_socket != null:
		if _hello_seen:
			return true
		var state := control_socket.get_ready_state()
		if state == WebSocketPeer.STATE_CLOSED:
			_capture_close_state()
			push_warning("NetworkBackend: socket closed before hello")
			control_socket = null
			return false
		if Time.get_ticks_msec() > deadline:
			last_error_message = "timed out waiting for server hello"
			push_warning("NetworkBackend: timeout waiting for hello")
			disconnect_from_server()
			return false
		await get_tree().process_frame
	return false

func disconnect_from_server() -> void:
	if control_socket != null:
		control_socket.close()
		control_socket = null
	_hello_seen = false
	hello_payload = {}
	control_disconnected.emit()

## Send a JSON envelope. Returns an Error; ERR_UNAVAILABLE if not connected.
func send_envelope(envelope: Dictionary) -> Error:
	if not is_control_connected():
		return ERR_UNAVAILABLE
	var text := JSON.stringify(envelope)
	return control_socket.send_text(text)

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
				control_disconnected.emit()
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
		print("[NetworkBackend] recv %s" % msg_type)
		control_message.emit(envelope)
		if msg_type == "hello":
			hello_payload = envelope.get("d", {}) if envelope.get("d") is Dictionary else {}
			_hello_seen = true
			hello_received.emit(hello_payload)

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
