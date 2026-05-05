from typing import Dict, List, Optional, Tuple

try:
    from network.protocol import LEFT_BEHIND_COOLDOWN_DISTANCE, LEFT_BEHIND_DISTANCE
except ModuleNotFoundError:
    from protocol import LEFT_BEHIND_COOLDOWN_DISTANCE, LEFT_BEHIND_DISTANCE  # type: ignore

Position = Tuple[float, float]


class GameEndPolicy:
    def __init__(
        self,
        left_behind_distance: float = LEFT_BEHIND_DISTANCE,
        elimination_cooldown_distance: float = LEFT_BEHIND_COOLDOWN_DISTANCE,
    ):
        self.left_behind_distance = left_behind_distance
        self.elimination_cooldown_distance = elimination_cooldown_distance
        self._cooldown_reference_id: Optional[int] = None
        self._cooldown_reference_y: Optional[float] = None

    def left_behind_candidates(self, alive_positions: Dict[int, Position]) -> List[int]:
        if len(alive_positions) < 2:
            self.clear_elimination_cooldown()
            return []

        if self._is_elimination_cooling_down(alive_positions):
            return []

        ranked = self._ranked_by_progress(alive_positions)
        last_player_id, (_last_x, last_y) = ranked[-1]
        _next_player_id, (_next_x, next_y) = ranked[-2]

        if (last_y - next_y) > self.left_behind_distance:
            return [last_player_id]
        return []

    def record_elimination(self, alive_positions: Dict[int, Position]):
        if len(alive_positions) < 2:
            self.clear_elimination_cooldown()
            return

        ranked = self._ranked_by_progress(alive_positions)
        reference_player_id, (_reference_x, reference_y) = ranked[-2]
        self._cooldown_reference_id = reference_player_id
        self._cooldown_reference_y = reference_y

    def clear_elimination_cooldown(self):
        self._cooldown_reference_id = None
        self._cooldown_reference_y = None

    def _is_elimination_cooling_down(self, alive_positions: Dict[int, Position]) -> bool:
        if self._cooldown_reference_id is None or self._cooldown_reference_y is None:
            return False

        reference_position = alive_positions.get(self._cooldown_reference_id)
        if reference_position is None:
            self.clear_elimination_cooldown()
            return False

        _reference_x, reference_y = reference_position
        if (self._cooldown_reference_y - reference_y) >= self.elimination_cooldown_distance:
            self.clear_elimination_cooldown()
            return False
        return True

    def _ranked_by_progress(self, alive_positions: Dict[int, Position]) -> List[Tuple[int, Position]]:
        return sorted(alive_positions.items(), key=lambda item: (item[1][1], item[0]))
