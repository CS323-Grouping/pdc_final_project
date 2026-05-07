from network.room_state import RoomState
from network import protocol


def test_room_state_tracks_join_and_leave():
    room_state = RoomState(room_name="TestRoom", game_port=5555)

    player_id, is_new = room_state.add_or_get_player(("127.0.0.1", 12001), "Alpha")
    assert is_new is True
    assert player_id == 0

    same_id, is_new_again = room_state.add_or_get_player(("127.0.0.1", 12001), "Alpha")
    assert is_new_again is False
    assert same_id == player_id

    snapshot = room_state.snapshot()
    assert snapshot.current_players == 1
    assert snapshot.room_name == "TestRoom"

    room_state.remove_player(player_id)
    assert room_state.snapshot().current_players == 0


def test_room_state_peer_listing_excludes_sender():
    room_state = RoomState(room_name="TestRoom", game_port=5555)
    addr_1 = ("127.0.0.1", 12001)
    addr_2 = ("127.0.0.1", 12002)

    room_state.add_or_get_player(addr_1, "Alpha")
    room_state.add_or_get_player(addr_2, "Bravo")

    peers = room_state.peers(exclude_addr=addr_1)
    assert peers == [addr_2]


def test_room_state_reconnects_disconnected_alive_player_to_new_addr():
    room_state = RoomState(room_name="TestRoom", game_port=5555)
    old_addr = ("127.0.0.1", 12001)
    new_addr = ("127.0.0.1", 12055)

    player_id, _is_new = room_state.add_or_get_player(old_addr, "Alpha")
    token = room_state.session_token(player_id)
    assert token is not None
    room_state.enter_game()
    room_state.update_position(player_id, 44.0, 90.0)
    room_state.mark_disconnected(player_id, now=10.0, grace_seconds=protocol.RECONNECT_GRACE_SECONDS)

    assert room_state.disconnected_alive_ids() == [player_id]
    position = room_state.reconnect_player(new_addr, player_id, token, now=20.0)

    assert position == (44.0, 90.0)
    assert room_state.get_player_id_by_addr(new_addr) == player_id
    assert room_state.disconnected_alive_ids() == []


def test_room_state_reconnect_rejects_bad_or_expired_token():
    room_state = RoomState(room_name="TestRoom", game_port=5555)
    player_id, _is_new = room_state.add_or_get_player(("127.0.0.1", 12001), "Alpha")
    token = room_state.session_token(player_id)
    assert token is not None
    room_state.enter_game()
    room_state.mark_disconnected(player_id, now=10.0, grace_seconds=5.0)

    assert room_state.reconnect_player(("127.0.0.1", 12002), player_id, token + 1, now=11.0) is None
    assert room_state.reconnect_player(("127.0.0.1", 12002), player_id, token, now=16.0) is None


def test_room_state_reconnects_disconnected_alive_player_by_name():
    room_state = RoomState(room_name="TestRoom", game_port=5555)
    player_id, _is_new = room_state.add_or_get_player(("127.0.0.1", 12001), "Alpha")
    token = room_state.session_token(player_id)
    assert token is not None
    room_state.enter_game()
    room_state.update_position(player_id, 88.0, 42.0)
    room_state.mark_disconnected(player_id, now=10.0, grace_seconds=30.0)

    reconnected = room_state.reconnect_player_by_name(("127.0.0.1", 12044), "alpha", now=18.0)

    assert reconnected == (player_id, (88.0, 42.0), token)
    assert room_state.get_player_id_by_addr(("127.0.0.1", 12044)) == player_id
    assert room_state.disconnected_alive_ids() == []


def test_room_state_checks_connected_names_case_insensitively():
    room_state = RoomState(room_name="TestRoom", game_port=5555)
    addr = ("127.0.0.1", 12001)

    room_state.add_or_get_player(addr, "Alpha")

    assert room_state.connected_player_name_taken("alpha")
    assert not room_state.connected_player_name_taken("alpha", exclude_addr=addr)


def test_enter_game_resets_connected_player_positions_for_rematch():
    room_state = RoomState(room_name="TestRoom", game_port=5555)
    first_id, _ = room_state.add_or_get_player(("127.0.0.1", 12001), "Alpha")
    second_id, _ = room_state.add_or_get_player(("127.0.0.1", 12002), "Bravo")

    room_state.enter_game()
    room_state.update_position(first_id, 180.0, -600.0)
    room_state.update_position(second_id, 80.0, -560.0)
    room_state.reset_for_lobby()
    room_state.enter_game()

    positions = room_state.connected_positions()
    assert positions[first_id] == (100.0, 100.0)
    assert positions[second_id] == (112.0, 100.0)


def test_ready_state_reports_whether_value_changed():
    room_state = RoomState(room_name="TestRoom", game_port=5555)
    player_id, _ = room_state.add_or_get_player(("127.0.0.1", 12001), "Alpha")

    assert room_state.set_ready(player_id, False) is False
    assert room_state.set_ready(player_id, True) is True
    assert room_state.set_ready(player_id, True) is False


def test_room_state_reports_timed_out_connected_players():
    room_state = RoomState(room_name="TestRoom", game_port=5555)
    active_id, _ = room_state.add_or_get_player(("127.0.0.1", 12001), "Alpha")
    stale_id, _ = room_state.add_or_get_player(("127.0.0.1", 12002), "Bravo")

    room_state.touch_player(active_id, now=10.0)
    room_state.touch_player(stale_id, now=0.0)

    assert room_state.timed_out_connected_ids(now=12.0, timeout_seconds=8.0) == [stale_id]
