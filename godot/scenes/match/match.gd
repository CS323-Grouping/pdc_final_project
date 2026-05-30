extends Node2D

## Match scene — Phase 4a.4.
##
## The Go backend remains the room authority, while player motion is a
## client-authoritative relay for the MVP: local clients send `player_state`
## over the existing control WebSocket at 20 Hz, and the server fans
## `peer_state_update` to the other clients in the room.
##
## ESC returns to the previous scene (SceneManager handles ui_cancel
## globally; this scene doesn't need its own handler).

const DEFAULT_ENV_ID := &"default"
const DEFAULT_DIFFICULTY := 1
const DEFAULT_SEED := 42
const CAMERA_FOLLOW_LERP := 0.15
const CAMERA_PLAYER_OFFSET_Y := -30.0
const PLAYER_STATE_SEND_HZ := 20.0
const PLAYER_STATE_SEND_INTERVAL := 1.0 / PLAYER_STATE_SEND_HZ
const ORB_PICKUP_RADIUS := 10.0
const ELIMINATION_PADDING := 120.0
const MATCH_FINISH_Y := 24.0
const PLAYER_SCENE: PackedScene = preload("res://scenes/match/player.tscn")
const RESULTS_SCENE := "res://scenes/results/match_results.tscn"

@onready var _camera: Camera2D = %Camera
@onready var _level_root: Node2D = %LevelRoot
@onready var _debug_label: Label = %DebugLabel

var _data: LevelData
var _env: LevelEnvironment
var _player: MatchPlayer
var _peers: Dictionary = {}
var _orbs: Dictionary = {}
var _collected_orbs: Dictionary = {}
var _state_send_accum: float = 0.0
var _state_tick: int = 0
var _added_elements: int = 0
var _your_player_id: String = ""
var _match_finished: bool = false
var _local_done: bool = false
var _status_text: String = ""

func _ready() -> void:
	var params: Dictionary = Session.match_params
	AvatarCache.cache_players(Session.current_room_snapshot.get("players", []))
	_your_player_id = String(params.get("your_player_id", Session.user_id))
	if _your_player_id.is_empty():
		_your_player_id = Session.user_id
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

	var populator: LevelPopulator = LevelPopulator.new()
	add_child(populator)
	_added_elements = populator.populate(_data, _level_root)
	_index_orbs()

	_add_floor()
	_spawn_player()

	if _player != null:
		_camera.position = Vector2(160.0, _player.position.y + CAMERA_PLAYER_OFFSET_Y)

	if not NetworkBackend.control_message.is_connected(_on_control_message):
		NetworkBackend.control_message.connect(_on_control_message)
	_update_debug_label()

func _exit_tree() -> void:
	if NetworkBackend.control_message.is_connected(_on_control_message):
		NetworkBackend.control_message.disconnect(_on_control_message)

func _process(delta: float) -> void:
	if _player == null or _data == null:
		return

	_update_camera()
	if _match_finished:
		return

	_state_send_accum += delta
	if _state_send_accum >= PLAYER_STATE_SEND_INTERVAL:
		_state_send_accum = 0.0
		_send_player_state()
	_check_orb_pickups()
	_check_elimination()

func _update_camera() -> void:
	var target_y: float = _player.position.y + CAMERA_PLAYER_OFFSET_Y
	target_y = clampf(target_y, 90.0, float(_data.total_height) - 90.0)
	var pos: Vector2 = _camera.position
	pos.x = 160.0
	pos.y = lerpf(pos.y, target_y, CAMERA_FOLLOW_LERP)
	_camera.position = pos

func _add_floor() -> void:
	var body: StaticBody2D = StaticBody2D.new()
	body.position = Vector2(160.0, float(_data.total_height) + 5.0)
	var shape: CollisionShape2D = CollisionShape2D.new()
	var rect: RectangleShape2D = RectangleShape2D.new()
	rect.size = Vector2(320.0, 10.0)
	shape.shape = rect
	body.add_child(shape)
	_level_root.add_child(body)

