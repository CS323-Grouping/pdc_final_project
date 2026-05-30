extends Control

const AVATAR_PORTRAIT_SCRIPT := preload("res://scenes/avatar/avatar_portrait.gd")
const MODEL_COLORS := ["Black", "Blue", "Gray", "Green", "Purple", "Red", "White"]
const HEAD_PNG_SIZE := 32
const MAX_HEAD_B64_LEN := 8 * 1024

var _draft_avatar: Dictionary = {}
var _portrait
var _model_option: OptionButton
var _save_button: Button
var _upload_button: Button
var _remove_button: Button
var _status_label: Label
var _color_buttons: Dictionary = {}
var _file_dialog: FileDialog
var _crop_panel: Panel
var _crop_preview: TextureRect
var _crop_zoom: HSlider
var _source_image: Image
var _crop_offset := Vector2.ZERO
var _busy := false

func _ready() -> void:
	_clear_placeholder_content()
	_draft_avatar = AvatarCache.get_avatar(Session.user_id)
	_build_preview_panel()
	_build_options_panel()
	_build_file_dialog()
	_build_crop_panel()
	_refresh_editor()

func _clear_placeholder_content() -> void:
	for path in ["PreviewPanel/PreviewLabel", "OptionsPanel/OptionsLabel"]:
		var node := get_node_or_null(path)
		if node != null:
			node.queue_free()

func _build_preview_panel() -> void:
	var panel := $PreviewPanel
	_add_label(panel, "PREVIEW", Rect2(8, 6, 94, 10), "BodyTiny", HORIZONTAL_ALIGNMENT_CENTER)

	_portrait = AVATAR_PORTRAIT_SCRIPT.new()
	_portrait.position = Vector2(30, 18)
	_portrait.size = Vector2(50, 54)
	panel.add_child(_portrait)

	_upload_button = _add_button(panel, "UPLOAD", Rect2(8, 76, 44, 16))
	_upload_button.pressed.connect(_on_upload_pressed)
	_remove_button = _add_button(panel, "REMOVE", Rect2(58, 76, 44, 16))
	_remove_button.pressed.connect(_on_remove_pressed)
	_status_label = _add_label(panel, "", Rect2(6, 94, 98, 10), "BodyTiny", HORIZONTAL_ALIGNMENT_CENTER)

func _build_options_panel() -> void:
	var panel := $OptionsPanel
	_add_label(panel, "MODEL", Rect2(8, 6, 52, 10), "BodyTiny")
	_model_option = OptionButton.new()
	_model_option.position = Vector2(58, 4)
	_model_option.size = Vector2(92, 16)
	_model_option.add_item("Default")
	_model_option.item_selected.connect(_on_model_selected)
	panel.add_child(_model_option)

	_add_label(panel, "COLOR", Rect2(8, 28, 144, 10), "BodyTiny", HORIZONTAL_ALIGNMENT_CENTER)
	for i in range(MODEL_COLORS.size()):
		var color_name: String = MODEL_COLORS[i]
		var button := Button.new()
		button.toggle_mode = true
		button.text = color_name.substr(0, 1).to_upper()
		button.tooltip_text = color_name
		button.position = Vector2(10 + (i % 4) * 36, 42 + int(i / 4) * 20)
		button.size = Vector2(30, 16)
		button.modulate = AvatarCache.model_color(color_name).lerp(Color.WHITE, 0.12)
		button.pressed.connect(_on_color_pressed.bind(color_name))
		panel.add_child(button)
		_color_buttons[color_name] = button

	_save_button = _add_button(panel, "SAVE", Rect2(46, 86, 68, 16))
	_save_button.pressed.connect(_on_save_pressed)

func _build_file_dialog() -> void:
	_file_dialog = FileDialog.new()
	_file_dialog.access = FileDialog.ACCESS_FILESYSTEM
	_file_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
	_file_dialog.filters = PackedStringArray(["*.png ; PNG Images", "*.jpg, *.jpeg ; JPG Images"])
	_file_dialog.title = "Choose avatar image"
	_file_dialog.file_selected.connect(_on_file_selected)
	add_child(_file_dialog)

