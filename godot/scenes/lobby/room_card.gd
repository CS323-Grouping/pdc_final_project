extends Panel

## Single row in the public-room browser list. Instanced dynamically by
## room_browser.gd from each entry in a `room_list_update` payload.
##
## Emits `pressed(code)` on left click or `ui_accept` (Enter/Space) when the
## card has focus. Browser handles the actual join_room flow.

signal pressed(code: String)

var room_code: String = ""

func _ready() -> void:
	# Focusable + clickable. Set in code as well as the tscn so dynamically
	# instanced cards still work even if the scene file's defaults drift.
	focus_mode = Control.FOCUS_ALL
	mouse_filter = Control.MOUSE_FILTER_STOP
	gui_input.connect(_on_gui_input)

## Populate from one entry of `room_list_update.rooms`.
func set_room(data: Dictionary) -> void:
	room_code = String(data.get("code", ""))
	var raw_name := String(data.get("name", ""))
	var display_name := raw_name if raw_name.length() <= 18 else raw_name.substr(0, 17) + "…"
	var players := int(data.get("players", 0))
	var capacity := int(data.get("capacity", 8))
	var level := int(data.get("level", 1))
	var env := String(data.get("environment_id", "default"))
	%CardLabel.text = "%s    %s    %d/%d  L%d  %s" % [
		display_name,
		room_code,
		players,
		capacity,
		level,
		env,
	]

func _on_gui_input(event: InputEvent) -> void:
	var activate := false
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		activate = true
	elif event.is_action_pressed("ui_accept"):
		activate = true
	if activate and not room_code.is_empty():
		pressed.emit(room_code)
