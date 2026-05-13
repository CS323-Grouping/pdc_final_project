"""
Orb pickup effect codes for HUD sync (spectators / remote players).

Mirrors durations and shield interactions from ``Player.collect_power_up`` timer fields.
Wire format: single int ``effect_id`` appended to ORB_COLLECT (see protocol).
"""

from __future__ import annotations

# Keep in sync with pack_orb_collect validation (non-negative small int).
ORB_EFFECT_UNSPECIFIED = 0
ORB_EFFECT_SPEED = 1
ORB_EFFECT_JUMP = 2
ORB_EFFECT_SHIELD = 3
ORB_EFFECT_DOUBLE_JUMP = 4
ORB_EFFECT_LAUNCH = 5
ORB_EFFECT_REVERSE_CONTROL = 6
ORB_EFFECT_SLIPPERY = 7
ORB_EFFECT_SLOW_FALLING = 8
ORB_EFFECT_HEAVY = 9
ORB_EFFECT_WEAK_JUMP = 10
ORB_EFFECT_SHIELD_BLOCKED = 11


_ACTUAL_EFFECT_TO_CODE = {
    "speed": ORB_EFFECT_SPEED,
    "jump": ORB_EFFECT_JUMP,
    "shield": ORB_EFFECT_SHIELD,
    "double_jump": ORB_EFFECT_DOUBLE_JUMP,
    "launch": ORB_EFFECT_LAUNCH,
    "reverse_control": ORB_EFFECT_REVERSE_CONTROL,
    "slippery": ORB_EFFECT_SLIPPERY,
    "slow_falling": ORB_EFFECT_SLOW_FALLING,
    "heavy": ORB_EFFECT_HEAVY,
    "weak_jump": ORB_EFFECT_WEAK_JUMP,
    "shield_blocked": ORB_EFFECT_SHIELD_BLOCKED,
}


def effect_id_from_collect_result(actual_effect: str) -> int:
    """Map ``collect_power_up`` return value to wire ``effect_id``."""
    return int(_ACTUAL_EFFECT_TO_CODE.get(actual_effect, ORB_EFFECT_UNSPECIFIED))


def is_valid_effect_id(effect_id: int) -> bool:
    return ORB_EFFECT_UNSPECIFIED <= int(effect_id) <= ORB_EFFECT_SHIELD_BLOCKED


def apply_effect_id_to_hud_timers(effect_id: int, timers: dict[str, float]) -> None:
    """
    Apply the same timer mutations as ``Player.collect_power_up`` uses for HUD labels.

    Mutates ``timers`` in place (positive float seconds remaining per label).
    """
    code = int(effect_id)
    if code == ORB_EFFECT_UNSPECIFIED:
        return
    if code == ORB_EFFECT_SHIELD_BLOCKED:
        timers.pop("Shield Aura", None)
        return

    debuff_clear_shield = {
        ORB_EFFECT_REVERSE_CONTROL,
        ORB_EFFECT_SLIPPERY,
        ORB_EFFECT_SLOW_FALLING,
        ORB_EFFECT_HEAVY,
        ORB_EFFECT_WEAK_JUMP,
    }
    if code in debuff_clear_shield:
        timers.pop("Shield Aura", None)

    if code == ORB_EFFECT_SPEED:
        timers["Speed Buff"] = 3.0
    elif code == ORB_EFFECT_JUMP:
        timers["Jump Buff"] = 3.0
    elif code == ORB_EFFECT_SHIELD:
        timers["Shield Aura"] = 15.0
    elif code == ORB_EFFECT_DOUBLE_JUMP:
        timers["Double Jump"] = 3.0
    elif code == ORB_EFFECT_LAUNCH:
        timers["Launch Boost"] = 1.0
    elif code == ORB_EFFECT_REVERSE_CONTROL:
        timers["Reverse Control"] = 5.0
    elif code == ORB_EFFECT_SLIPPERY:
        timers["Slippery"] = 5.0
    elif code == ORB_EFFECT_SLOW_FALLING:
        timers["Slow Falling"] = 5.0
    elif code == ORB_EFFECT_HEAVY:
        timers["Heavy"] = 5.0
    elif code == ORB_EFFECT_WEAK_JUMP:
        timers["Weak Jump"] = 2.0


def tick_hud_timers(dt: float, timers: dict[str, float]) -> None:
    if dt <= 0.0:
        return
    for key in list(timers.keys()):
        timers[key] = max(0.0, timers[key] - dt)
        if timers[key] <= 0.0:
            del timers[key]
