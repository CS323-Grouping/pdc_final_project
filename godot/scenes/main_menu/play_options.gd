extends Control

const AVATAR_EDITOR_SCENE: PackedScene = preload("res://scenes/avatar/avatar_editor.tscn")
const MATCH_SCENE: PackedScene = preload("res://scenes/match/match.tscn")
const ROOM_BROWSER_SCENE: PackedScene = preload("res://scenes/lobby/room_browser.tscn")

func _ready() -> void:
	%ProfileNameLabel.text = Session.display_name if not Session.display_name.is_empty() else "Guest"
	%ProfileEmailLabel.text = Session.email if not Session.email.is_empty() else "Local profile"
	%AvatarButton.pressed.connect(_on_avatar_pressed)
	%SingleplayerButton.pressed.connect(_on_singleplayer_pressed)
	%MultiplayerButton.pressed.connect(_on_multiplayer_pressed)

func _on_avatar_pressed() -> void:
	SceneManager.go_to(AVATAR_EDITOR_SCENE)

func _on_singleplayer_pressed() -> void:
	_start_endless_mode()

func _on_multiplayer_pressed() -> void:
	SceneManager.go_to(ROOM_BROWSER_SCENE)

func _start_endless_mode() -> void:
	Session.match_params = {
		"environment_id": "sky",
		"level": 1,
		"mode": "endless",
		"seed": int(Time.get_ticks_msec()),
		"your_player_id": Session.user_id,
	}
	SceneManager.go_to(MATCH_SCENE)
