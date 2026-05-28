extends Node

@export var hover_scale: float = 1.03
@export var pressed_scale: float = 0.94
@export var hover_duration: float = 0.08
@export var pressed_duration: float = 0.045
@export var return_duration: float = 0.07

var _button: BaseButton
var _tween: Tween
var _hovered: bool = false

func _ready() -> void:
	_button = get_parent() as BaseButton
	if _button == null:
		push_warning("AnimatedButton: parent is not a BaseButton: %s" % get_path())
		return

	_update_pivot()
	_button.resized.connect(_update_pivot)
	_button.mouse_entered.connect(_on_mouse_entered)
	_button.mouse_exited.connect(_on_mouse_exited)
	_button.button_down.connect(_on_button_down)
	_button.button_up.connect(_on_button_up)
	_button.visibility_changed.connect(_on_visibility_changed)
	_button.tree_exiting.connect(_on_button_exiting)

func _exit_tree() -> void:
	_kill_tween()
	if _button != null:
		_button.scale = Vector2.ONE

func _update_pivot() -> void:
	if _button == null:
		return
	_button.pivot_offset = _button.size * 0.5

func _on_mouse_entered() -> void:
	if _button.disabled:
		return
	_hovered = true
	_animate_to(Vector2.ONE * hover_scale, hover_duration)

func _on_mouse_exited() -> void:
	_hovered = false
	if _button == null or _button.button_pressed:
		return
	_animate_to(Vector2.ONE, return_duration)

func _on_button_down() -> void:
	if _button.disabled:
		return
	_animate_to(Vector2.ONE * pressed_scale, pressed_duration)

func _on_button_up() -> void:
	if _button.disabled:
		return
	var target_scale := hover_scale if _hovered else 1.0
	_animate_to(Vector2.ONE * target_scale, return_duration)

func _on_visibility_changed() -> void:
	if _button == null or _button.visible:
		return
	_hovered = false
	_kill_tween()
	_button.scale = Vector2.ONE

func _on_button_exiting() -> void:
	_kill_tween()

func _animate_to(target_scale: Vector2, duration: float) -> void:
	if _button == null:
		return
	_kill_tween()
	_tween = create_tween()
	_tween.set_trans(Tween.TRANS_QUAD)
	_tween.set_ease(Tween.EASE_OUT)
	_tween.tween_property(_button, "scale", target_scale, duration)

func _kill_tween() -> void:
	if _tween != null:
		_tween.kill()
		_tween = null
