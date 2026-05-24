class_name LevelEnvironment extends Resource

## A themed environment for Skyward Race matches (visuals + element bag).
##
## NOTE on the name: Godot ships a built-in `Environment` class (3D
## rendering). We renamed ours to `LevelEnvironment` to avoid the shadow. The
## vault and message-contract `environment_id` field still uses the short
## name — the rename is class-name only.
##
## Stored as `.tres` in `res://resources/environments/`. EnvironmentRegistry
## autoload discovers all envs in that folder at boot.

@export var id: StringName
@export var display_name: String = ""
@export var description: String = ""
@export var preview_icon: Texture2D                   # for lobby card + browser entry
@export var background_scene: PackedScene             # full-screen parallax background
@export var music: AudioStream
@export var palette: PalettePreset
@export var element_set: Array[EnvElementEntry] = []  # platforms + hazards + pickups
@export var ambient_particles: PackedScene            # snow flakes / lava embers / etc.
