from network.end_policy import GameEndPolicy


def test_left_behind_candidates_are_detected():
    policy = GameEndPolicy(left_behind_distance=100.0)
    alive_positions = {
        1: (0.0, 100.0),
        2: (0.0, 150.0),
        3: (0.0, 260.0),
    }

    assert policy.left_behind_candidates(alive_positions) == [3]


def test_left_behind_uses_player_immediately_ahead():
    policy = GameEndPolicy(left_behind_distance=100.0)
    alive_positions = {
        1: (0.0, 100.0),
        2: (0.0, 800.0),
        3: (0.0, 850.0),
    }

    assert policy.left_behind_candidates(alive_positions) == []


def test_left_behind_elimination_cooldown_waits_for_race_progress():
    policy = GameEndPolicy(left_behind_distance=100.0, elimination_cooldown_distance=200.0)

    policy.record_elimination({
        1: (0.0, 100.0),
        2: (0.0, 150.0),
    })

    assert policy.left_behind_candidates({
        1: (0.0, 50.0),
        2: (0.0, 260.0),
    }) == []
    assert policy.left_behind_candidates({
        1: (0.0, -100.0),
        2: (0.0, 260.0),
    }) == [2]
