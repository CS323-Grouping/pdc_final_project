class_name Element extends Resource

## One gameplay piece: a platform type, a hazard, a pickup, a mechanism.
##
## Stored as `.tres` in `res://resources/elements/`. Referenced from
## `LevelEnvironment.element_set` via `EnvElementEntry`. The generator picks
## from the env's element pool, weighted, filtered by difficulty.

enum Category { PLATFORM, HAZARD, PICKUP, MECHANISM }

@export var id: StringName
@export var display_name: String = ""
@export var category: Category = Category.PLATFORM
@export var scene: PackedScene
@export var base_weight: float = 1.0
@export var min_difficulty: int = 1
@export var max_difficulty: int = 10
@export var tags: Array[StringName] = []
@export var min_horizontal_clearance: int = 0
@export var min_vertical_clearance: int = 0
