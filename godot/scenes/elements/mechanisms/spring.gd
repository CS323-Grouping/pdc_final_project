extends LevelElement

const BOOST := -365.0
const COOLDOWN_MSEC := 260

@onready var _boost_area: Area2D = $BoostArea

var _last_boost_at_msec := 0

func _physics_process(_delta: float) -> void:
	var now := Time.get_ticks_msec()
	if now - _last_boost_at_msec < COOLDOWN_MSEC:
		return
	for body in _boost_area.get_overlapping_bodies():
		var player := body as MatchPlayer
		if player != null:
			player.boost_jump(BOOST)
			_last_boost_at_msec = now
			queue_redraw()
			return

func _draw() -> void:
	draw_rect(Rect2(-10, 2, 20, 4), Color(0.25, 0.95, 0.55, 1.0))
	draw_line(Vector2(-8, 2), Vector2(-4, -6), Color(0.8, 1.0, 0.7, 1.0), 2.0)
	draw_line(Vector2(-4, -6), Vector2(0, 2), Color(0.8, 1.0, 0.7, 1.0), 2.0)
	draw_line(Vector2(0, 2), Vector2(4, -6), Color(0.8, 1.0, 0.7, 1.0), 2.0)
	draw_line(Vector2(4, -6), Vector2(8, 2), Color(0.8, 1.0, 0.7, 1.0), 2.0)
