extends Node2D

## Match scene — Phase 4a.3.
##
## Phase 4a.1: generator + populator running standalone (F6).
## Phase 4a.2: server `match_started` populates `Session.match_params` and
##             every client transitions here together with the same seed.
## Phase 4a.3 (this revision): spawns a MatchPlayer, adds a floor under the
##             generated level, camera now follows the player. Solo gameplay
##             works — multi-player position sync is Phase 4a.4.
##
## ESC returns to the previous scene (SceneManager handles ui_cancel
## globally; this scene doesn't need its own handler).

const DEFAULT_ENV_ID := &"default"
const DEFAULT_DIFFICULTY := 1
const DEFAULT_SEED := 42
const CAMERA_FOLLOW_LERP := 0.15
const CAMERA_PLAYER_OFFSET_Y := -30.0   # camera centered slightly above player
const PLAYER_SCENE: PackedScene = preload("res://scenes/match/player.tscn")

# @onready typed accessors so property reads/writes don't go through Variant.
@onready var _camera: Camera2D = %Camera
@onready var _level_root: Node2D = %LevelRoot
@onready var _debug_label: Label = %DebugLabel

var _data: LevelData
var _env: LevelEnvironment
var _player: MatchPlayer

func _ready() -> void:
	var params: Dictionary = Session.match_params
	var env_id := StringName(String(params.get("environment_id", DEFAULT_ENV_ID)))
	var difficulty: int = int(params.get("level", DEFAULT_DIFFICULTY))
	var seed: int = int(params.get("seed", DEFAULT_SEED))

	_env = Environments.by_id(env_id)
	if _env == null:
		push_warning("Match: env %s not found, falling back to default" % env_id)
		_env = Environments.by_id(DEFAULT_ENV_ID)
	if _env == null:
		push_error("Match: even default env is missing — check resources/environments/")
		return

	_data = LevelGenerator.generate(_env, difficulty, seed)
	print("[Match] env=%s difficulty=%d seed=%d slots=%d height=%d" % [
		_data.env_id, _data.difficulty, _data.seed, _data.slots.size(), _data.total_height,
	])

	if _env.palette != null:
		RenderingServer.set_default_clear_color(_env.palette.background_color)

	var populator := LevelPopulator.new()
	add_child(populator)
	var added := populator.populate(_data, _level_root)

	_add_floor()
	_spawn_player()

	# Park camera on the player initially (subsequent frames lerp to follow).
	if _player != null:
		_camera.position = Vector2(160.0, _player.position.y + CAMERA_PLAYER_OFFSET_Y)

	_debug_label.text = "env=%s  diff=%d  seed=%d  slots=%d/%d  height=%d  (WASD+space, ESC back)" % [
		_data.env_id, _data.difficulty, _data.seed, added, _data.slots.size(), _data.total_height,
	]

func _process(_delta: float) -> void:
	if _player == null or _data == null:
		return
	var target_y := _player.position.y + CAMERA_PLAYER_OFFSET_Y
	target_y = clampf(target_y, 90.0, float(_data.total_height) - 90.0)
	var pos := _camera.position
	pos.x = 160.0
	pos.y = lerpf(pos.y, target_y, CAMERA_FOLLOW_LERP)
	_camera.position = pos

# Solid floor under the generated level so the player has something to land on
# at spawn time. Built in code so the level_root keeps its declarative
# "everything-comes-from-LevelData" property — the floor is a runtime concern,
# not part of the generated geometry.
func _add_floor() -> void:
	var body := StaticBody2D.new()
	body.position = Vector2(160.0, float(_data.total_height) + 5.0)
	var shape := CollisionShape2D.new()
	var rect := RectangleShape2D.new()
	rect.size = Vector2(320.0, 10.0)
	shape.shape = rect
	body.add_child(shape)
	_level_root.add_child(body)

func _spawn_player() -> void:
	_player = PLAYER_SCENE.instantiate() as MatchPlayer
	if _player == null:
		push_error("Match: PLAYER_SCENE root does not extend MatchPlayer")
		return
	# Spawn 25 px above the floor, horizontally centered in the playfield.
	_player.position = Vector2(160.0, float(_data.total_height) - 25.0)
	_level_root.add_child(_player)
