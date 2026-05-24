class_name LevelData extends Resource

## Output of LevelGenerator.generate(env, difficulty, seed). Pure data —
## position + element id per slot, env-agnostic to instantiate. LevelPopulator
## walks this to spawn live scenes.
##
## Same (env_id, difficulty, seed) MUST produce byte-identical LevelData on
## every machine — that's the property the GUT test verifies in Phase 4a.

@export var env_id: StringName
@export var difficulty: int = 1
@export var seed: int = 0
@export var total_height: int = 600
@export var slots: Array[SlotInfo] = []
