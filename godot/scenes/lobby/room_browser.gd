extends Control

## Public room browser — placeholder.
##
## Phase 3 delivers the live list (subscribed via WS to GET /rooms updates) and
## per-card join action. For now, 4 static placeholder cards + the two forward
## actions: CREATE and JOIN BY CODE. BackButton handles back nav.
##
## Cards are focusable Panels — keyboard/controller users can Tab through them
## and activate with `ui_accept` (Enter/Space by default).

const CREATE_ROOM_SCENE: PackedScene = preload("res://scenes/lobby/create_room.tscn")
const JOIN_BY_CODE_SCENE: PackedScene = preload("res://scenes/lobby/join_by_code.tscn")
const LOBBY_SCENE: PackedScene = preload("res://scenes/lobby/skyward_lobby.tscn")

func _ready() -> void:
	%CreateRoomButton.pressed.connect(_on_create_pressed)
	%JoinByCodeButton.pressed.connect(_on_join_pressed)
	# Placeholder: clicking (or pressing ui_accept on focused) card jumps to lobby.
	# Phase 3 will instead call join_room({code}) and wait for join_ok.
	for card in [%RoomCard1, %RoomCard2, %RoomCard3, %RoomCard4]:
		card.gui_input.connect(_on_card_input)

func _on_create_pressed() -> void:
	SceneManager.go_to(CREATE_ROOM_SCENE)

func _on_join_pressed() -> void:
	SceneManager.go_to(JOIN_BY_CODE_SCENE)

func _on_card_input(event: InputEvent) -> void:
	var activate := false
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		activate = true
	elif event.is_action_pressed("ui_accept"):
		activate = true
	if activate:
		SceneManager.go_to(LOBBY_SCENE)
