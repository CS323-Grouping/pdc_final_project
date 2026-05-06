from network.end_policy import GameEndPolicy


def test_left_behind_candidates_are_detected():
    policy = GameEndPolicy(left_behind_distance=100.0)
    alive_positions = {
        1: (0.0, 100.0),
        2: (0.0, 150.0),
        3: (0.0, 260.0),
    }

    assert policy.left_behind_candidates(alive_positions) == [3]
