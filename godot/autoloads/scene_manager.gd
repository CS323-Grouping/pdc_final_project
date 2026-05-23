extends Node

## Centralized scene transitions with a simple back stack.
##
## Use `SceneManager.go_to(scene)` to navigate forward — pushes current scene
## onto history. `scene` is either a PackedScene (preferred — survives file
## moves via UID) or a String resource path.
## Use `SceneManager.go_back()` to pop. Use `SceneManager.replace(scene)` to
## swap without affecting history (e.g. logout returning to login should NOT be
## "back-able" to the post-login screen).
##
## ESC is wired as a global "back" key via the built-in `ui_cancel` input
## action (defaults to ESC; remappable). Individual scenes don't need to
## repeat the handler. Scenes that need their own ESC behavior (e.g. closing
## a modal) should handle it in `_input` (higher priority than
## `_unhandled_input`).
##
## Internally defers `change_scene_to_file` so it's safe to call from inside a
## button signal or input handler (avoids "Can't change scene during input").
##
## Caveat: history is tracked via `scene_file_path` of the main scene. If we
## ever switch to a model where multiple scenes coexist as siblings of a
## persistent root, this needs to track those instead.

signal scene_changing(from_path: String, to_path: String)

const HISTORY_LIMIT := 32

var _history: Array[String] = []

func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel") and not _history.is_empty():
		go_back()
		get_viewport().set_input_as_handled()

func go_to(scene: Variant) -> void:
	var path := _resolve_path(scene)
	if path.is_empty():
		return
	var current: String = _current_path()
	if current != "" and current != path:
		_history.append(current)
		if _history.size() > HISTORY_LIMIT:
			_history.pop_front()
	scene_changing.emit(current, path)
	call_deferred("_change_scene", path)

func go_back() -> bool:
	if _history.is_empty():
		return false
	var previous: String = _history.pop_back()
	scene_changing.emit(_current_path(), previous)
	call_deferred("_change_scene", previous)
	return true

func replace(scene: Variant) -> void:
	## Switch scene without pushing onto history.
	var path := _resolve_path(scene)
	if path.is_empty():
		return
	scene_changing.emit(_current_path(), path)
	call_deferred("_change_scene", path)

func clear_history() -> void:
	_history.clear()

static func _resolve_path(scene: Variant) -> String:
	if scene is PackedScene:
		return (scene as PackedScene).resource_path
	if scene is String:
		return scene
	push_error("SceneManager: expected PackedScene or String, got %s" % typeof(scene))
	return ""

func _current_path() -> String:
	if get_tree().current_scene == null:
		return ""
	return get_tree().current_scene.scene_file_path

func _change_scene(scene_path: String) -> void:
	var err: Error = get_tree().change_scene_to_file(scene_path)
	if err != OK:
		push_error("SceneManager: failed to load %s (err %d)" % [scene_path, err])

func quit() -> void:
	get_tree().quit()
