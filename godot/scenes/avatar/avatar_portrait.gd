class_name AvatarPortrait
extends Control

@export var user_id: String = "":
	set(value):
		user_id = value
		queue_redraw()

var avatar_override: Dictionary = {}:
	set(value):
		if value is Dictionary and (value as Dictionary).is_empty():
			avatar_override = {}
		else:
			avatar_override = AvatarCache.normalize_avatar(value)
		_override_texture = null
		queue_redraw()

var _override_texture: Texture2D

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	if not AvatarCache.avatar_changed.is_connected(_on_avatar_changed):
		AvatarCache.avatar_changed.connect(_on_avatar_changed)

func _exit_tree() -> void:
	if AvatarCache.avatar_changed.is_connected(_on_avatar_changed):
		AvatarCache.avatar_changed.disconnect(_on_avatar_changed)

func clear_override() -> void:
	avatar_override = {}
	_override_texture = null
	queue_redraw()

func _on_avatar_changed(changed_user_id: String, _avatar: Dictionary) -> void:
	if avatar_override.is_empty() and changed_user_id == user_id:
		queue_redraw()

func _draw() -> void:
	if size.x <= 1.0 or size.y <= 1.0:
		return
	var avatar := avatar_override if not avatar_override.is_empty() else AvatarCache.get_avatar(user_id)
	var model: Dictionary = avatar.get("model", {}) if avatar.get("model") is Dictionary else {}
	var body_color := AvatarCache.model_color(String(model.get("model_color", AvatarCache.DEFAULT_MODEL_COLOR)))
	var bg_rect := Rect2(Vector2.ZERO, size)
	draw_rect(bg_rect, Color(0.04, 0.07, 0.12, 0.92))
	draw_rect(bg_rect, Color(0.32, 0.47, 0.70, 0.85), false, maxf(1.0, floorf(minf(size.x, size.y) / 18.0)))

	var unit: float = maxf(1.0, floorf(minf(size.x / 18.0, size.y / 24.0)))
	var center_x := floorf(size.x * 0.5)
	var foot_y := size.y - unit * 2.0
	var body_rect := Rect2(
		Vector2(center_x - unit * 4.0, foot_y - unit * 12.0),
		Vector2(unit * 8.0, unit * 12.0)
	)
	var head_rect := Rect2(
		Vector2(center_x - unit * 4.5, body_rect.position.y - unit * 7.0),
		Vector2(unit * 9.0, unit * 9.0)
	)

	draw_rect(body_rect, body_color)
	draw_rect(Rect2(body_rect.position + Vector2(unit, unit * 8.0), Vector2(unit * 6.0, unit * 2.0)), body_color.darkened(0.25))

	var head_texture := _head_texture_for_avatar(avatar)
	if head_texture != null:
		draw_texture_rect(head_texture, head_rect, false)
	else:
		draw_rect(head_rect, body_color.lerp(Color.WHITE, 0.32))
		draw_rect(Rect2(head_rect.position + Vector2(unit * 2.0, unit * 3.0), Vector2(unit, unit)), Color(0.08, 0.10, 0.16, 1.0))
		draw_rect(Rect2(head_rect.position + Vector2(unit * 6.0, unit * 3.0), Vector2(unit, unit)), Color(0.08, 0.10, 0.16, 1.0))

func _head_texture_for_avatar(avatar: Dictionary) -> Texture2D:
	if avatar_override.is_empty():
		return AvatarCache.head_texture(user_id)
	if _override_texture == null:
		_override_texture = AvatarCache.texture_from_avatar(avatar)
	return _override_texture
