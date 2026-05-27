extends "res://world/stateful_element.gd"

const WIDTH := 50.0
const HEIGHT := 8.0
const BREAK_DELAY_MSEC := 1300

@onready var _body: StaticBody2D = $Body
@onready var _shape: CollisionShape2D = $Body/Shape
@onready var _surface_area: Area2D = $SurfaceArea

var _stand_started_at_msec := 0
var _broken := false

func _physics_process(_delta: float) -> void:
	if _broken:
		return
	var has_player := false
	for body in _surface_area.get_overlapping_bodies():
		if body is MatchPlayer:
			has_player = true
			break
	if has_player and _stand_started_at_msec == 0:
		_stand_started_at_msec = Time.get_ticks_msec()
		set_state_value(&"stand_started_at_msec", _stand_started_at_msec)
	if _stand_started_at_msec > 0 and Time.get_ticks_msec() - _stand_started_at_msec >= BREAK_DELAY_MSEC:
		_break()

func _break() -> void:
	_broken = true
	_shape.disabled = true
	_body.collision_layer = 0
	set_state_value(&"broken", true)
	queue_redraw()

func _draw() -> void:
	if _broken:
		draw_line(Vector2(-20, 0), Vector2(20, 0), Color(0.58, 0.9, 1.0, 0.45), 1.0)
		return
	draw_rect(Rect2(-WIDTH * 0.5, -HEIGHT * 0.5, WIDTH, HEIGHT), Color(0.75, 0.92, 1.0, 1.0))
	draw_line(Vector2(-18, -2), Vector2(-6, 2), Color(0.3, 0.65, 0.9, 1.0), 1.0)
	draw_line(Vector2(3, -3), Vector2(14, 2), Color(0.3, 0.65, 0.9, 1.0), 1.0)
