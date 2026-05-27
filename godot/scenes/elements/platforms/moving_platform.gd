extends "res://world/stateful_element.gd"

const WIDTH := 50.0
const HEIGHT := 8.0
const TRAVEL := 42.0
const SPEED := 1.35

var _origin: Vector2 = Vector2.ZERO
var _phase: float = 0.0

func _ready() -> void:
	_origin = position

func init_with_seed(seed: int) -> void:
	_phase = float(abs(seed % 628)) / 100.0

func _physics_process(delta: float) -> void:
	_phase += delta * SPEED
	position = _origin + Vector2(sin(_phase) * TRAVEL, 0.0)
	set_state_value(&"offset_x", position.x - _origin.x)

func _draw() -> void:
	draw_rect(Rect2(-WIDTH * 0.5, -HEIGHT * 0.5, WIDTH, HEIGHT), Color(0.82, 0.72, 0.95, 1.0))
	draw_line(Vector2(-WIDTH * 0.5, -HEIGHT * 0.5), Vector2(WIDTH * 0.5, -HEIGHT * 0.5), Color(1, 0.92, 1, 1), 1.0)
	draw_line(Vector2(-WIDTH * 0.35, HEIGHT * 0.5 + 3.0), Vector2(WIDTH * 0.35, HEIGHT * 0.5 + 3.0), Color(0.45, 0.38, 0.62, 1), 1.0)
