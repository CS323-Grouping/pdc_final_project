extends Node

signal avatar_changed(user_id: String, avatar: Dictionary)

const DEFAULT_MODEL_TYPE := "default"
const DEFAULT_MODEL_COLOR := "Blue"

var _avatars: Dictionary = {}
var _head_textures: Dictionary = {}

func default_avatar() -> Dictionary:
	return {
		"model": {
			"model_type": DEFAULT_MODEL_TYPE,
			"model_color": DEFAULT_MODEL_COLOR,
		},
		"head_png_b64": "",
	}

func normalize_avatar(value: Variant) -> Dictionary:
	var avatar: Dictionary = value if value is Dictionary else {}
	var model_value: Variant = avatar.get("model", {})
	var model: Dictionary = model_value if model_value is Dictionary else {}
	var model_type := String(model.get("model_type", DEFAULT_MODEL_TYPE)).strip_edges().to_lower()
	if model_type.is_empty():
		model_type = DEFAULT_MODEL_TYPE
	if model_type != DEFAULT_MODEL_TYPE:
		model_type = DEFAULT_MODEL_TYPE
	return {
		"model": {
			"model_type": model_type,
			"model_color": normalize_model_color(String(model.get("model_color", DEFAULT_MODEL_COLOR))),
		},
		"head_png_b64": String(avatar.get("head_png_b64", "")).strip_edges(),
	}

func normalize_model_color(color_name: String) -> String:
	match color_name.strip_edges().to_lower():
		"black":
			return "Black"
		"gray", "grey":
			return "Gray"
		"green":
			return "Green"
		"purple":
			return "Purple"
		"red":
			return "Red"
		"white":
			return "White"
		_:
			return DEFAULT_MODEL_COLOR

func model_color(color_name: String) -> Color:
	match normalize_model_color(color_name):
		"Black":
			return Color(0.16, 0.18, 0.23, 1.0)
		"Gray":
			return Color(0.55, 0.60, 0.66, 1.0)
		"Green":
			return Color(0.25, 0.72, 0.38, 1.0)
		"Purple":
			return Color(0.58, 0.39, 0.86, 1.0)
		"Red":
			return Color(0.86, 0.30, 0.30, 1.0)
		"White":
			return Color(0.88, 0.92, 0.96, 1.0)
		_:
			return Color(0.28, 0.52, 0.90, 1.0)

func set_avatar(user_id: String, avatar: Variant) -> void:
	if user_id.is_empty():
		return
	var normalized := normalize_avatar(avatar)
	_avatars[user_id] = normalized
	_head_textures.erase(user_id)
	avatar_changed.emit(user_id, normalized)

func clear() -> void:
	_avatars.clear()
	_head_textures.clear()

func get_avatar(user_id: String) -> Dictionary:
	if not user_id.is_empty() and _avatars.has(user_id):
		return (_avatars[user_id] as Dictionary).duplicate(true)
	return default_avatar()

func apply_hello_payload(payload: Dictionary) -> void:
	var user_id := String(payload.get("your_user_id", ""))
	if payload.get("your_avatar") is Dictionary:
		set_avatar(user_id, payload.get("your_avatar"))

func cache_players(players_value: Variant) -> void:
	if not (players_value is Array):
		return
	for player_value in players_value:
		var player: Dictionary = player_value if player_value is Dictionary else {}
		var user_id := String(player.get("user_id", ""))
		if not user_id.is_empty() and player.get("avatar") is Dictionary:
			set_avatar(user_id, player.get("avatar"))

func head_texture(user_id: String) -> Texture2D:
	if user_id.is_empty():
		return null
	var avatar := get_avatar(user_id)
	var head_png_b64 := String(avatar.get("head_png_b64", ""))
	if head_png_b64.is_empty():
		return null
	if _head_textures.has(user_id):
		return _head_textures[user_id] as Texture2D
	var texture := _texture_from_b64(head_png_b64)
	if texture != null:
		_head_textures[user_id] = texture
	return texture

func texture_from_avatar(avatar: Variant) -> Texture2D:
	var normalized := normalize_avatar(avatar)
	return _texture_from_b64(String(normalized.get("head_png_b64", "")))

func _texture_from_b64(head_png_b64: String) -> Texture2D:
	if head_png_b64.is_empty():
		return null
	var raw := Marshalls.base64_to_raw(head_png_b64)
	if raw.is_empty():
		return null
	var image := Image.new()
	if image.load_png_from_buffer(raw) != OK:
		return null
	return ImageTexture.create_from_image(image)
