extends LevelElement

## Placeholder regular platform — solid rectangle, no behavior yet.
## Sprite swap lands when art arrives; collision lands in Phase 4a.3 with
## player physics.

const WIDTH := 50
const HEIGHT := 8

func _draw() -> void:
	# Centered around the LevelElement's position so generator coordinates
	# refer to the platform's center.
	draw_rect(
		Rect2(-WIDTH * 0.5, -HEIGHT * 0.5, WIDTH, HEIGHT),
		Color(0.65, 0.78, 0.95, 1.0),
	)
	# Top highlight + bottom shadow for a hint of pixel-art chrome.
	draw_line(
		Vector2(-WIDTH * 0.5, -HEIGHT * 0.5),
		Vector2(WIDTH * 0.5, -HEIGHT * 0.5),
		Color(0.85, 0.95, 1.0, 1.0),
		1.0,
	)
	draw_line(
		Vector2(-WIDTH * 0.5, HEIGHT * 0.5 - 1),
		Vector2(WIDTH * 0.5, HEIGHT * 0.5 - 1),
		Color(0.25, 0.35, 0.55, 1.0),
		1.0,
	)