func _spawn_player() -> void:
	_player = PLAYER_SCENE.instantiate() as MatchPlayer
	if _player == null:
		push_error("Match: PLAYER_SCENE root does not extend MatchPlayer")
		return
	var player_name: String = Session.display_name if not Session.display_name.is_empty() else "You"
	_player.configure(_your_player_id, player_name, true)
	_player.position = Vector2(160.0, float(_data.total_height) - 25.0)
	_level_root.add_child(_player)

func _spawn_remote_player(user_id: String, player_name: String, start_position: Vector2) -> MatchPlayer:
	var peer: MatchPlayer = PLAYER_SCENE.instantiate() as MatchPlayer
	if peer == null:
		push_error("Match: PLAYER_SCENE root does not extend MatchPlayer")
		return null
	peer.configure(user_id, player_name, false)
	peer.position = start_position
	_level_root.add_child(peer)
	_peers[user_id] = peer
	_update_debug_label()
	return peer

func _send_player_state() -> void:
	if _local_done or not NetworkBackend.is_control_connected():
		return
	_state_tick += 1
	var payload: Dictionary = _player.snapshot_state(_state_tick)
	var err: Error = NetworkBackend.send_envelope({
		"t": "player_state",
		"d": payload,
	})
	if err != OK:
		push_warning("Match: could not send player_state (%d)" % err)

func _on_control_message(envelope: Dictionary) -> void:
	var msg_type: String = String(envelope.get("t", ""))
	var raw_payload: Variant = envelope.get("d", {})
	var payload: Dictionary = {}
	if raw_payload is Dictionary:
		payload = raw_payload
	match msg_type:
		"peer_state_update":
			_handle_peer_state(payload)
		"peer_left":
			_handle_peer_left(payload)
		"orb_collected":
			_handle_orb_collected(payload)
		"match_results":
			_handle_match_results(payload)
		"avatar_updated":
			_handle_avatar_updated(payload)
		"match_snapshot":
			_handle_match_snapshot(payload)

func _handle_peer_state(payload: Dictionary) -> void:
	var user_id: String = String(payload.get("user_id", ""))
	if user_id.is_empty() or user_id == _your_player_id:
		return
	var existing: Variant = _peers.get(user_id)
	var peer: MatchPlayer = existing as MatchPlayer
	if peer == null:
		var display_name: String = String(payload.get("display_name", user_id))
		var default_y: float = _player.global_position.y if _player != null else float(_data.total_height)
		var start_position: Vector2 = Vector2(float(payload.get("x", 160.0)), float(payload.get("y", default_y)))
		peer = _spawn_remote_player(user_id, display_name, start_position)
	if peer != null:
		peer.apply_remote_state(payload)

func _handle_peer_left(payload: Dictionary) -> void:
	var user_id: String = String(payload.get("user_id", ""))
	if user_id.is_empty():
		return
	var existing: Variant = _peers.get(user_id)
	var peer: MatchPlayer = existing as MatchPlayer
	if peer != null:
		peer.queue_free()
	_peers.erase(user_id)
	_update_debug_label()

func _handle_avatar_updated(payload: Dictionary) -> void:
	var user_id := String(payload.get("user_id", ""))
	if user_id.is_empty():
		return
	AvatarCache.set_avatar(user_id, payload)

func _handle_match_snapshot(payload: Dictionary) -> void:
	if payload.get("snapshot") is Dictionary:
		Session.set_lobby_snapshot(payload.get("snapshot"))
	if payload.get("peer_states") is Array:
		for state_value in payload.get("peer_states"):
			if state_value is Dictionary:
				_handle_peer_state(state_value)
	if payload.get("collected_orbs") is Array:
		for orb_id_value in payload.get("collected_orbs"):
			_mark_orb_collected(String(orb_id_value))
	if payload.get("placements") is Array:
		var placements: Array = payload.get("placements")
		if not placements.is_empty():
			_apply_placement_status(placements)
			_update_debug_label()
	if bool(payload.get("final", false)):
		_match_finished = true
		Session.match_results = {
			"placements": payload.get("placements", []),
			"final": true,
		}
		SceneManager.replace(RESULTS_SCENE)

func _check_orb_pickups() -> void:
	if _local_done:
		return
	for value in _orbs.values():
		var orb: OrbPickup = value as OrbPickup
		if orb == null or orb.collected or orb.network_id.is_empty():
			continue
		if _player.global_position.distance_to(orb.global_position) <= ORB_PICKUP_RADIUS:
			_mark_orb_collected(orb.network_id)
			_send_orb_collected(orb.network_id)

