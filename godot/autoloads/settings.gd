extends Node

## Persistent local user settings + window-level concerns.
##
## Saved to `user://settings.cfg`. Loaded on engine boot via _ready().
## Anything ephemeral (JWT, current room) belongs in `Session`, not here.
##
## Also owns the global `toggle_fullscreen` input action handler and the
## minimum window size — pixel-art convention: never let the user shrink below
## the internal resolution (320×180).

const SETTINGS_PATH := "user://settings.cfg"
const INTERNAL_WIDTH := 320
const INTERNAL_HEIGHT := 180

var fullscreen: bool = false
var control_scheme: String = "wasd"  # "wasd" | "arrows"
var show_performance_metrics: bool = false
var master_volume: float = 1.0

signal changed

func _ready() -> void:
	# Prevent shrinking the window below the design resolution — keeps the pixel
	# art legible and avoids degenerate layouts. See vault: Skyward Race - Port Plan.md.
	DisplayServer.window_set_min_size(Vector2i(INTERNAL_WIDTH, INTERNAL_HEIGHT))
	load_settings()

func _unhandled_input(event: InputEvent) -> void:
	# Action declared in project.godot [input] section; bound to F11 + Alt+Enter.
	# Configurable later from a Settings UI (Phase 8) without touching this code.
	if event.is_action_pressed("toggle_fullscreen"):
		toggle_fullscreen()
		get_viewport().set_input_as_handled()

func toggle_fullscreen() -> void:
	fullscreen = not fullscreen
	apply_runtime_settings()
	save_settings()

func load_settings() -> void:
	var cfg := ConfigFile.new()
	if cfg.load(SETTINGS_PATH) != OK:
		# First run or missing file — keep defaults silently.
		return
	fullscreen = cfg.get_value("display", "fullscreen", fullscreen)
	control_scheme = cfg.get_value("controls", "scheme", control_scheme)
	show_performance_metrics = cfg.get_value("debug", "perf_overlay", show_performance_metrics)
	master_volume = cfg.get_value("audio", "master_volume", master_volume)
	apply_runtime_settings()

func save_settings() -> void:
	var cfg := ConfigFile.new()
	cfg.set_value("display", "fullscreen", fullscreen)
	cfg.set_value("controls", "scheme", control_scheme)
	cfg.set_value("debug", "perf_overlay", show_performance_metrics)
	cfg.set_value("audio", "master_volume", master_volume)
	var err: Error = cfg.save(SETTINGS_PATH)
	if err != OK:
		push_error("Settings: failed to save (err %d)" % err)
	changed.emit()

func apply_runtime_settings() -> void:
	if fullscreen:
		DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_FULLSCREEN)
	else:
		DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_WINDOWED)
