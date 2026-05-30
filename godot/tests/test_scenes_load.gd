extends GutTest

## Scene-load smoke test.
##
## Instantiates every screen / element scene and asserts it loads without error.
## This is the "every destination renders" check that the manual Phase 0
## walkthrough does, minus live pixels and network behavior: it catches the
## common breakage (renamed nodes, dangling preloads, missing/typo'd scripts,
## corrupted .tscn) that a headless load surfaces immediately.
##
## Note: this calls instantiate() but does NOT add the node to the scene tree,
## so _ready() does not run. That keeps the test free of live-network
## dependencies (room_browser/skyward_lobby talk to the server in _ready). The
## live login->menu->match flow is verified by the interactive run with the
## server up.

const SCREEN_SCENES := [
	"res://scenes/boot/login.tscn",
	"res://scenes/boot/register.tscn",
	"res://scenes/main_menu/main_menu.tscn",
	"res://scenes/main_menu/main_menu_background.tscn",
	"res://scenes/main_menu/play_options.tscn",
	"res://scenes/main_menu/settings.tscn",
	"res://scenes/lobby/room_browser.tscn",
	"res://scenes/lobby/room_card.tscn",
	"res://scenes/lobby/create_room.tscn",
	"res://scenes/lobby/join_by_code.tscn",
	"res://scenes/lobby/skyward_lobby.tscn",
	"res://scenes/match/match.tscn",
	"res://scenes/match/player.tscn",
	"res://scenes/results/match_results.tscn",
	"res://scenes/avatar/avatar_editor.tscn",
	"res://scenes/ui/back_button.tscn",
]

const ELEMENT_SCENES := [
	"res://scenes/elements/platforms/regular_platform.tscn",
	"res://scenes/elements/platforms/moving_platform.tscn",
	"res://scenes/elements/platforms/fragile_ice_platform.tscn",
	"res://scenes/elements/platforms/slippery_platform.tscn",
	"res://scenes/elements/hazards/spike_strip.tscn",
	"res://scenes/elements/hazards/icicle_drop.tscn",
	"res://scenes/elements/mechanisms/spring.tscn",
	"res://scenes/elements/pickups/orb.tscn",
]

func _assert_scene_instantiates(path: String) -> void:
	assert_true(ResourceLoader.exists(path), "scene missing: %s" % path)
	var packed := load(path) as PackedScene
	assert_not_null(packed, "failed to load PackedScene: %s" % path)
	if packed == null:
		return
	var inst := packed.instantiate()
	assert_not_null(inst, "instantiate() returned null: %s" % path)
	if inst != null:
		inst.free()

func test_all_screen_scenes_instantiate() -> void:
	for path in SCREEN_SCENES:
		_assert_scene_instantiates(path)

func test_all_element_scenes_instantiate_as_level_elements() -> void:
	# Element scene roots MUST extend LevelElement — the populator hard-casts to
	# it and skips anything that doesn't. A failure here would silently drop
	# pieces from generated levels.
	for path in ELEMENT_SCENES:
		assert_true(ResourceLoader.exists(path), "scene missing: %s" % path)
		var packed := load(path) as PackedScene
		assert_not_null(packed, "failed to load: %s" % path)
		if packed == null:
			continue
		var inst := packed.instantiate()
		assert_not_null(inst, "instantiate() returned null: %s" % path)
		if inst != null:
			assert_true(inst is LevelElement, "%s root does not extend LevelElement" % path)
			inst.free()
