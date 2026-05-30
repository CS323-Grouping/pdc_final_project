extends GutTest

func test_packed_scene_without_resource_path_is_valid_target_when_instantiable() -> void:
	var scene := PackedScene.new()
	var root := Node.new()
	root.name = "PackedOnlyScene"
	var err := scene.pack(root)
	root.free()

	assert_eq(err, OK)
	assert_eq(scene.resource_path, "")
	var target := SceneManager._resolve_target(scene)
	assert_false(target.is_empty())
	assert_true(target.get("packed") is PackedScene)
	assert_eq(String(target.get("path", "")), "")

func test_empty_packed_scene_is_not_instantiable() -> void:
	var scene := PackedScene.new()
	assert_false(scene.can_instantiate())
