"""Player control scheme (mutually exclusive key bindings)."""

CONTROL_SCHEME_WASD = "wasd"
CONTROL_SCHEME_ARROWS = "arrows"
_CONTROL_SCHEMES_FROZEN = frozenset({CONTROL_SCHEME_WASD, CONTROL_SCHEME_ARROWS})


def normalize_control_scheme(value: str) -> str:
    s = str(value or "").strip().lower()
    if s in _CONTROL_SCHEMES_FROZEN:
        return s
    return CONTROL_SCHEME_WASD


def control_scheme_display_label(scheme: str) -> str:
    s = normalize_control_scheme(scheme)
    if s == CONTROL_SCHEME_ARROWS:
        return "Arrow keys"
    return "WASD"
