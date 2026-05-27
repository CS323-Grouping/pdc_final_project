extends Node

## Discovers every `.tres` `LevelEnvironment` under `res://resources/environments/`
## at boot. Lobby UI and LevelPopulator query by `id`.
##
## Autoload name: `Environments` (short, reads well at call sites like
## `Environments.by_id(env_id)`).

const ENV_DIR := "res://resources/environments/"

var _by_id: Dictionary = {}   # StringName → LevelEnvironment

func _ready() -> void:
	_load_all()
	var ids: Array = _by_id.keys()
	print("[Environments] loaded %d env(s): %s" % [ids.size(), ids])

func _load_all() -> void:
	var dir := DirAccess.open(ENV_DIR)
	if dir == null:
		push_error("EnvironmentRegistry: cannot open %s" % ENV_DIR)
		return
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if not dir.current_is_dir() and name.ends_with(".tres"):
			var path := ENV_DIR + name
			var res := load(path) as LevelEnvironment
			if res != null:
				_by_id[res.id] = res
			else:
				push_warning("EnvironmentRegistry: %s is not a LevelEnvironment" % path)
		name = dir.get_next()

## Returns all loaded environments, sorted by id for stable UI order.
func all() -> Array[LevelEnvironment]:
	var out: Array[LevelEnvironment] = []
	for v in _by_id.values():
		var env := v as LevelEnvironment
		if env != null:
			out.append(env)
	out.sort_custom(func(a: LevelEnvironment, b: LevelEnvironment) -> bool: return String(a.id) < String(b.id))
	return out

## Environments shown in player-facing selectors. `default` remains loadable
## for compatibility, but Phase 4b presents Sky/Ice as the launch choices.
func playable() -> Array[LevelEnvironment]:
	var out: Array[LevelEnvironment] = []
	for env: LevelEnvironment in all():
		if env.id != &"default":
			out.append(env)
	if out.is_empty():
		return all()
	return out

func by_id(id: StringName) -> LevelEnvironment:
	return _by_id.get(id) as LevelEnvironment
