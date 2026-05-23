extends Node

## Live (non-persistent) session state — JWT, user identity, current room.
##
## Phase 1.3 ships in-memory only — no disk persistence. Phase 7 adds
## `user://session.cfg` so refresh tokens survive relaunch (auto-login).
## Nothing here should outlive the process today.

var user_id: String = ""
var display_name: String = ""
var email: String = ""
var verified: bool = false
var jwt: String = ""
var refresh_token: String = ""
var current_room_id: String = ""
var current_room_code: String = ""

signal logged_in
signal logged_out
signal room_changed(new_room_id: String)

func is_authenticated() -> bool:
	return jwt != ""

## Populate from a successful /auth/login or /auth/refresh response body.
## Pass the parsed JSON Dictionary as-is (the `data` field of AuthClient's
## return value).
func set_from_login(data: Dictionary) -> void:
	var user: Dictionary = data.get("user", {}) if data.get("user") is Dictionary else {}
	user_id = String(user.get("id", ""))
	display_name = String(user.get("display_name", ""))
	email = String(user.get("email", ""))
	verified = bool(user.get("verified", false))
	jwt = String(data.get("access_token", ""))
	refresh_token = String(data.get("refresh_token", ""))
	logged_in.emit()

## Replace just the token pair (used after /auth/refresh — user record is
## unchanged).
func set_tokens(access_token: String, refresh: String) -> void:
	jwt = access_token
	refresh_token = refresh

func set_room(room_id: String, room_code: String = "") -> void:
	current_room_id = room_id
	current_room_code = room_code
	room_changed.emit(current_room_id)

func clear() -> void:
	user_id = ""
	display_name = ""
	email = ""
	verified = false
	jwt = ""
	refresh_token = ""
	current_room_id = ""
	current_room_code = ""
	logged_out.emit()
