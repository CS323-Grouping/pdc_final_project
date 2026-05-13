"""
Client-side network telemetry foundation for RTT quality, loss, and throughput.

Intended to scale toward production netcode observability (HUD, logs, later exporters).
All math is O(n) on a bounded window (n <= maxlen) for stable per-frame cost.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

# Default RTT samples kept for rolling mean / percentiles / jitter (tunable per title).
RTT_WINDOW_DEFAULT_SIZE = 128


def _percentile_nearest_rank(sorted_samples: list[float], p: float) -> float | None:
    """Nearest-rank percentile in [0, 100]; ``p==50`` ≈ median."""
    n = len(sorted_samples)
    if n == 0:
        return None
    p = max(0.0, min(100.0, p))
    idx = int(math.ceil((p / 100.0) * n) - 1)
    idx = max(0, min(n - 1, idx))
    return sorted_samples[idx]


@dataclass
class LatencyWindow:
    """
    Fixed-size rolling buffer of RTT samples (milliseconds).

    Provides window mean/min/max, jitter (population stdev), and p50/p95 for
    SLO-style dashboards (small ``maxlen`` keeps percentiles cheap).
    """

    maxlen: int = RTT_WINDOW_DEFAULT_SIZE

    def __post_init__(self) -> None:
        cap = max(4, int(self.maxlen))
        self._samples: deque[float] = deque(maxlen=cap)

    def add(self, rtt_ms: float) -> None:
        self._samples.append(float(rtt_ms))

    def clear(self) -> None:
        self._samples.clear()

    def count(self) -> int:
        return len(self._samples)

    def mean(self) -> float | None:
        if not self._samples:
            return None
        return sum(self._samples) / len(self._samples)

    def minimum(self) -> float | None:
        if not self._samples:
            return None
        return min(self._samples)

    def maximum(self) -> float | None:
        if not self._samples:
            return None
        return max(self._samples)

    def stdev(self) -> float | None:
        """Population standard deviation of samples in the window (jitter)."""
        n = len(self._samples)
        if n < 2:
            return None
        m = sum(self._samples) / n
        var = sum((x - m) ** 2 for x in self._samples) / n
        return math.sqrt(var)

    def p50(self) -> float | None:
        if not self._samples:
            return None
        return _percentile_nearest_rank(sorted(self._samples), 50.0)

    def p95(self) -> float | None:
        if not self._samples:
            return None
        return _percentile_nearest_rank(sorted(self._samples), 95.0)
