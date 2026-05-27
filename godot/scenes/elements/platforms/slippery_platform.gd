extends LevelElement

const WIDTH := 50.0
const HEIGHT := 8.0

@onready var _surface_area: Area2D = $SurfaceArea

func _physics_process(_delta: float) -> void:
	for body in _surface_area.get_overlapping_bodies():
		var player := body as MatchPlayer
		if player != null:
			player.mark_slippery()

func _draw() -> void:
	draw_rect(Rect2(-WIDTH * 0.5, -HEIGHT * 0.5, WIDTH, HEIGHT), Color(0.68, 0.95, 1.0, 1.0))
	draw_line(Vector2(-WIDTH * 0.5, -HEIGHT * 0.5), Vector2(WIDTH * 0.5, -HEIGHT * 0.5), Color(0.95, 1.0, 1.0, 1.0), 1.0)
	for i in 3:
		var y := -2.0 + float(i) * 2.0
		draw_line(Vector2(-18.0, y), Vector2(18.0, y - 2.0), Color(0.35, 0.72, 0.92, 1.0), 1.0)
