extends Control

## Main menu screen.
##
## Main entry screen using the exported 320x180 menu art. Play opens the
## profile/mode selection screen; settings and exit keep their direct actions.

const SETTINGS_SCENE := "res://scenes/main_menu/settings.tscn"
const PLAY_OPTIONS_SCENE := "res://scenes/main_menu/play_options.tscn"

const HELP_PAGES: Array[String] = [
	"Reach the top before the other players.\n\nMove with A/D or Left/Right.\nJump with Space, W, or Up.",
	"Collect orbs while climbing for extra score.\n\nWatch for hazards and special platforms in each environment.",
	"Multiplayer rooms support up to 5 players in the regular mode.\n\nReady up in the lobby, then race when the host starts the match."
]

var _help_page_index: int = 0

func _ready() -> void:
	# Main menu is the root of the navigation tree — clear any stale history
	# (e.g. if we landed back here via SceneManager.go_to after a deep flow).
	SceneManager.clear_history()
	%PlayButton.pressed.connect(_on_play_pressed)
	%ExitButton.pressed.connect(_on_exit_pressed)
	%SettingsButton.pressed.connect(_on_settings_pressed)
	%HelpButton.pressed.connect(_on_help_pressed)
	%HelpPrevButton.pressed.connect(_on_help_prev_pressed)
	%HelpNextButton.pressed.connect(_on_help_next_pressed)
	%HelpCloseButton.pressed.connect(_on_help_close_pressed)
	_update_help_page()

func _on_play_pressed() -> void:
	SceneManager.go_to(PLAY_OPTIONS_SCENE)

func _on_exit_pressed() -> void:
	SceneManager.quit()

func _on_settings_pressed() -> void:
	SceneManager.go_to(SETTINGS_SCENE)

func _on_help_pressed() -> void:
	_help_page_index = 0
	_update_help_page()
	%HelpDialog.visible = true

func _on_help_prev_pressed() -> void:
	_help_page_index = maxi(_help_page_index - 1, 0)
	_update_help_page()

func _on_help_next_pressed() -> void:
	_help_page_index = mini(_help_page_index + 1, HELP_PAGES.size() - 1)
	_update_help_page()

func _on_help_close_pressed() -> void:
	%HelpDialog.visible = false

func _update_help_page() -> void:
	%HelpBody.text = HELP_PAGES[_help_page_index]
	%HelpPageLabel.text = "%d / %d" % [_help_page_index + 1, HELP_PAGES.size()]
	%HelpPrevButton.disabled = _help_page_index == 0
	%HelpNextButton.disabled = _help_page_index == HELP_PAGES.size() - 1
