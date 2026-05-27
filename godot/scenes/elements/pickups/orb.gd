class_name OrbPickup extends LevelElement

## Placeholder orb pickup — drawn as a small filled circle.
## Phase 4a.4 keeps collision lightweight: Match.gd checks local player
## overlap, then asks the server to fan out the collected network_id.

const RADIUS := 4.0

var collected: bool = false

func collect() -> void:
	if collected:
		return
	collected = true
	visible = false
	queue_redraw()

func _draw() -> void:
	if collected:
		return
	draw_circle(Vector2.ZERO, RADIUS, Color(1.0, 0.85, 0.3, 1.0))
	# Tiny inner highlight so the orb reads as glowy rather than flat.
	draw_circle(Vector2(-1, -1), 1.5, Color(1.0, 0.97, 0.75, 1.0))