func _build_crop_panel() -> void:
	_crop_panel = Panel.new()
	_crop_panel.visible = false
	_crop_panel.position = Vector2(52, 28)
	_crop_panel.size = Vector2(216, 124)
	add_child(_crop_panel)

	_add_label(_crop_panel, "CROP", Rect2(8, 8, 200, 10), "BodyTiny", HORIZONTAL_ALIGNMENT_CENTER)
	_crop_preview = TextureRect.new()
	_crop_preview.position = Vector2(16, 24)
	_crop_preview.size = Vector2(64, 64)
	_crop_preview.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_crop_preview.stretch_mode = TextureRect.STRETCH_SCALE
	_crop_panel.add_child(_crop_preview)

	_crop_zoom = HSlider.new()
	_crop_zoom.min_value = 1.0
	_crop_zoom.max_value = 4.0
	_crop_zoom.step = 0.05
	_crop_zoom.value = 1.0
	_crop_zoom.position = Vector2(96, 30)
	_crop_zoom.size = Vector2(96, 16)
	_crop_zoom.value_changed.connect(_on_crop_zoom_changed)
	_crop_panel.add_child(_crop_zoom)

	_add_button(_crop_panel, "^", Rect2(132, 50, 24, 16)).pressed.connect(_on_crop_nudge.bind(Vector2.UP))
	_add_button(_crop_panel, "<", Rect2(104, 68, 24, 16)).pressed.connect(_on_crop_nudge.bind(Vector2.LEFT))
	_add_button(_crop_panel, ">", Rect2(160, 68, 24, 16)).pressed.connect(_on_crop_nudge.bind(Vector2.RIGHT))
	_add_button(_crop_panel, "v", Rect2(132, 86, 24, 16)).pressed.connect(_on_crop_nudge.bind(Vector2.DOWN))
	_add_button(_crop_panel, "SAVE", Rect2(16, 100, 70, 16)).pressed.connect(_on_crop_save)
	_add_button(_crop_panel, "CANCEL", Rect2(130, 100, 70, 16)).pressed.connect(_on_crop_cancel)

func _add_label(parent: Node, text: String, rect: Rect2, variation: String = "BodySmall", align: HorizontalAlignment = HORIZONTAL_ALIGNMENT_LEFT) -> Label:
	var label := Label.new()
	label.text = text
	label.theme_type_variation = StringName(variation)
	label.horizontal_alignment = align
	label.position = rect.position
	label.size = rect.size
	parent.add_child(label)
	return label

func _add_button(parent: Node, text: String, rect: Rect2) -> Button:
	var button := Button.new()
	button.text = text
	button.theme_type_variation = &"Tiny"
	button.position = rect.position
	button.size = rect.size
	parent.add_child(button)
	return button

func _on_model_selected(_index: int) -> void:
	_set_model_field("model_type", AvatarCache.DEFAULT_MODEL_TYPE)

func _on_color_pressed(color_name: String) -> void:
	_set_model_field("model_color", color_name)

func _set_model_field(key: String, value: String) -> void:
	var avatar := AvatarCache.normalize_avatar(_draft_avatar)
	var model: Dictionary = avatar.get("model", {}).duplicate(true)
	model[key] = value
	avatar["model"] = model
	_draft_avatar = avatar
	_refresh_editor()

func _on_upload_pressed() -> void:
	if _busy:
		return
	_file_dialog.popup_centered(Vector2i(290, 150))

func _on_remove_pressed() -> void:
	if _busy:
		return
	_draft_avatar["head_png_b64"] = ""
	_refresh_editor()
	_status_label.text = "head cleared"

func _on_save_pressed() -> void:
	if _busy:
		return
	if not NetworkBackend.is_control_connected():
		_status_label.text = "not connected"
		return

	_set_busy(true, "saving...")
	var result := await NetworkBackend.send_control_request("set_avatar", AvatarCache.normalize_avatar(_draft_avatar))
	_set_busy(false, "")
	if not result.success:
		_status_label.text = _error_message(result.error, "save failed")
		return

	var data: Dictionary = result.data if result.data is Dictionary else {}
	var saved: Dictionary = data.get("avatar", _draft_avatar) if data.get("avatar") is Dictionary else _draft_avatar
	AvatarCache.set_avatar(Session.user_id, saved)
	_draft_avatar = AvatarCache.get_avatar(Session.user_id)
	_status_label.text = "saved"
	_refresh_editor()

