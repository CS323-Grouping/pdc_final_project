from typing import Dict, List, Tuple

Position = Tuple[float, float]


class GameEndPolicy:

    def left_behind_candidates(self, alive_positions: Dict[int, Position]) -> List[int]:
        return []
