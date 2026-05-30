extends Control

## Join-by-code form — placeholder.
##
## Phase 2 delivers the real 6-char input (auto-uppercase, charset-restricted
## per `Networking - Room Model.md`) and the join_room WS message.

const LOBBY_SCENE := "res://scenes/lobby/skyward_lobby.tscn"

var _busy := false

func _ready() -> void:
	%JoinButton.pressed.connect(_on_join_pressed)
	%CodeField.text_submitted.connect(_on_code_submitted)
	%CodeField.text_changed.connect(_on_code_changed)
	%CodeField.grab_focus()

func _on_code_submitted(_text: String) -> void:
	_on_join_pressed()

func _on_code_changed(text: String) -> void:
	var normalized := _normalize_code(text)
	if normalized != text:
		var caret: int = %CodeField.caret_column
		%CodeField.text = normalized
		%CodeField.caret_column = min(caret, normalized.length())

func _on_join_pressed() -> void:
	if _busy:
		return
	var code := _normalize_code(%CodeField.text)
	if code.length() != 6:
		$PhaseNote.text = "Enter a 6-character code"
		return
	if not NetworkBackend.is_control_connected():
		$PhaseNote.text = "Not connected to server"
		return

	_set_busy(true, "Joining...")
	var result := await NetworkBackend.send_control_request("join_room", {"code": code})
	if not result.success:
		_set_busy(false, _join_error(result))
		return

	var data: Dictionary = result.data if result.data is Dictionary else {}
	var snapshot: Dictionary = data.get("snapshot", {}) if data.get("snapshot") is Dictionary else {}
	Session.set_lobby_snapshot(snapshot)
	_set_busy(false, "")
	SceneManager.replace(LOBBY_SCENE)

func _normalize_code(code: String) -> String:
	var allowed := "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
	var out := ""
	var upper := code.to_upper()
	for i in range(upper.length()):
		var ch := upper.substr(i, 1)
		if allowed.contains(ch):
			out += ch
		if out.length() == 6:
			break
	return out

func _set_busy(busy: bool, status: String) -> void:
	_busy = busy
	%JoinButton.disabled = busy
	%CodeField.editable = not busy
	$PhaseNote.text = status

func _join_error(result: Dictionary) -> String:
	var envelope: Dictionary = result.get("envelope", {}) if result.get("envelope") is Dictionary else {}
	var data: Dictionary = envelope.get("d", {}) if envelope.get("d") is Dictionary else {}
	var reason := String(data.get("reason", ""))
	match reason:
		"not_found":
			return "Room not found"
		"full":
			return "Room is full"
		"in_progress":
			return "Room already started"
		"bad_request":
			return "Invalid room code"
	var err: Dictionary = result.get("error", {}) if result.get("error") is Dictionary else {}
	return String(err.get("message", "Could not join room"))