func _on_file_selected(path: String) -> void:
	var image := Image.new()
	var err := image.load(path)
	if err != OK:
		_status_label.text = "image load failed"
		return
	if image.get_width() <= 0 or image.get_height() <= 0:
		_status_label.text = "empty image"
		return
	image.convert(Image.FORMAT_RGBA8)
	_source_image = image
	_crop_offset = Vector2.ZERO
	_crop_zoom.value = 1.0
	_crop_panel.visible = true
	_update_crop_preview()

func _on_crop_zoom_changed(_value: float) -> void:
	_clamp_crop_offset()
	_update_crop_preview()

func _on_crop_nudge(direction: Vector2) -> void:
	if _source_image == null:
		return
	var visible_size := _visible_crop_size()
	_crop_offset += direction * visible_size * 0.12
	_clamp_crop_offset()
	_update_crop_preview()

func _on_crop_save() -> void:
	if _source_image == null:
		return
	var image := _make_cropped_image(HEAD_PNG_SIZE)
	var png := image.save_png_to_buffer()
	var b64 := Marshalls.raw_to_base64(png)
	if b64.length() > MAX_HEAD_B64_LEN:
		_status_label.text = "image too large"
		return
	_draft_avatar["head_png_b64"] = b64
	_crop_panel.visible = false
	_source_image = null
	_status_label.text = "head staged"
	_refresh_editor()

func _on_crop_cancel() -> void:
	_crop_panel.visible = false
	_source_image = null

func _refresh_editor() -> void:
	_draft_avatar = AvatarCache.normalize_avatar(_draft_avatar)
	_portrait.avatar_override = _draft_avatar
	var model: Dictionary = _draft_avatar.get("model", {}) if _draft_avatar.get("model") is Dictionary else {}
	var selected_color := AvatarCache.normalize_model_color(String(model.get("model_color", AvatarCache.DEFAULT_MODEL_COLOR)))
	for color_name in MODEL_COLORS:
		var button: Button = _color_buttons[color_name]
		button.button_pressed = color_name == selected_color
	_remove_button.disabled = _busy or String(_draft_avatar.get("head_png_b64", "")).is_empty()
	_save_button.disabled = _busy
	_upload_button.disabled = _busy

func _set_busy(busy: bool, status: String) -> void:
	_busy = busy
	_status_label.text = status
	_refresh_editor()

func _update_crop_preview() -> void:
	if _source_image == null:
		return
	var image := _make_cropped_image(64)
	_crop_preview.texture = ImageTexture.create_from_image(image)

func _make_cropped_image(size_px: int) -> Image:
	var visible_size := _visible_crop_size()
	var center := Vector2(_source_image.get_width(), _source_image.get_height()) * 0.5 + _crop_offset
	var x := int(round(clampf(center.x - visible_size * 0.5, 0.0, float(_source_image.get_width()) - visible_size)))
	var y := int(round(clampf(center.y - visible_size * 0.5, 0.0, float(_source_image.get_height()) - visible_size)))
	var side := int(round(visible_size))
	var cropped := _source_image.get_region(Rect2i(x, y, side, side))
	cropped.resize(size_px, size_px, Image.INTERPOLATE_LANCZOS)
	cropped.convert(Image.FORMAT_RGBA8)
	return cropped

func _visible_crop_size() -> float:
	if _source_image == null:
		return 1.0
	var min_side := float(mini(_source_image.get_width(), _source_image.get_height()))
	return maxf(1.0, min_side / maxf(1.0, float(_crop_zoom.value)))

func _clamp_crop_offset() -> void:
	if _source_image == null:
		_crop_offset = Vector2.ZERO
		return
	var visible_size := _visible_crop_size()
	var max_x := maxf(0.0, (float(_source_image.get_width()) - visible_size) * 0.5)
	var max_y := maxf(0.0, (float(_source_image.get_height()) - visible_size) * 0.5)
	_crop_offset.x = clampf(_crop_offset.x, -max_x, max_x)
	_crop_offset.y = clampf(_crop_offset.y, -max_y, max_y)

func _error_message(err: Dictionary, fallback: String) -> String:
	return String(err.get("message", fallback))
