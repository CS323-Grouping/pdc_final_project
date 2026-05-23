extends Control

## Main menu screen.
##
## Port of states/menu.py (pygame original). Layout uses the same 320×180
## logical coordinates as the pygame asset rects in MENU_ASSET_RECTS.
##
## Buttons navigate to placeholder destination scenes — those scenes are
## themselves placeholders until later phases flesh them out (see vault
## Roadmap.md).
##
## When sprites land, swap Panels for TextureRects (or NinePatchRects for the
## frames) and Buttons for TextureButtons without touching positions.

const SETTINGS_SCENE: PackedScene = preload("res://scenes/main_menu/settings.tscn")
const AVATAR_EDITOR_SCENE: PackedScene = preload("res://scenes/avatar/avatar_editor.tscn")
const ROOM_BROWSER_SCENE: PackedScene = preload("res://scenes/lobby/room_browser.tscn")

func _ready() -> void:
	# Main menu is the root of the navigation tree — clear any stale history
	# (e.g. if we landed back here via SceneManager.go_to after a deep flow).
	SceneManager.clear_history()
	# Show the authenticated user's display name once login wires it through
	# Session. Falls back to the placeholder if we somehow got here unauth'd.
	if Session.is_authenticated() and not Session.display_name.is_empty():
		%NameLabel.text = Session.display_name
	%PlayButton.pressed.connect(_on_play_pressed)
	%ExitButton.pressed.connect(_on_exit_pressed)
	%SettingsButton.pressed.connect(_on_settings_pressed)
	%AvatarButton.pressed.connect(_on_avatar_pressed)

func _on_play_pressed() -> void:
	SceneManager.go_to(ROOM_BROWSER_SCENE)

func _on_exit_pressed() -> void:
	SceneManager.quit()

func _on_settings_pressed() -> void:
	SceneManager.go_to(SETTINGS_SCENE)

func _on_avatar_pressed() -> void:
	SceneManager.go_to(AVATAR_EDITOR_SCENE)
