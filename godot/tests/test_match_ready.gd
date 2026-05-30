extends GutTest

## Reproduction: does match.tscn survive _ready() when driven by a real
## match_started payload? The lobby->match transition silently fails in the
## live client (scene never swaps, no logged error), so this exercises the
## exact path the scene-load smoke test skips: adding the scene to the tree so
## _ready() actually runs, with the float-typed numbers JSON delivers
## (seed/level come across the wire as doubles).

const MATCH_SCENE := preload("res://scenes/match/match.tscn")

func _make_params() -> Dictionary:
	# Mirrors a real match_started 'd' payload as JSON.parse_string produces it:
	# every number is a float, including the crypto/rand int63 seed.
	return {
		"environment_id": "sky",
		"level": 5.0,
		"seed": 3972727331913960960.0,
		"start_at_server_ts": 1780022254000.0,
		"your_player_id": "01KSBVFSJYBRPPP6BQZPY5DKCR",
		"room_id": "room-abc",
	}

func test_match_scene_ready_runs_to_completion() -> void:
	Session.match_params = _make_params()
	Session.user_id = "01KSBVFSJYBRPPP6BQZPY5DKCR"
	var scene: Node = MATCH_SCENE.instantiate()
	add_child_autofree(scene)
	await wait_frames(3, "let _ready + a few _process frames run")
	assert_not_null(scene, "match scene instance went null")
	assert_true(is_instance_valid(scene), "match scene was freed during _ready/_process")
	# _data is set near the end of _ready; if _ready aborted early it stays null.
	assert_not_null(scene.get("_data"), "_ready did not finish: _data is null")
