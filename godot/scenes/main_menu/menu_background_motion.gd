extends Node2D

@export var cloud_reset_left_x: float = -60.0
@export var cloud_reset_right_x: float = 380.0
@export var cloud_texture_filter: CanvasItem.TextureFilter = CanvasItem.TEXTURE_FILTER_NEAREST
@export var island_texture_filter: CanvasItem.TextureFilter = CanvasItem.TEXTURE_FILTER_NEAREST
@export var disable_viewport_pixel_snap: bool = true

var _time: float = 0.0
var _viewport: Viewport
var _had_viewport_snap_settings: bool = false
var _previous_snap_transforms: bool = true
var _previous_snap_vertices: bool = true
var _clouds: Array[Sprite2D] = []
var _cloud_positions: Dictionary = {}
var _cloud_speeds: Dictionary = {
	"MediumCloud": 4.0,
	"SmallCloud3": 7.0,
	"LargeCloud2": 2.0,
	"MediumCloud2": 5.0,
	"SmallCloud": 6.0,
	"LargeCloud": 2.0,
	"LargeCloud3": 3.0,
	"SmallCloud2": 6.0,
}
var _cloud_opacities: Dictionary = {
	"LargeCloud": 1.0,
	"LargeCloud2": 0.92,
	"LargeCloud3": 0.96,
	"MediumCloud": 0.78,
	"MediumCloud2": 0.72,
	"SmallCloud": 0.56,
	"SmallCloud2": 0.52,
	"SmallCloud3": 0.60,
}

var _island_anchors: Array[Node2D] = []
var _island_base_positions: Dictionary = {}
var _island_motion: Dictionary = {
	"RightFloatingIslandAnchor": {"amplitude": 3.0, "period": 30.0, "phase": 0.0},
	"SmallIslandAnchor": {"amplitude": 1.1, "period": 16.0, "phase": 1.2},
	"SmallIslandAnchor2": {"amplitude": 0.9, "period": 18.0, "phase": 2.4},
	"SmallIslandAnchor3": {"amplitude": 1.0, "period": 17.0, "phase": 3.1},
	"MediumIslandAnchor": {"amplitude": 2.0, "period": 24.0, "phase": 0.7},
	"MediumIslandAnchor2": {"amplitude": 1.7, "period": 21.0, "phase": 1.8},
	"MediumIslandAnchor3": {"amplitude": 1.9, "period": 26.0, "phase": 2.7},
	"MediumIslandAnchor4": {"amplitude": 1.5, "period": 20.0, "phase": 3.6},
	"MediumIslandAnchor5": {"amplitude": 1.8, "period": 25.0, "phase": 4.4},
}

func _ready() -> void:
	_disable_viewport_snap()
	_capture_clouds($cloudsBack)
	_capture_clouds($cloudsFront)
	_capture_islands($floatingIslands)

func _exit_tree() -> void:
	_restore_viewport_snap()

func _process(delta: float) -> void:
	_time += delta
	_animate_clouds(delta)
	_animate_islands()

func _disable_viewport_snap() -> void:
	if not disable_viewport_pixel_snap:
		return

	_viewport = get_viewport()
	if _viewport == null:
		return

	_had_viewport_snap_settings = (
		_has_property(_viewport, "snap_2d_transforms_to_pixel")
		and _has_property(_viewport, "snap_2d_vertices_to_pixel")
	)
	if not _had_viewport_snap_settings:
		return

	_previous_snap_transforms = bool(_viewport.get("snap_2d_transforms_to_pixel"))
	_previous_snap_vertices = bool(_viewport.get("snap_2d_vertices_to_pixel"))
	_viewport.set("snap_2d_transforms_to_pixel", false)
	_viewport.set("snap_2d_vertices_to_pixel", false)

func _restore_viewport_snap() -> void:
	if _viewport == null or not _had_viewport_snap_settings:
		return

	_viewport.set("snap_2d_transforms_to_pixel", _previous_snap_transforms)
	_viewport.set("snap_2d_vertices_to_pixel", _previous_snap_vertices)

func _has_property(object: Object, property_name: String) -> bool:
	for property: Dictionary in object.get_property_list():
		if String(property.get("name", "")) == property_name:
			return true
	return false

func _capture_clouds(layer: Node) -> void:
	for child: Node in layer.get_children():
		var cloud := child as Sprite2D
		if cloud == null:
			continue

		cloud.texture_filter = cloud_texture_filter
		cloud.modulate.a = float(_cloud_opacities.get(String(cloud.name), 1.0))
		_clouds.append(cloud)
		_cloud_positions[cloud] = cloud.position

func _capture_islands(layer: Node) -> void:
	for child: Node in layer.get_children():
		var anchor := child as Node2D
		if anchor == null or not _island_motion.has(String(anchor.name)):
			continue

		_island_anchors.append(anchor)
		_island_base_positions[anchor] = anchor.position
		_apply_texture_filter_recursive(anchor, island_texture_filter)

func _apply_texture_filter_recursive(node: Node, texture_filter: CanvasItem.TextureFilter) -> void:
	var canvas_item := node as CanvasItem
	if canvas_item != null:
		canvas_item.texture_filter = texture_filter

	for child: Node in node.get_children():
		_apply_texture_filter_recursive(child, texture_filter)

func _animate_clouds(delta: float) -> void:
	for cloud: Sprite2D in _clouds:
		var base_position: Vector2 = _cloud_positions.get(cloud, cloud.position)
		var speed: float = float(_cloud_speeds.get(String(cloud.name), 3.0))
		base_position.x -= speed * delta

		if base_position.x < cloud_reset_left_x:
			base_position.x = cloud_reset_right_x

		_cloud_positions[cloud] = base_position
		cloud.position = base_position

func _animate_islands() -> void:
	for anchor: Node2D in _island_anchors:
		var base_position: Vector2 = _island_base_positions.get(anchor, anchor.position)
		var settings: Dictionary = _island_motion.get(String(anchor.name), {})
		var amplitude: float = float(settings.get("amplitude", 1.0))
		var period: float = maxf(float(settings.get("period", 20.0)), 0.001)
		var phase: float = float(settings.get("phase", 0.0))

		anchor.position = Vector2(
			base_position.x,
			base_position.y + sin((_time / period * TAU) + phase) * amplitude
		)
