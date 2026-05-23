extends Control

## Skyward Race lobby — placeholder.
##
## Phase 2 delivers the real lobby (player list synced from `lobby_state`,
## ready toggle, host controls for level + visibility + kick, countdown +
## start_match). For now: placeholder player rows + Ready/Start/Leave actions.
##
## "Leave" is a BackButton scene instance (custom text "LEAVE", same back-stack
## behavior as elsewhere).

func _ready() -> void:
	%ReadyButton.pressed.connect(_on_ready_pressed)
	%StartButton.pressed.connect(_on_start_pressed)

func _on_ready_pressed() -> void:
	print("[Lobby] READY pressed — set_ready WS message lands in Phase 2")

func _on_start_pressed() -> void:
	print("[Lobby] START pressed — start_match WS message + match scene transition land in Phase 4")
