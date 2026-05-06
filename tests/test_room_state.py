from network.room_state import RoomState


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
