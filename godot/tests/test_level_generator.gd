extends GutTest

## Determinism contract for LevelGenerator.
##
## The whole "ship only (env_id, difficulty, seed) on the wire" model depends on
## LevelGenerator.generate() being a pure function: same inputs -> byte-identical
## LevelData on every machine. If this test ever fails, multiplayer levels will
## desync (players standing on platforms that don't exist on someone else's
## screen). See docs/obsidian "Levels & Environments" -> Determinism rules.

const ENVS := {
	"sky": preload("res://resources/environments/sky.tres"),
	"ice": preload("res://resources/environments/ice.tres"),
	"default": preload("res://resources/environments/default.tres"),
}

func _assert_levels_identical(a: LevelData, b: LevelData, ctx: String) -> void:
	assert_eq(a.env_id, b.env_id, "%s: env_id" % ctx)
	assert_eq(a.difficulty, b.difficulty, "%s: difficulty" % ctx)
	assert_eq(a.seed, b.seed, "%s: seed" % ctx)
	assert_eq(a.total_height, b.total_height, "%s: total_height" % ctx)
	assert_eq(a.slots.size(), b.slots.size(), "%s: slot count" % ctx)
	if a.slots.size() != b.slots.size():
		return
	for i in a.slots.size():
		var sa := a.slots[i]
		var sb := b.slots[i]
		assert_eq(sa.position, sb.position, "%s: slot[%d].position" % [ctx, i])
		assert_eq(sa.category, sb.category, "%s: slot[%d].category" % [ctx, i])
		assert_eq(sa.chosen_element_id, sb.chosen_element_id, "%s: slot[%d].element" % [ctx, i])
		assert_eq(sa.instance_seed, sb.instance_seed, "%s: slot[%d].instance_seed" % [ctx, i])

# Same (env, difficulty, seed) must reproduce byte-identical LevelData, across
# every environment and the full 1-10 difficulty range.
func test_generate_is_deterministic_across_envs_and_difficulties() -> void:
	const SEED := 1234567
	for env_id in ENVS:
		var env: LevelEnvironment = ENVS[env_id]
		for difficulty in range(1, 11):
			var a := LevelGenerator.generate(env, difficulty, SEED)
			var b := LevelGenerator.generate(env, difficulty, SEED)
			_assert_levels_identical(a, b, "%s/diff=%d" % [env_id, difficulty])

# Re-running the same seed many times never drifts (guards against accidental
# use of a global RNG / wall clock inside generation).
func test_repeated_generation_does_not_drift() -> void:
	var env: LevelEnvironment = ENVS["ice"]
	var baseline := LevelGenerator.generate(env, 7, 42)
	for _i in 25:
		var again := LevelGenerator.generate(env, 7, 42)
		_assert_levels_identical(baseline, again, "ice/diff=7 repeat")

# Sanity: the generator is actually seed-sensitive, not emitting a constant
# level regardless of input. Different seeds should (overwhelmingly likely)
# differ somewhere.
func test_different_seeds_produce_different_levels() -> void:
	var env: LevelEnvironment = ENVS["sky"]
	var a := LevelGenerator.generate(env, 5, 1)
	var b := LevelGenerator.generate(env, 5, 999999)
	var differs := a.slots.size() != b.slots.size()
	if not differs:
		for i in a.slots.size():
			if a.slots[i].position != b.slots[i].position \
					or a.slots[i].chosen_element_id != b.slots[i].chosen_element_id:
				differs = true
				break
	assert_true(differs, "two different seeds produced identical levels")

# Difficulty is clamped to 1..10, so out-of-range inputs must still be
# deterministic and equal to their clamped counterpart.
func test_difficulty_is_clamped_and_stable() -> void:
	var env: LevelEnvironment = ENVS["sky"]
	_assert_levels_identical(
		LevelGenerator.generate(env, 0, 77),
		LevelGenerator.generate(env, 1, 77),
		"clamp low")
	_assert_levels_identical(
		LevelGenerator.generate(env, 99, 77),
		LevelGenerator.generate(env, 10, 77),
		"clamp high")
