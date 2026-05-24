extends Node

## Async wrappers around the server's /auth/* endpoints and /me.
##
## All methods are awaitable and return a uniform Dictionary shape:
##
##   {success: true,  data: <parsed JSON body>, status: <int>}
##   {success: false, error: {code, message, details?}, status: <int>}
##
## Network errors / non-JSON bodies surface as success=false with a synthetic
## error code, so callers have a single code path.
##
## Server URL is hardcoded for Phase 1.3 dev. Will become env/setting-driven
## before any non-localhost deployment.

const SERVER_BASE := "http://localhost:8080"
const REQUEST_TIMEOUT_SEC := 10.0

func login(email: String, password: String) -> Dictionary:
	return await _post_json("/auth/login", {"email": email, "password": password})

func register(email: String, password: String, display_name: String) -> Dictionary:
	return await _post_json("/auth/register", {
		"email": email,
		"password": password,
		"display_name": display_name,
	})

func verify(token: String) -> Dictionary:
	return await _post_json("/auth/verify", {"token": token})

func refresh(refresh_token: String) -> Dictionary:
	return await _post_json("/auth/refresh", {"refresh_token": refresh_token})

func logout(refresh_token: String) -> Dictionary:
	return await _post_json("/auth/logout", {"refresh_token": refresh_token})

func me(access_token: String) -> Dictionary:
	var http := _new_request()
	var headers := PackedStringArray(["Authorization: Bearer " + access_token])
	var err := http.request(SERVER_BASE + "/me", headers, HTTPClient.METHOD_GET)
	if err != OK:
		http.queue_free()
		return _synthetic_error("request_failed", "HTTPRequest start error: %d" % err, 0)
	var result: Array = await http.request_completed
	http.queue_free()
	return _handle_response(result)

func _post_json(path: String, payload: Dictionary) -> Dictionary:
	var http := _new_request()
	var headers := PackedStringArray(["Content-Type: application/json"])
	var body := JSON.stringify(payload)
	var err := http.request(SERVER_BASE + path, headers, HTTPClient.METHOD_POST, body)
	if err != OK:
		http.queue_free()
		return _synthetic_error("request_failed", "HTTPRequest start error: %d" % err, 0)
	var result: Array = await http.request_completed
	http.queue_free()
	return _handle_response(result)

func _new_request() -> HTTPRequest:
	var http := HTTPRequest.new()
	http.timeout = REQUEST_TIMEOUT_SEC
	add_child(http)
	return http

func _handle_response(result: Array) -> Dictionary:
	# request_completed args: [result_code, status, headers, body]
	var result_code: int = result[0]
	var status: int = result[1]
	var body_bytes: PackedByteArray = result[3]

	if result_code != HTTPRequest.RESULT_SUCCESS:
		return _synthetic_error("request_failed", "HTTPRequest result %d" % result_code, status)

	var body_str := body_bytes.get_string_from_utf8()
	var parsed: Variant = null
	if not body_str.is_empty():
		parsed = JSON.parse_string(body_str)
		if parsed == null:
			return _synthetic_error("invalid_json", "server returned invalid JSON", status)

	if status >= 200 and status < 300:
		return {"success": true, "data": parsed, "status": status}

	# Map server error envelope into our shape; fall back to raw body if missing.
	var err_obj: Dictionary
	if parsed is Dictionary and parsed.get("error") is Dictionary:
		err_obj = parsed.error
	else:
		err_obj = {
			"code": "unknown",
			"message": body_str if not body_str.is_empty() else "no body (status %d)" % status,
		}
	return {"success": false, "error": err_obj, "status": status}

func _synthetic_error(code: String, message: String, status: int) -> Dictionary:
	return {
		"success": false,
		"error": {"code": code, "message": message},
		"status": status,
	}
