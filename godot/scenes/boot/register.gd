extends Control

## Register screen.
##
## Submit flow:
##   1. Disable, "registering..."
##   2. AuthClient.register → on failure, show error, re-enable
##   3. AuthClient.login with same creds (auto-login) — server returned only
##      user_id from register; we still need tokens
##   4. Session.set_from_login → NetworkBackend.connect_to_server → main menu
##
## Cancel goes back to login. SceneManager's back stack handles ESC too.

const MAIN_MENU_PATH := "res://scenes/main_menu/main_menu.tscn"

func _ready() -> void:
	%SubmitButton.pressed.connect(_on_submit)
	%CancelButton.pressed.connect(_on_cancel)
	%StatusLabel.text = ""
	%EmailField.grab_focus()

func _on_submit() -> void:
	var email := (%EmailField.text as String).strip_edges()
	var display_name := (%DisplayNameField.text as String).strip_edges()
	var password := %PasswordField.text as String
	if email.is_empty() or display_name.is_empty() or password.is_empty():
		%StatusLabel.text = "all fields required"
		return

	_set_busy(true, "registering...")
	var reg_result := await AuthClient.register(email, password, display_name)
	if not reg_result.success:
		_set_busy(false, _humanize_error(reg_result.error))
		return

	%StatusLabel.text = "logging in..."
	var login_result := await AuthClient.login(email, password)
	if not login_result.success:
		_set_busy(false, "registered but auto-login failed: " + _humanize_error(login_result.error))
		return

	Session.set_from_login(login_result.data)
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
	print("[Register] connected. hello payload: %s" % NetworkBackend.hello_payload)
	SceneManager.replace(MAIN_MENU_PATH)

func _on_cancel() -> void:
	if not SceneManager.go_back():
		SceneManager.go_to("res://scenes/boot/login.tscn")

func _set_busy(busy: bool, status: String) -> void:
	%SubmitButton.disabled = busy
	%CancelButton.disabled = busy
	%StatusLabel.text = status

func _humanize_error(err: Dictionary) -> String:
	var msg := String(err.get("message", "request failed"))
	if err.get("code") == "validation_failed" and err.get("details") is Array:
		var details: Array = err.details
		if details.size() > 0 and details[0] is Dictionary:
			var first: Dictionary = details[0]
			return "%s: %s" % [first.get("field", "?"), first.get("reason", msg)]
	return msg
