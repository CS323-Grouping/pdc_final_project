class_name LevelElement extends Node2D

## Base class for every spawnable level element (platforms, hazards, pickups,
## mechanisms). LevelPopulator instantiates element scenes and casts their
## roots to LevelElement — anything that doesn't extend this class is rejected
## at populate time rather than silently failing.
##
## Override `init_with_seed` if the element needs per-spawn randomization
## (visual variant, slight jitter, etc.). Default is a no-op so most elements
## don't need to implement it.

var element_id: StringName = &""
var slot_index: int = -1
var network_id: String = ""

func init_with_seed(_seed: int) -> void:
	pass
