extends Control

## Login screen — first scene the app boots into (see project.godot's
## run/main_scene).
##
## Submit flow:
##   1. Disable button, show "logging in…"
##   2. AuthClient.login → on failure, show server error, re-enable
##   3. Session.set_from_login
##   4. NetworkBackend.connect_to_server (opens WS, awaits hello)
##   5. SceneManager.replace(main_menu) — `replace` so BACK from main_menu
##      doesn't return to the login screen.
##
## Phase 1.3 has no auto-login. Phase 7 adds: check user://session.cfg for a
## refresh_token, attempt /auth/refresh on boot, skip this scene on success.

const REGISTER_PATH := "res://scenes/boot/register.tscn"
const MAIN_MENU_PATH := "res://scenes/main_menu/main_menu.tscn"

var _busy := false

func _ready() -> void:
	%SubmitButton.pressed.connect(_on_submit)
	%RegisterLink.pressed.connect(_on_register_link)
	%EmailField.text_submitted.connect(_on_text_submitted)
	%PasswordField.text_submitted.connect(_on_text_submitted)
	%StatusLabel.text = ""
	%EmailField.grab_focus()

func _on_text_submitted(_text: String) -> void:
	_on_submit()

func _on_submit() -> void:
	if _busy:
		return
	var email := (%EmailField.text as String).strip_edges()
	var password := %PasswordField.text as String
	if email.is_empty() or password.is_empty():
		%StatusLabel.text = "email and password required"
		return

	_set_busy(true, "logging in...")
	var result := await AuthClient.login(email, password)
	if not result.success:
		_set_busy(false, _humanize_error(result.error))
		return

	Session.set_from_login(result.data)
	%StatusLabel.text = "connecting..."
	var ok := await NetworkBackend.connect_to_server(Session.jwt)
	if not ok:
		var connect_error := NetworkBackend.last_error_message
		if connect_error.is_empty():
			connect_error = "could not reach game server"
		Session.clear()
		_set_busy(false, connect_error)
		return

	_set_busy(false, "")
	print("[Login] connected. hello payload: %s" % NetworkBackend.hello_payload)
	SceneManager.replace(MAIN_MENU_PATH)

func _on_register_link() -> void:
	if _busy:
		return
	SceneManager.go_to(REGISTER_PATH)

func _set_busy(busy: bool, status: String) -> void:
	_busy = busy
	%SubmitButton.disabled = busy
	%RegisterLink.disabled = busy
	%StatusLabel.text = status

func _humanize_error(err: Dictionary) -> String:
	var msg := String(err.get("message", "login failed"))
	# Validation errors include per-field details — surface the first.
	if err.get("code") == "validation_failed" and err.get("details") is Array:
		var details: Array = err.details
		if details.size() > 0 and details[0] is Dictionary:
			var first: Dictionary = details[0]
			return "%s: %s" % [first.get("field", "?"), first.get("reason", msg)]
	return msg
