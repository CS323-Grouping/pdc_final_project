class_name MatchPlayer extends CharacterBody2D

## Phase 4a.3 player — solo physics + collision against platforms.
##
## No networking yet (4a.4 wires server-side position sync). Inputs come from
## the Input Map actions `move_left`, `move_right`, `jump` — declared in
## project.godot's `[input]` section, bound to WASD + arrow keys + space.
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

func _physics_process(delta: float) -> void:
	if not is_on_floor():
		velocity.y += GRAVITY * delta

	if Input.is_action_just_pressed("jump") and is_on_floor():
		velocity.y = JUMP_VELOCITY

	var direction := Input.get_axis("move_left", "move_right")
	if direction != 0.0:
		velocity.x = direction * SPEED
	else:
		velocity.x = move_toward(velocity.x, 0.0, SPEED)

	move_and_slide()

func _draw() -> void:
	# 8×12 placeholder body, centered on origin so position == body center.
	# Sprite swap comes later when art arrives.
	draw_rect(Rect2(-4.0, -6.0, 8.0, 12.0), Color(1.0, 0.55, 0.55, 1.0))
	# Tiny "eye" so we can see facing direction at a glance once we add
	# flipping in 4a.4.
	draw_rect(Rect2(-1.0, -3.0, 2.0, 2.0), Color(0.1, 0.1, 0.15, 1.0))
