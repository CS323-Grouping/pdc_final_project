class_name EnvElementEntry extends Resource

## One entry in a LevelEnvironment's `element_set`. The element belongs to that
## env's pool; the weight_override (if > 0) lets the same element have
## different spawn frequency in different envs without editing the element
## itself.

@export var element: Element
@export var weight_override: float = -1.0   # -1 means "use element.base_weight"