func _send_orb_collected(orb_id: String) -> void:
	if not NetworkBackend.is_control_connected():
		return
	var err: Error = NetworkBackend.send_envelope({
		"t": "orb_collected",
		"d": {"orb_id": orb_id},
	})
	if err != OK:
		push_warning("Match: could not send orb_collected (%d)" % err)

func _check_elimination() -> void:
	if _local_done or _player == null:
		return
	if _player.global_position.y <= MATCH_FINISH_Y:
		return
	var inside_bounds := (
		_player.global_position.y <= float(_data.total_height) + ELIMINATION_PADDING
		and _player.global_position.x >= -80.0
		and _player.global_position.x <= 400.0
	)
	if inside_bounds:
		return
	_local_done = true
	_player.visible = false
	_player.set_controls_enabled(false)
	_status_text = "ELIMINATED - spectating"
	_update_debug_label()
	_send_player_eliminated("fell")

func _send_player_eliminated(reason: String) -> void:
	if not NetworkBackend.is_control_connected():
		return
	var err: Error = NetworkBackend.send_envelope({
		"t": "player_eliminated",
		"d": {"reason": reason},
	})
	if err != OK:
		push_warning("Match: could not send player_eliminated (%d)" % err)

func _handle_orb_collected(payload: Dictionary) -> void:
	var orb_id: String = String(payload.get("orb_id", ""))
	if orb_id.is_empty():
		return
	_mark_orb_collected(orb_id)

func _mark_orb_collected(orb_id: String) -> void:
	if _collected_orbs.has(orb_id):
		return
	_collected_orbs[orb_id] = true
	var existing: Variant = _orbs.get(orb_id)
	var orb: OrbPickup = existing as OrbPickup
	if orb != null:
		orb.collect()
	_update_debug_label()

func _handle_match_results(payload: Dictionary) -> void:
	var raw_placements: Variant = payload.get("placements", [])
	if not (raw_placements is Array):
		return
	var placements: Array = raw_placements
	if placements.is_empty():
		return
	_apply_placement_status(placements)
	_update_debug_label()
	if bool(payload.get("final", false)):
		_match_finished = true
		Session.match_results = payload
		SceneManager.replace(RESULTS_SCENE)

func _apply_placement_status(placements: Array) -> void:
	var first: Dictionary = placements[0] if placements[0] is Dictionary else {}
	var winner_id: String = String(first.get("user_id", ""))
	var winner_name: String = String(first.get("display_name", winner_id))
	if winner_id == _your_player_id:
		_status_text = "FINISHED 1st - waiting for results"
	elif not winner_name.is_empty():
		_status_text = "LEADER: %s" % winner_name
	for placement_value in placements:
		var placement: Dictionary = placement_value if placement_value is Dictionary else {}
		if String(placement.get("user_id", "")) != _your_player_id:
			continue
		_local_done = true
		if _player != null:
			_player.set_controls_enabled(false)
		var result := String(placement.get("result", "finished"))
		if result == "eliminated":
			_status_text = "ELIMINATED - spectating"
		else:
			_status_text = "FINISHED #%d - spectating" % int(placement.get("place", 0))
		break
	if not winner_name.is_empty():
		print("[Match] match_results leader=%s" % winner_name)

func _index_orbs() -> void:
	_orbs.clear()
	_collect_orbs_under(_level_root)

func _collect_orbs_under(node: Node) -> void:
	for child in node.get_children():
		var orb: OrbPickup = child as OrbPickup
		if orb != null and not orb.network_id.is_empty():
			_orbs[orb.network_id] = orb
		_collect_orbs_under(child)

func _update_debug_label() -> void:
	if _data == null:
		return
	var debug_line: String = "env=%s diff=%d seed=%d elts=%d/%d peers=%d orbs=%d/%d" % [
		_data.env_id,
		_data.difficulty,
		_data.seed,
		_added_elements,
		_data.slots.size(),
		_peers.size(),
		_collected_orbs.size(),
		_orbs.size(),
	]
	_debug_label.text = debug_line if _status_text.is_empty() else "%s\n%s" % [_status_text, debug_line]
