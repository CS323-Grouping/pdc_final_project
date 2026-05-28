extends Node2D

@export var reset_left_x: float = -50.0
@export var reset_right_x: float = 370.0

var cloud_speeds := {
	"MediumCloud": 4.0,
	"SmallCloud3": 7.0,
	"LargeCloud2": 2.0,
	"MediumCloud2": 5.0,
	"SmallCloud": 6.0,
}

func _process(delta: float) -> void:
	for cloud in get_children():
		if cloud is Sprite2D:
			var speed: float = cloud_speeds.get(cloud.name, 3.0)
			cloud.position.x -= speed * delta
			
			if cloud.position.x < reset_left_x:
				cloud.position.x = reset_right_x
