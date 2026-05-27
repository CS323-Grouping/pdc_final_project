extends Control

const LOBBY_SCENE: PackedScene = preload("res://scenes/lobby/skyward_lobby.tscn")
const ROOM_BROWSER_SCENE := "res://scenes/lobby/room_browser.tscn"

var _busy := false

func _ready() -> void:
	%RematchButton.pressed.connect(_on_rematch_pressed)
	%LobbyButton.pressed.connect(_on_lobby_pressed)
	%RoomsButton.pressed.connect(_on_rooms_pressed)
	if not NetworkBackend.control_message.is_connected(_on_control_message):
		NetworkBackend.control_message.connect(_on_control_message)
	_render()

func _exit_tree() -> void:
	if NetworkBackend.control_message.is_connected(_on_control_message):
		NetworkBackend.control_message.disconnect(_on_control_message)

func _on_control_message(envelope: Dictionary) -> void:
	if String(envelope.get("t", "")) != "lobby_state":
		return
	var snapshot: Dictionary = envelope.get("d", {}) if envelope.get("d") is Dictionary else {}
	Session.set_lobby_snapshot(snapshot)
	Session.match_results = {}
	SceneManager.replace(LOBBY_SCENE)

func _render() -> void:
	var results: Dictionary = Session.match_results
	var placements: Array = results.get("placements", []) if results.get("placements") is Array else []
	%TitleLabel.text = "MATCH RESULTS"
	%SubtitleLabel.text = "Room %s" % (Session.current_room_code if not Session.current_room_code.is_empty() else "------")

	var rows := [%Row1, %Row2, %Row3, %Row4, %Row5]
	for i in range(rows.size()):
		rows[i].text = "%d. --" % (i + 1)

	for i in range(min(placements.size(), rows.size())):
		var row: Label = rows[i]
		var placement: Dictionary = placements[i] if placements[i] is Dictionary else {}
		var display_name := String(placement.get("display_name", placement.get("user_id", "Player")))
		var result := String(placement.get("result", "finished")).capitalize()
		row.text = "%d. %s  %s" % [i + 1, display_name.substr(0, 14), result]

	var host_id := String(Session.current_room_snapshot.get("host_user_id", ""))
	var is_host := host_id == Session.user_id
	%RematchButton.disabled = not is_host or not NetworkBackend.is_control_connected()
	%StatusLabel.text = "Host can start a rematch" if is_host else "Waiting for host"

func _on_rematch_pressed() -> void:
	if _busy:
		return
	_busy = true
	%RematchButton.disabled = true
	%StatusLabel.text = "Requesting rematch..."
	var result := await NetworkBackend.send_control_request("request_rematch", {})
	_busy = false
	if not result.success:
		%StatusLabel.text = String(result.error.get("message", "Could not request rematch"))
		_render()
		return
	var data: Dictionary = result.data if result.data is Dictionary else {}
	var snapshot: Dictionary = data.get("snapshot", {}) if data.get("snapshot") is Dictionary else {}
	if not snapshot.is_empty():
		Session.set_lobby_snapshot(snapshot)
	Session.match_results = {}
	SceneManager.replace(LOBBY_SCENE)

func _on_lobby_pressed() -> void:
	Session.match_results = {}
	SceneManager.replace(LOBBY_SCENE)

func _on_rooms_pressed() -> void:
	Session.clear_room()
	SceneManager.replace(ROOM_BROWSER_SCENE)
