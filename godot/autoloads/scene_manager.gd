extends Node

## Centralized scene transitions with a simple back stack.
##
## Use `SceneManager.go_to(scene_path)` to navigate forward — pushes current
## scene onto history. App-level screen navigation should pass a String
## resource path. Passing PackedScene is supported for narrow non-cyclic cases,
## but String paths avoid preload cycles between screens.
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
const PACKED_SCENE_LABEL := "<packed_scene>"

var _history: Array[String] = []

func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel") and not _history.is_empty():
		go_back()
		get_viewport().set_input_as_handled()

func go_to(scene: Variant) -> void:
	var target := _resolve_target(scene)
	if target.is_empty():
		return
	var path := String(target.get("path", ""))
	var label := path if not path.is_empty() else PACKED_SCENE_LABEL
	var current: String = _current_path()
	if current != "" and current != label:
		_history.append(current)
		if _history.size() > HISTORY_LIMIT:
			_history.pop_front()
	scene_changing.emit(current, label)
	call_deferred("_change_scene_target", target)

func go_back() -> bool:
	if _history.is_empty():
		return false
	var previous: String = _history.pop_back()
	scene_changing.emit(_current_path(), previous)
	call_deferred("_change_scene", previous)
	return true

func replace(scene: Variant) -> void:
	## Switch scene without pushing onto history.
	var target := _resolve_target(scene)
	if target.is_empty():
		return
	var path := String(target.get("path", ""))
	var label := path if not path.is_empty() else PACKED_SCENE_LABEL
	print("[SceneManager] replace requested -> '%s'" % label)
	scene_changing.emit(_current_path(), label)
	call_deferred("_change_scene_target", target)

func clear_history() -> void:
	_history.clear()

static func _resolve_target(scene: Variant) -> Dictionary:
	if scene is PackedScene:
		var packed := scene as PackedScene
		return {
			"packed": packed,
			"path": packed.resource_path,
		}
	if scene is String:
		var path := String(scene)
		if path.is_empty():
			push_error("SceneManager: empty scene path")
			return {}
		return {"path": path}
	push_error("SceneManager: expected PackedScene or String, got %s" % typeof(scene))
	return {}

func _current_path() -> String:
	if get_tree().current_scene == null:
		return ""
	return get_tree().current_scene.scene_file_path

func _change_scene(scene_path: String) -> void:
	print("[SceneManager] _change_scene -> %s (current=%s)" % [scene_path, _current_path()])
	var err: Error = get_tree().change_scene_to_file(scene_path)
	print("[SceneManager] change_scene_to_file('%s') returned %d" % [scene_path, err])
	if err != OK:
		push_error("SceneManager: failed to load %s (err %d)" % [scene_path, err])

func _change_scene_target(target: Dictionary) -> void:
	var packed: PackedScene = target.get("packed", null) as PackedScene
	if packed != null:
		var path := String(target.get("path", ""))
		var label := path if not path.is_empty() else PACKED_SCENE_LABEL
		if not packed.can_instantiate():
			push_error("SceneManager: packed scene %s has no instantiable state; use a String path or break preload cycles" % label)
			return
		print("[SceneManager] _change_scene_packed -> %s (current=%s)" % [label, _current_path()])
		var packed_err: Error = get_tree().change_scene_to_packed(packed)
		print("[SceneManager] change_scene_to_packed('%s') returned %d" % [label, packed_err])
		if packed_err != OK:
			push_error("SceneManager: failed to load packed scene %s (err %d)" % [label, packed_err])
		return
	_change_scene(String(target.get("path", "")))

func quit() -> void:
	get_tree().quit()
