extends LevelElement

## Placeholder orb pickup — drawn as a small filled circle.
## Phase 5 wires collision + score effects.

const RADIUS := 4.0

func _draw() -> void:
	draw_circle(Vector2.ZERO, RADIUS, Color(1.0, 0.85, 0.3, 1.0))
	# Tiny inner highlight so the orb reads as glowy rather than flat.
	draw_circle(Vector2(-1, -1), 1.5, Color(1.0, 0.97, 0.75, 1.0))
