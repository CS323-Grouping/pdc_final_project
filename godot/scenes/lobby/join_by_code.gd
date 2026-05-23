extends Control

## Join-by-code form — placeholder.
##
## Phase 2 delivers the real 6-char input (auto-uppercase, charset-restricted
## per `Networking - Room Model.md`) and the join_room WS message.

const LOBBY_SCENE: PackedScene = preload("res://scenes/lobby/skyward_lobby.tscn")

func _ready() -> void:
	%JoinButton.pressed.connect(_on_join_pressed)

func _on_join_pressed() -> void:
	# Placeholder: jump straight to the lobby. Phase 2 sends join_room and
	# waits for join_ok | join_err. `replace` so BACK from lobby doesn't
	# return here.
	SceneManager.replace(LOBBY_SCENE)
