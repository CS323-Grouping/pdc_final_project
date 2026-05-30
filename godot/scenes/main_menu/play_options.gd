extends Control

const AVATAR_EDITOR_SCENE := "res://scenes/avatar/avatar_editor.tscn"
const AVATAR_PORTRAIT_SCRIPT := preload("res://scenes/avatar/avatar_portrait.gd")
const MATCH_SCENE := "res://scenes/match/match.tscn"
const ROOM_BROWSER_SCENE := "res://scenes/lobby/room_browser.tscn"

var _portrait

func _ready() -> void:
	%ProfileNameLabel.text = Session.display_name if not Session.display_name.is_empty() else "Guest"
	%ProfileEmailLabel.text = Session.email if not Session.email.is_empty() else "Local profile"
	_build_avatar_preview()
	%AvatarButton.pressed.connect(_on_avatar_pressed)
	%SingleplayerButton.pressed.connect(_on_singleplayer_pressed)
	%MultiplayerButton.pressed.connect(_on_multiplayer_pressed)

func _build_avatar_preview() -> void:
	var label := $AvatarPanel/AvatarPreview/AvatarLabel
	if label != null:
		label.visible = false
	_portrait = AVATAR_PORTRAIT_SCRIPT.new()
	_portrait.user_id = Session.user_id
	_portrait.position = Vector2(5, 4)
	_portrait.size = Vector2(40, 42)
	$AvatarPanel/AvatarPreview.add_child(_portrait)

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
