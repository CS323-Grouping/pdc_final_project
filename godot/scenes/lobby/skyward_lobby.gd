extends Control

## Skyward Race lobby — placeholder.
##
## Phase 2 delivers the real lobby (player list synced from `lobby_state`,
## ready toggle, host controls for level + visibility + kick, countdown +
## start_match). For now: placeholder player rows + Ready/Start/Leave actions.
##
## "Leave" is a BackButton scene instance (custom text "LEAVE", same back-stack
## behavior as elsewhere).

const ROOM_BROWSER_SCENE := "res://scenes/lobby/room_browser.tscn"
const MATCH_SCENE: PackedScene = preload("res://scenes/match/match.tscn")

var _snapshot: Dictionary = {}
var _busy := false

func _ready() -> void:
	%ReadyButton.pressed.connect(_on_ready_pressed)
	%StartButton.pressed.connect(_on_start_pressed)
	var back_callable := Callable($LeaveButton, "_on_pressed")
	if $LeaveButton.pressed.is_connected(back_callable):
		$LeaveButton.pressed.disconnect(back_callable)
	$LeaveButton.pressed.connect(_on_leave_pressed)
	Session.lobby_state_changed.connect(_on_lobby_state_changed)
	NetworkBackend.control_message.connect(_on_control_message)
	_apply_snapshot(Session.current_room_snapshot)

func _exit_tree() -> void:
	if Session.lobby_state_changed.is_connected(_on_lobby_state_changed):
		Session.lobby_state_changed.disconnect(_on_lobby_state_changed)
	if NetworkBackend.control_message.is_connected(_on_control_message):
		NetworkBackend.control_message.disconnect(_on_control_message)

func _on_lobby_state_changed(snapshot: Dictionary) -> void:
	_apply_snapshot(snapshot)

func _on_control_message(envelope: Dictionary) -> void:
	var msg_type := String(envelope.get("t", ""))
	if msg_type == "lobby_state":
		var snapshot: Dictionary = envelope.get("d", {}) if envelope.get("d") is Dictionary else {}
		Session.set_lobby_snapshot(snapshot)
	elif msg_type == "host_changed":
		print("[Lobby] host changed: %s" % envelope.get("d", {}))
	elif msg_type == "match_started":
		# Server pushes match_started to every player in the room (including
		# the host who triggered it). Each recipient gets a payload with
		# their own user_id under your_player_id, so all clients land here
		# nearly simultaneously and transition together.
		var payload: Dictionary = envelope.get("d", {}) if envelope.get("d") is Dictionary else {}
		Session.match_params = payload
		print("[Lobby] match_started — env=%s level=%s seed=%s" % [
			payload.get("environment_id"),
			payload.get("level"),
			payload.get("seed"),
		])
		SceneManager.replace(MATCH_SCENE)

func _on_ready_pressed() -> void:
	if _busy or Session.current_room_id.is_empty():
		return
	var ready := not _is_me_ready()
	_set_busy(true)
	var result := await NetworkBackend.send_control_request("set_ready", {"ready": ready})
	_set_busy(false)
	if not result.success:
		$PlayerList/PhaseNote.text = _error_message(result.error, "Could not update ready state")

func _on_start_pressed() -> void:
	if _busy or Session.current_room_id.is_empty():
		return
	if not NetworkBackend.is_control_connected():
		$PlayerList/PhaseNote.text = "Not connected to server"
		return
	# Only the host can start; non-hosts have the button disabled in
	# _apply_snapshot, but guard anyway in case state drifted.
	if String(_snapshot.get("host_user_id", "")) != Session.user_id:
		$PlayerList/PhaseNote.text = "Only the host can start"
		return
	_set_busy(true)
	var result := await NetworkBackend.send_control_request("start_match", {})
	_set_busy(false)
	if not result.success:
		# Scene transition happens via the match_started push (see
		# _on_control_message), not via the ok-reply, so on success there's
		# nothing more to do here.
		$PlayerList/PhaseNote.text = _error_message(result.error, "Could not start match")

func _on_leave_pressed() -> void:
	if _busy:
		return
	_set_busy(true)
	if NetworkBackend.is_control_connected() and not Session.current_room_id.is_empty():
		await NetworkBackend.send_control_request("leave_room", {})
	Session.clear_room()
	_set_busy(false)
	SceneManager.replace(ROOM_BROWSER_SCENE)

func _apply_snapshot(snapshot: Dictionary) -> void:
	_snapshot = snapshot
	var has_room := not String(snapshot.get("room_id", "")).is_empty()
	if not has_room:
		$Header.text = "LOBBY"
		$HostBadge.text = "host: --"
		$PlayerList/PhaseNote.text = "No server room joined"
		%ReadyButton.disabled = true
		%StartButton.disabled = true
		return

	$Header.text = "LOBBY: %s" % String(snapshot.get("code", "------"))
	$HostBadge.text = "host: %s" % _host_name(snapshot)
	$SettingsPanel/LevelRow.text = "Level: %d" % int(snapshot.get("level", 1))
	$SettingsPanel/VisibilityRow.text = String(snapshot.get("visibility", "private")).capitalize()
	$SettingsPanel/CountdownRow.text = "--"
	_render_players(snapshot.get("players", []))
	var player_count := 0
	if snapshot.get("players") is Array:
		player_count = (snapshot.get("players") as Array).size()
	$PlayerList/PhaseNote.text = "%d/%d players" % [player_count, int(snapshot.get("capacity", 8))]
	%ReadyButton.disabled = false
	%ReadyButton.text = "UNREADY" if _is_me_ready() else "READY"
	%StartButton.disabled = String(snapshot.get("host_user_id", "")) != Session.user_id

func _render_players(players_value: Variant) -> void:
	var rows := [$PlayerList/PlayerRow1, $PlayerList/PlayerRow2, $PlayerList/PlayerRow3, $PlayerList/PlayerRow4]
	for i in range(rows.size()):
		rows[i].text = "%d. (open slot)" % (i + 1)
	if not (players_value is Array):
		return
	var players: Array = players_value
	for i in range(min(players.size(), rows.size())):
		var player: Dictionary = players[i] if players[i] is Dictionary else {}
		var status := "HOST" if bool(player.get("is_host", false)) else ("READY" if bool(player.get("ready", false)) else "    ")
		rows[i].text = "%d. %s [%s]" % [
			i + 1,
			String(player.get("display_name", "player")).substr(0, 12).to_upper().rpad(12),
			status,
		]

func _host_name(snapshot: Dictionary) -> String:
	var host_id := String(snapshot.get("host_user_id", ""))
	var players: Array = snapshot.get("players", []) if snapshot.get("players") is Array else []
	for player_value in players:
		var player: Dictionary = player_value if player_value is Dictionary else {}
		if String(player.get("user_id", "")) == host_id:
			return String(player.get("display_name", "PLAYER")).to_upper()
	return "--"

func _is_me_ready() -> bool:
	var players: Array = _snapshot.get("players", []) if _snapshot.get("players") is Array else []
	for player_value in players:
		var player: Dictionary = player_value if player_value is Dictionary else {}
		if String(player.get("user_id", "")) == Session.user_id:
			return bool(player.get("ready", false))
	return false

func _set_busy(busy: bool) -> void:
	_busy = busy
	%ReadyButton.disabled = busy or Session.current_room_id.is_empty()
	$LeaveButton.disabled = busy

func _error_message(err: Dictionary, fallback: String) -> String:
	return String(err.get("message", fallback))
