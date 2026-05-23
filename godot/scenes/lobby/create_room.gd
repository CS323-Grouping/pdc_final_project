extends Control

## Create-room form — placeholder.
##
## Phase 2 delivers the real form (room name input, level dropdown,
## public/private toggle, max-players slider, environment selector) and the
## create_room WS message.

const LOBBY_SCENE: PackedScene = preload("res://scenes/lobby/skyward_lobby.tscn")

func _ready() -> void:
	%CreateButton.pressed.connect(_on_create_pressed)

func _on_create_pressed() -> void:
	# Placeholder: jump straight to the lobby. Phase 2 will send create_room,
	# wait for room_created, then transition. `replace` so BACK from lobby
	# doesn't return here.
	SceneManager.replace(LOBBY_SCENE)
