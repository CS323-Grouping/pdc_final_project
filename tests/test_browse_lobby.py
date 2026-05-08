from types import SimpleNamespace

from network import protocol
from states.browse_lobby import BrowseLobbyState


def make_state(reconnect_ticket=None):
    context = SimpleNamespace(reconnect_ticket=reconnect_ticket)
    return BrowseLobbyState(machine=SimpleNamespace(), context=context)


def make_room(state=protocol.STATE_IN_GAME):
    return SimpleNamespace(
        state=state,
        addr="127.0.0.1",
        game_port=5555,
        room_name="RoomOne",
    )


def test_in_game_room_is_not_reconnectable_without_ticket():
    state = make_state(reconnect_ticket=None)

    assert not state._can_reconnect(make_room(protocol.STATE_IN_GAME))
    assert not state._joinable(make_room(protocol.STATE_IN_GAME))


def test_in_game_room_is_reconnectable_with_matching_ticket():
    ticket = SimpleNamespace(
        addr="127.0.0.1",
        port=5555,
        room_name="RoomOne",
    )
    state = make_state(reconnect_ticket=ticket)

    assert state._can_reconnect(make_room(protocol.STATE_IN_GAME))
    assert state._joinable(make_room(protocol.STATE_IN_GAME))


def test_countdown_room_is_not_joinable_or_reconnectable():
    ticket = SimpleNamespace(
        addr="127.0.0.1",
        port=5555,
        room_name="RoomOne",
    )
    state = make_state(reconnect_ticket=ticket)

    assert not state._can_reconnect(make_room(protocol.STATE_COUNTDOWN))
    assert not state._joinable(make_room(protocol.STATE_COUNTDOWN))
