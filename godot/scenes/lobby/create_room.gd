extends Control

## Create-room form.
##
## Reads name (LineEdit), level (SpinBox 1-10), and visibility (CheckButton —
## checked = Public, unchecked = Private; per vault [[Open Questions]] private
## is the default at create time), then sends `create_room`. On success,
## populates Session with the returned lobby snapshot and replaces into the
## lobby scene (`replace` so BACK from the lobby returns to the browser, not
## here).

const LOBBY_SCENE: PackedScene = preload("res://scenes/lobby/skyward_lobby.tscn")

var _busy := false

func _ready() -> void:
	%CreateButton.pressed.connect(_on_create_pressed)
	%VisibilityToggle.toggled.connect(_on_visibility_toggled)
	# Default name suggests something the user can keep or override.
	%NameField.placeholder_text = _default_room_name()
	_on_visibility_toggled(%VisibilityToggle.button_pressed)

func _on_visibility_toggled(public: bool) -> void:
	%VisibilityToggle.text = "Public" if public else "Private"

func _on_create_pressed() -> void:
	if _busy:
		return
	if not NetworkBackend.is_control_connected():
		_set_status("Not connected to server")
		return

	var name := (%NameField.text as String).strip_edges()
	if name.is_empty():
		name = _default_room_name()
	if name.length() > 32:
		name = name.substr(0, 32)
	var visibility := "public" if %VisibilityToggle.button_pressed else "private"
	var level := int(%LevelSpinBox.value)

	_set_busy(true, "Creating %s room..." % visibility)
	var result := await NetworkBackend.send_control_request("create_room", {
		"type": "skyward_lobby",
		"name": name,
		"visibility": visibility,
		"level": level,
		"environment_id": "default",
		"capacity": 8,
	})
	if not result.success:
		_set_busy(false, _error_message(result.error, "Could not create room"))
		return

	var data: Dictionary = result.data if result.data is Dictionary else {}
	var snapshot: Dictionary = data.get("snapshot", {}) if data.get("snapshot") is Dictionary else {}
	Session.set_lobby_snapshot(snapshot)
	_set_busy(false, "")
	SceneManager.replace(LOBBY_SCENE)

func _default_room_name() -> String:
	if Session.display_name.is_empty():
		return "Skyward Room"
	return "%s's room" % Session.display_name

func _set_busy(busy: bool, status: String) -> void:
	_busy = busy
	%CreateButton.disabled = busy
	%NameField.editable = not busy
	%LevelSpinBox.editable = not busy
	%VisibilityToggle.disabled = busy
	_set_status(status)

func _set_status(status: String) -> void:
	%StatusLabel.text = status

func _error_message(err: Dictionary, fallback: String) -> String:
	return String(err.get("message", fallback))
