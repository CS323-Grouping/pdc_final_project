from network.cooldown import KickCooldownTable
from network.protocol import UINT32_MAX


def test_kick_cooldown_tiers_progress():
    table = KickCooldownTable()
    name = "PlayerOne"

    table.register_kick(name)  # 0s
    blocked, remaining = table.check("playerone")
    assert blocked is False
    assert remaining == 0

    table.register_kick(name)  # 15s
    blocked, remaining = table.check(name)
    assert blocked is True
    assert 1 <= remaining <= 15


def test_kick_cooldown_eventually_permanent():
    table = KickCooldownTable()
    name = "PlayerTwo"
    for _ in range(6):
        table.register_kick(name)

    blocked, remaining = table.check(name)
    assert blocked is True
    assert remaining == UINT32_MAX
