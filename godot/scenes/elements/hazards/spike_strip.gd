extends LevelElement

const WIDTH := 46.0
const HEIGHT := 10.0

@onready var _hit_area: Area2D = $HitArea

func _physics_process(_delta: float) -> void:
	for body in _hit_area.get_overlapping_bodies():
		var player := body as MatchPlayer
		if player != null:
			player.hit_hazard(global_position)

func _draw() -> void:
	for i in 6:
		var x := -WIDTH * 0.5 + float(i) * (WIDTH / 6.0)
		var points := PackedVector2Array([
			Vector2(x, HEIGHT * 0.5),
			Vector2(x + WIDTH / 12.0, -HEIGHT * 0.5),
			Vector2(x + WIDTH / 6.0, HEIGHT * 0.5),
		])
		draw_colored_polygon(points, Color(0.95, 0.32, 0.36, 1.0))
