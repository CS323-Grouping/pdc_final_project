class_name SlotInfo extends Resource

## One slot in a generated LevelData — position, category, the element chosen
## for it, and a sub-seed the element can use for any per-instance
## randomization (sprite variant, jitter, etc.).

@export var position: Vector2i
@export var category: Element.Category = Element.Category.PLATFORM
@export var chosen_element_id: StringName
@export var instance_seed: int = 0
