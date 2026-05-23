extends Button

## Reusable back button.
##
## Default behavior: SceneManager.go_back(). If history is empty (someone
## deep-linked into this scene), falls back to `fallback_scene_path` set
## per-instance in the editor.
##
## Drop this scene into any screen that needs a back button. Override `text`
## if you want a different label (e.g. "LEAVE" in a lobby, "CANCEL" in a
## modal).
##
## Note on the String-path instead of PackedScene: using PackedScene here
## would force the instancing scene to declare an ExtResource for the
## fallback target (typically main_menu.tscn), which creates a load cycle
## (main_menu → main_menu.gd preloads settings.tscn → settings.tscn loads
## back_button → ExtResource(main_menu)). String path is lazy-loaded only
## when the fallback fires, breaking the cycle.

@export_file("*.tscn") var fallback_scene_path: String = ""

func _ready() -> void:
	pressed.connect(_on_pressed)

func _on_pressed() -> void:
	if SceneManager.go_back():
		return
	if not fallback_scene_path.is_empty():
		SceneManager.go_to(fallback_scene_path)
	else:
		push_warning("BackButton: empty history and no fallback_scene_path set on %s" % get_path())
