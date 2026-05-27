class_name MatchPlayer extends CharacterBody2D

## Phase 4a.4 player — local physics plus remote interpolation.
##
## Local players run the same CharacterBody2D movement from 4a.3. Remote
## players are visual ghosts driven by `peer_state_update` payloads from the
## Go server, leaving collision authority with the local client for this MVP.
##
## Tuning numbers below are picked so a single jump comfortably clears one
## BAND_HEIGHT (50 px) gap. If you change BAND_HEIGHT in level_generator.gd,
## re-check JUMP_VELOCITY here too.
##
## Coyote time / jump buffering / variable-height jump are polish items —
## defer until the basic feel is validated.

const SPEED := 110.0           # px/s horizontal
const JUMP_VELOCITY := -250.0  # px/s — negative is up
const GRAVITY := 480.0         # px/s²
const REMOTE_INTERP_SPEED := 14.0
const SLIPPERY_DECEL_MULT := 0.22

var owner_user_id: String = ""
var display_name: String = ""
var is_local_player: bool = true
var controls_enabled: bool = true
var facing: int = 1

var _remote_target_position: Vector2 = Vector2.ZERO
var _remote_target_velocity: Vector2 = Vector2.ZERO
var _has_remote_target: bool = false
var _slippery_until_msec: int = 0
var _hazard_cooldown_until_msec: int = 0

func _physics_process(delta: float) -> void:
	if not is_local_player:
		_physics_process_remote(delta)
		return

	if not controls_enabled:
		velocity = Vector2.ZERO
		return

	if not is_on_floor():
		velocity.y += GRAVITY * delta

	if Input.is_action_just_pressed("jump") and is_on_floor():
		velocity.y = JUMP_VELOCITY

	var direction: float = Input.get_axis("move_left", "move_right")
	if direction != 0.0:
		velocity.x = direction * SPEED
		facing = -1 if direction < 0.0 else 1
		queue_redraw()
	else:
		var decel: float = SPEED * SLIPPERY_DECEL_MULT if _is_slippery() else SPEED
		velocity.x = move_toward(velocity.x, 0.0, decel)

	move_and_slide()

func configure(user_id: String, player_name: String, local_player: bool) -> void:
	owner_user_id = user_id
	display_name = player_name
	is_local_player = local_player
	if is_local_player:
		collision_layer = 1
		collision_mask = 1
	else:
		collision_layer = 0
		collision_mask = 0
	queue_redraw()

func snapshot_state(tick: int) -> Dictionary:
	return {
		"tick": tick,
		"x": global_position.x,
		"y": global_position.y,
		"vx": velocity.x,
		"vy": velocity.y,
		"grounded": is_on_floor(),
		"facing": facing,
	}

func apply_remote_state(state: Dictionary) -> void:
	var x: float = float(state.get("x", global_position.x))
	var y: float = float(state.get("y", global_position.y))
	var vx: float = float(state.get("vx", 0.0))
	var vy: float = float(state.get("vy", 0.0))
	_remote_target_position = Vector2(x, y)
	_remote_target_velocity = Vector2(vx, vy)
	_has_remote_target = true
	var incoming_facing: int = int(state.get("facing", facing))
	if incoming_facing != facing:
		facing = -1 if incoming_facing < 0 else 1
		queue_redraw()

func set_controls_enabled(enabled: bool) -> void:
	controls_enabled = enabled
	if not enabled:
		velocity = Vector2.ZERO

func boost_jump(strength: float) -> void:
	if not is_local_player:
		return
	velocity.y = minf(velocity.y, strength)

func mark_slippery(duration_msec: int = 220) -> void:
	if not is_local_player:
		return
	_slippery_until_msec = maxi(_slippery_until_msec, Time.get_ticks_msec() + duration_msec)

func hit_hazard(source_position: Vector2, upward_force: float = -210.0, horizontal_force: float = 90.0) -> void:
	if not is_local_player:
		return
	var now := Time.get_ticks_msec()
	if now < _hazard_cooldown_until_msec:
		return
	_hazard_cooldown_until_msec = now + 450
	var direction := 1.0 if global_position.x >= source_position.x else -1.0
	velocity.x = direction * horizontal_force
	velocity.y = minf(velocity.y, upward_force)

func _physics_process_remote(delta: float) -> void:
	if not _has_remote_target:
		return
	var weight: float = clampf(delta * REMOTE_INTERP_SPEED, 0.0, 1.0)
	global_position = global_position.lerp(_remote_target_position, weight)
	velocity = _remote_target_velocity

func _is_slippery() -> bool:
	return Time.get_ticks_msec() <= _slippery_until_msec

func _draw() -> void:
	# 8×12 placeholder body, centered on origin so position == body center.
	# Sprite swap comes later when art arrives.
	var body_color: Color = Color(1.0, 0.55, 0.55, 1.0) if is_local_player else Color(0.35, 0.68, 1.0, 0.9)
	draw_rect(Rect2(-4.0, -6.0, 8.0, 12.0), body_color)
	var eye_x: float = 1.0 if facing >= 0 else -3.0
	draw_rect(Rect2(eye_x, -3.0, 2.0, 2.0), Color(0.1, 0.1, 0.15, 1.0))
