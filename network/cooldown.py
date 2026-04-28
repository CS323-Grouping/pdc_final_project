import math
import time
from typing import Dict, Optional, Tuple

try:
    from network.protocol import UINT32_MAX
except ModuleNotFoundError:
    from protocol import UINT32_MAX  # type: ignore

KICK_COOLDOWNS = (0, 15, 30, 60, 300, math.inf)


class KickCooldownTable:
    def __init__(self):
        self._kick_counts: Dict[str, int] = {}
        self._blocked_until: Dict[str, float] = {}

    def register_kick(self, player_name: str):
        key = player_name.lower()
        kick_count = self._kick_counts.get(key, 0) + 1
        self._kick_counts[key] = kick_count

        cooldown = KICK_COOLDOWNS[min(kick_count - 1, len(KICK_COOLDOWNS) - 1)]
        if cooldown == math.inf:
            self._blocked_until[key] = math.inf
        elif cooldown > 0:
            self._blocked_until[key] = time.monotonic() + cooldown
        else:
            self._blocked_until[key] = 0.0

    def check(self, player_name: str) -> Tuple[bool, int]:
        key = player_name.lower()
        if key not in self._kick_counts:
            return False, 0

        block_until = self._blocked_until.get(key, 0.0)
        if block_until == math.inf:
            return True, UINT32_MAX

        now = time.monotonic()
        if now < block_until:
            remaining = max(1, int(round(block_until - now)))
            return True, remaining

        return False, 0
