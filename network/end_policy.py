from typing import Dict, List, Tuple

try:
    from network.protocol import LEFT_BEHIND_DISTANCE
except ModuleNotFoundError:
    from protocol import LEFT_BEHIND_DISTANCE  # type: ignore

Position = Tuple[float, float]


class GameEndPolicy:
    def __init__(self, left_behind_distance: float = LEFT_BEHIND_DISTANCE):
        self.left_behind_distance = left_behind_distance

    def left_behind_candidates(self, alive_positions: Dict[int, Position]) -> List[int]:
        if not alive_positions:
            return []

        leader_y = min(position[1] for position in alive_positions.values())
        eliminated = [
            player_id
            for player_id, position in alive_positions.items()
            if (position[1] - leader_y) > self.left_behind_distance
        ]
        eliminated.sort()
        return eliminated
