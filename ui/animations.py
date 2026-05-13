import math


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def fade_in_progress(elapsed: float, duration: float) -> float:
    if duration <= 0:
        return 1.0
    return clamp01(elapsed / duration)


def pulse01(time_s: float, period_s: float = 0.9) -> float:
    """0..1 smooth pulse for countdown / ready button emphasis."""
    if period_s <= 0:
        return 1.0
    return 0.5 + 0.5 * math.sin(2 * math.pi * time_s / period_s)


def stagger_alpha(elapsed: float, row_index: int, delay_per_row: float = 0.07, fade: float = 0.12) -> float:
    """Row reveal 0..1 for results list."""
    start = row_index * delay_per_row
    if elapsed < start:
        return 0.0
    return clamp01((elapsed - start) / fade)


def highlight_decay(current: float, dt: float, rate: float = 2.8) -> float:
    """Exponential-ish decay for roster row flashes."""
    return max(0.0, current - dt * rate)
