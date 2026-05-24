extends Control

## Public room browser.
##
## Subscribes to `room_list_update` pushes from the server on _ready and
## renders one RoomCard per public room. Clicking (or `ui_accept` on a
## focused card) sends `join_room` and transitions to the lobby on success.
##
## CREATE → create_room scene. JOIN BY CODE → join_by_code scene. BACK → main
## menu (via the shared BackButton component).
##
## On _exit_tree we send `unsubscribe_room_list` so the server stops pushing
## updates to us once we leave the browser. Server also auto-unsubscribes on
## disconnect.

const CREATE_ROOM_SCENE: PackedScene = preload("res://scenes/lobby/create_room.tscn")
const JOIN_BY_CODE_SCENE: PackedScene = preload("res://scenes/lobby/join_by_code.tscn")
const LOBBY_SCENE: PackedScene = preload("res://scenes/lobby/skyward_lobby.tscn")
const ROOM_CARD_SCENE: PackedScene = preload("res://scenes/lobby/room_card.tscn")

var _busy: bool = false

func _ready() -> void:
	%CreateRoomButton.pressed.connect(_on_create_pressed)
	%JoinByCodeButton.pressed.connect(_on_join_pressed)
	NetworkBackend.control_message.connect(_on_control_message)
	_set_status("")
	_render_list([])

	if not NetworkBackend.is_control_connected():
		_set_status("Not connected to server")
		return

	var err := NetworkBackend.send_envelope({"t": "subscribe_room_list"})
	if err != OK:
		_set_status("Subscribe failed (%d)" % err)

func _exit_tree() -> void:
	if NetworkBackend.control_message.is_connected(_on_control_message):
		NetworkBackend.control_message.disconnect(_on_control_message)
	if NetworkBackend.is_control_connected():
		NetworkBackend.send_envelope({"t": "unsubscribe_room_list"})

func _on_control_message(envelope: Dictionary) -> void:
	if String(envelope.get("t", "")) != "room_list_update":
		return
	var data: Dictionary = envelope.get("d", {}) if envelope.get("d") is Dictionary else {}
	var rooms: Array = data.get("rooms", []) if data.get("rooms") is Array else []
	_render_list(rooms)

func _render_list(rooms: Array) -> void:
	for child in %ListBox.get_children():
		child.queue_free()
	if rooms.is_empty():
		%EmptyLabel.visible = true
		return
	%EmptyLabel.visible = false
	for room_value in rooms:
		if not (room_value is Dictionary):
			continue
		var card: Node = ROOM_CARD_SCENE.instantiate()
		%ListBox.add_child(card)
		card.set_room(room_value)
		card.pressed.connect(_on_card_pressed)

func _on_card_pressed(code: String) -> void:
	if _busy or code.is_empty():
		return
	if not NetworkBackend.is_control_connected():
		_set_status("Not connected to server")
		return
	_busy = true
	_set_status("Joining %s..." % code)
	var result := await NetworkBackend.send_control_request("join_room", {"code": code})
	_busy = false
	if not result.success:
		_set_status(_join_error_message(result))
		return
	var data: Dictionary = result.data if result.data is Dictionary else {}
	var snapshot: Dictionary = data.get("snapshot", {}) if data.get("snapshot") is Dictionary else {}
	Session.set_lobby_snapshot(snapshot)
	_set_status("")
	SceneManager.replace(LOBBY_SCENE)

func _on_create_pressed() -> void:
	SceneManager.go_to(CREATE_ROOM_SCENE)

func _on_join_pressed() -> void:
	SceneManager.go_to(JOIN_BY_CODE_SCENE)

func _set_status(status: String) -> void:
	%StatusLabel.text = status

func _join_error_message(result: Dictionary) -> String:
	# join_err comes back with d={reason: ...} on the envelope; the generic
	# error envelope has d={code, message}. Try the reason first since the
	# user-facing message is short, then fall back to the generic message.
	var envelope: Dictionary = result.get("envelope", {}) if result.get("envelope") is Dictionary else {}
	var data: Dictionary = envelope.get("d", {}) if envelope.get("d") is Dictionary else {}
	var reason := String(data.get("reason", ""))
	match reason:
		"not_found":
			return "Room no longer exists"
		"full":
			return "Room is full"
		"in_progress":
			return "Room already started"
		"bad_request":
			return "Invalid request"
	var err: Dictionary = result.get("error", {}) if result.get("error") is Dictionary else {}
	return String(err.get("message", "Could not join room"))
