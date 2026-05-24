class_name LevelPopulator extends Node

## Turns LevelData into live scene nodes parented under the caller's parent.
##
## Pure orchestration: looks up each slot's element in the env's element_set,
## instantiates the element's scene, casts to LevelElement (parse-time
## typed — no Python-style hasattr), positions it, hands it the slot's
## instance_seed, parents it.
##
## Returns the number of elements actually added (skips on missing element or
## type mismatch). Errors are logged via push_error.

func populate(data: LevelData, parent: Node) -> int:
	var env: LevelEnvironment = Environments.by_id(data.env_id)
	if env == null:
		push_error("LevelPopulator: env %s not in EnvironmentRegistry" % data.env_id)
		return 0

	# Build a fast id → Element lookup from the env's element_set.
	var element_lookup: Dictionary = {}
	for entry in env.element_set:
		if entry != null and entry.element != null:
			element_lookup[entry.element.id] = entry.element

	var added := 0
	for slot in data.slots:
		var element := element_lookup.get(slot.chosen_element_id) as Element
		if element == null or element.scene == null:
			push_warning("LevelPopulator: missing element/scene for %s" % slot.chosen_element_id)
			continue
		var instance := element.scene.instantiate() as LevelElement
		if instance == null:
			push_error("LevelPopulator: element %s scene root does not extend LevelElement" % slot.chosen_element_id)
			continue
		instance.position = Vector2(slot.position.x, slot.position.y)
		instance.init_with_seed(slot.instance_seed)
		parent.add_child(instance)
		added += 1
	return added
