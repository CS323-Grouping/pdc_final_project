extends "res://world/stateful_element.gd"

const GRAVITY := 520.0
const TERMINAL_VELOCITY := 280.0

@onready var _trigger_area: Area2D = $TriggerArea
@onready var _hit_area: Area2D = $HitArea

var _falling := false
var _velocity_y := 0.0

func _physics_process(delta: float) -> void:
	if not _falling:
		for body in _trigger_area.get_overlapping_bodies():
			if body is MatchPlayer:
				_falling = true
				set_state_value(&"falling", true)
				break
	else:
		_velocity_y = minf(_velocity_y + GRAVITY * delta, TERMINAL_VELOCITY)
		position.y += _velocity_y * delta

	for body in _hit_area.get_overlapping_bodies():
		var player := body as MatchPlayer
		if player != null:
			player.hit_hazard(global_position, -180.0, 70.0)

func _draw() -> void:
	var points := PackedVector2Array([
		Vector2(-4, -8),
		Vector2(4, -8),
		Vector2(0, 10),
	])
	draw_colored_polygon(points, Color(0.78, 0.96, 1.0, 1.0))
	draw_line(Vector2(-1, -6), Vector2(0, 6), Color(1, 1, 1, 1), 1.0)
