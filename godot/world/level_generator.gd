class_name LevelGenerator extends RefCounted

## Deterministic procedural tower generator.
##
## Pure function: same (env, difficulty, seed) always produces byte-identical
## LevelData on every machine — that's the contract that lets us ship only
## (env_id, difficulty, seed) on the wire and have every client regenerate the
## same geometry. Verified by the GUT determinism test.
##
## Topology is band-based: divide the tower into horizontal bands of
## BAND_HEIGHT each, scatter platforms in each band, sprinkle the occasional
## orb. The number of platforms per band thins out at higher difficulty
## (longer jumps required).
##
## Phase 4c adds hazards, mechanisms, and env-exclusive platform variants.
## Concrete element choice still flows through the env's element_set pool.
##
## DETERMINISM RULES (non-negotiable):
##   - All randomness goes through the seeded `rng`. No `randi()`,
##     `Time.get_ticks_msec()`, or other global RNG.
##   - No floating-point math whose ordering depends on map iteration order.
##   - The slot list order is deterministic (bottom-to-top band, then
##     positions in deterministic order).

const INTERNAL_WIDTH := 320
const BAND_HEIGHT := 50
const PLATFORM_WIDTH := 50
const SPAWN_PADDING := 30   # px at bottom reserved for spawn
const GOAL_PADDING := 30    # px at top reserved for goal
const ORB_CHANCE := 0.35
const BASE_HAZARD_CHANCE := 0.12
const BASE_MECHANISM_CHANCE := 0.10

static func generate(env: LevelEnvironment, difficulty: int, seed: int) -> LevelData:
	var rng := RandomNumberGenerator.new()
	rng.seed = seed

	var data := LevelData.new()
	data.env_id = env.id
	data.difficulty = clampi(difficulty, 1, 10)
	data.seed = seed
	data.total_height = 500 + (data.difficulty - 1) * 100   # 500..1400

	var usable_height := data.total_height - SPAWN_PADDING - GOAL_PADDING
	var band_count: int = maxi(1, usable_height / BAND_HEIGHT)

	var slots: Array[SlotInfo] = []

	# Bottom-to-top band iteration. Band 0 is just above the spawn area.
	for band_index in band_count:
		var band_top_y := data.total_height - SPAWN_PADDING - (band_index + 1) * BAND_HEIGHT
		var platform_count := _platforms_per_band(rng, data.difficulty)
		var xs := _platform_x_positions(rng, platform_count)
		for x in xs:
			var slot := SlotInfo.new()
			slot.position = Vector2i(x, band_top_y + 20)   # platform sits mid-band
			slot.category = Element.Category.PLATFORM
			slot.chosen_element_id = _pick_element(env, Element.Category.PLATFORM, rng, data.difficulty)
			slot.instance_seed = rng.randi()
			if slot.chosen_element_id != StringName(""):
				slots.append(slot)

		# Optional orb floating above one of this band's platforms.
		if rng.randf() < ORB_CHANCE and not xs.is_empty():
			var orb_x := xs[rng.randi_range(0, xs.size() - 1)] + PLATFORM_WIDTH / 2
			var orb_slot := SlotInfo.new()
			orb_slot.position = Vector2i(orb_x, band_top_y + 6)
			orb_slot.category = Element.Category.PICKUP
			orb_slot.chosen_element_id = _pick_element(env, Element.Category.PICKUP, rng, data.difficulty)
			orb_slot.instance_seed = rng.randi()
			if orb_slot.chosen_element_id != StringName(""):
				slots.append(orb_slot)

		# Optional gameplay modifiers. These stay data-driven: the env's
		# element_set decides which concrete hazard/mechanism is available.
		if not xs.is_empty() and rng.randf() < _hazard_chance(data.difficulty):
			var hazard_slot := _make_side_slot(env, Element.Category.HAZARD, rng, data.difficulty, xs, band_top_y)
			if hazard_slot.chosen_element_id != StringName(""):
				slots.append(hazard_slot)

		if not xs.is_empty() and rng.randf() < _mechanism_chance(data.difficulty):
			var mechanism_slot := _make_side_slot(env, Element.Category.MECHANISM, rng, data.difficulty, xs, band_top_y)
			if mechanism_slot.chosen_element_id != StringName(""):
				slots.append(mechanism_slot)

	data.slots = slots
	return data

# Higher difficulty → fewer platforms per band → longer jumps.
static func _platforms_per_band(rng: RandomNumberGenerator, difficulty: int) -> int:
	var roll := rng.randf()
	if difficulty <= 3:
		return 3 if roll > 0.4 else 2
	if difficulty <= 6:
		return 2 if roll > 0.4 else 1
	return 1 if roll > 0.3 else 2

# Spread `count` platforms across the playfield with deterministic jitter so
# they don't all line up at the same x positions every band.
static func _platform_x_positions(rng: RandomNumberGenerator, count: int) -> Array[int]:
	var out: Array[int] = []
	var margin := 10
	var usable := INTERNAL_WIDTH - 2 * margin - PLATFORM_WIDTH
	if count <= 0:
		return out
	if count == 1:
		var jitter := rng.randi_range(0, usable)
		out.append(margin + jitter)
		return out
	# count >= 2: divide usable width into `count` slots with jitter inside each.
	var slot_w := usable / count
	for i in count:
		var base := margin + i * slot_w
		var jitter := rng.randi_range(0, maxi(1, slot_w - 1))
		out.append(base + jitter)
	return out

static func _hazard_chance(difficulty: int) -> float:
	return clampf(BASE_HAZARD_CHANCE + float(difficulty - 1) * 0.035, 0.0, 0.42)

static func _mechanism_chance(difficulty: int) -> float:
	return clampf(BASE_MECHANISM_CHANCE + float(difficulty - 1) * 0.015, 0.0, 0.24)

static func _make_side_slot(
	env: LevelEnvironment,
	category: Element.Category,
	rng: RandomNumberGenerator,
	difficulty: int,
	xs: Array[int],
	band_top_y: int
) -> SlotInfo:
	var slot := SlotInfo.new()
	var platform_x := xs[rng.randi_range(0, xs.size() - 1)]
	var center_x := platform_x + PLATFORM_WIDTH / 2
	slot.category = category
	slot.chosen_element_id = _pick_element(env, category, rng, difficulty)
	slot.instance_seed = rng.randi()
	slot.position = Vector2i(center_x, band_top_y + 10)
	if slot.chosen_element_id == &"icicle_drop":
		slot.position = Vector2i(center_x, band_top_y - 10)
	return slot

# Weighted pick from the env's element_set, filtered by category + difficulty.
# Returns StringName("") if no element matches — caller skips the slot.
static func _pick_element(env: LevelEnvironment, category: Element.Category, rng: RandomNumberGenerator, difficulty: int) -> StringName:
	var candidate_ids: Array[StringName] = []
	var candidate_weights: Array[float] = []
	var total_weight := 0.0
	for entry in env.element_set:
		if entry == null or entry.element == null:
			continue
		var element := entry.element
		if element.category != category:
			continue
		if difficulty < element.min_difficulty or difficulty > element.max_difficulty:
			continue
		var weight := entry.weight_override if entry.weight_override > 0.0 else element.base_weight
		if weight <= 0.0:
			continue
		candidate_ids.append(element.id)
		candidate_weights.append(weight)
		total_weight += weight
	if candidate_ids.is_empty():
		return StringName("")
	var pick := rng.randf() * total_weight
	var running := 0.0
	for i in candidate_ids.size():
		running += candidate_weights[i]
		if pick <= running:
			return candidate_ids[i]
	return candidate_ids[candidate_ids.size() - 1]
