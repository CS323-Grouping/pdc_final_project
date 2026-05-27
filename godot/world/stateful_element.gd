class_name StatefulElement extends LevelElement

## Base for level elements with mutable match-time state.
##
## Phase 4c keeps the behavior local/deterministic because the current match
## transport is the raw control WebSocket. The state surface is explicit so the
## later server-owned sync pass can replicate this payload without rewriting
## every element script.

signal state_changed(network_id: String, state: Dictionary)

var state: Dictionary = {}

func set_state_value(key: StringName, value: Variant) -> void:
	if state.get(key) == value:
		return
	state[key] = value
	state_changed.emit(network_id, state.duplicate(true))

func get_state_value(key: StringName, fallback: Variant = null) -> Variant:
	return state.get(key, fallback)
