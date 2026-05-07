import time

from network import protocol
from network.room_state import RoomState
from network.server import LobbyServer


class FakeSocket:
    def __init__(self):
        self.sent = []

    def sendto(self, payload, addr):
        self.sent.append((payload, addr))


def _server_with_started_room():
    room_state = RoomState(room_name="TestRoom", game_port=5555)
    addr_a = ("127.0.0.1", 12001)
    addr_b = ("127.0.0.1", 12002)
    addr_c = ("127.0.0.1", 12003)
    id_a, _ = room_state.add_or_get_player(addr_a, "Alpha")
    id_b, _ = room_state.add_or_get_player(addr_b, "Bravo")
    id_c, _ = room_state.add_or_get_player(addr_c, "Charlie")
    room_state.state = protocol.STATE_IN_GAME
    room_state.enter_game()
    sock = FakeSocket()
    server = LobbyServer(sock, room_state, countdown_seconds=0.0)
    return server, room_state, sock, (id_a, addr_a), (id_b, addr_b), (id_c, addr_c)


def test_name_only_reconnect_claims_single_disconnected_slot():
    server, room_state, sock, (player_id, _old_addr), (_other_id, _other_addr), (_third_id, _third_addr) = _server_with_started_room()
    new_addr = ("127.0.0.1", 12055)
    room_state.update_position(player_id, 55.0, 77.0)
    room_state.mark_disconnected(player_id, now=time.monotonic(), grace_seconds=30.0)
    room_state.state = protocol.STATE_PAUSED

    server.handle_reconnect(protocol.pack_reconnect(-1, 0, "Alpha"), new_addr)

    assert room_state.get_player_id_by_addr(new_addr) == player_id
    tags = [protocol.tag_of(payload) for payload, addr in sock.sent if addr == new_addr]
    assert protocol.SESSION in tags
    assert protocol.RECONNECT_OK in tags


def test_handle_conn_rejects_case_insensitive_duplicate_player_name():
    room_state = RoomState(room_name="TestRoom", game_port=5555)
    room_state.add_or_get_player(("127.0.0.1", 12001), "Alpha")
    sock = FakeSocket()
    server = LobbyServer(sock, room_state, countdown_seconds=0.0)
    duplicate_addr = ("127.0.0.1", 12002)

    server.handle_conn(protocol.pack_conn("alpha"), duplicate_addr)

    assert room_state.connected_count() == 1
    assert protocol.safe_unpack_conno(sock.sent[0][0]) == (
        protocol.CONNO,
        protocol.CONNO_REASON_NAME_TAKEN,
        0,
    )


def test_lobby_replays_cached_avatar_to_late_joiner():
    room_state = RoomState(room_name="TestRoom", game_port=5555)
    alpha_addr = ("127.0.0.1", 12001)
    bravo_addr = ("127.0.0.1", 12002)
    alpha_id, _ = room_state.add_or_get_player(alpha_addr, "Alpha")
    _bravo_id, _ = room_state.add_or_get_player(bravo_addr, "Bravo")
    sock = FakeSocket()
    server = LobbyServer(sock, room_state, countdown_seconds=0.0)
    avatar_id = 77
    payload = b"avatar-payload"

    server.handle_avatar_header(
        protocol.pack_avatar_header(alpha_id, avatar_id, 1, len(payload)),
        alpha_addr,
    )
    server.handle_avatar_chunk(
        protocol.pack_avatar_chunk(alpha_id, avatar_id, 0, 1, payload),
        alpha_addr,
    )
    late_addr = ("127.0.0.1", 12003)
    sock.sent.clear()

    server.handle_conn(protocol.pack_conn("Charlie"), late_addr)

    late_packets = [packet for packet, addr in sock.sent if addr == late_addr]
    assert any(
        protocol.safe_unpack_avatar_header(packet) == (
            protocol.AVATAR_HEADER,
            alpha_id,
            avatar_id,
            1,
            len(payload),
            protocol.DEFAULT_MODEL_TYPE,
            protocol.DEFAULT_MODEL_COLOR,
        )
        for packet in late_packets
    )
    assert any(
        protocol.safe_unpack_avatar_chunk(packet) == (
            protocol.AVATAR_CHUNK,
            alpha_id,
            avatar_id,
            0,
            1,
            payload,
        )
        for packet in late_packets
    )


def test_eliminated_player_state_is_not_rebroadcast():
    server, room_state, sock, (player_id, addr), (_other_id, other_addr), (_third_id, _third_addr) = _server_with_started_room()
    room_state.update_position(player_id, 20.0, 20.0)
    server.eliminate_player(player_id)
    sock.sent.clear()

    server.handle_player_state(protocol.pack_player_state(200.0, 200.0, player_id, "walk_right"), addr)

    assert room_state.get_position(player_id) == (20.0, 20.0)
    assert not any(protocol.tag_of(payload) == protocol.PLAYER_STATE and sent_addr == other_addr for payload, sent_addr in sock.sent)


def test_tick_in_game_eliminates_left_behind_player():
    server, room_state, sock, (leader_id, _leader_addr), (_near_id, _near_addr), (behind_id, _behind_addr) = _server_with_started_room()
    room_state.update_position(leader_id, 100.0, 100.0)
    room_state.update_position(_near_id, 100.0, 260.0)
    room_state.update_position(behind_id, 100.0, 1100.0)
    sock.sent.clear()

    server.tick_in_game()

    assert not room_state.is_alive(behind_id)
    assert any(
        protocol.safe_unpack_elim(payload) == (protocol.ELIM, behind_id, 3)
        for payload, _addr in sock.sent
    )


def test_goal_finish_and_later_elimination_use_distinct_placements():
    room_state = RoomState(room_name="TestRoom", game_port=5555)
    players = []
    for index, name in enumerate(("Alpha", "Bravo", "Charlie", "Delta")):
        addr = ("127.0.0.1", 12100 + index)
        player_id, _ = room_state.add_or_get_player(addr, name)
        players.append((player_id, addr))
    room_state.state = protocol.STATE_IN_GAME
    room_state.enter_game()
    sock = FakeSocket()
    server = LobbyServer(sock, room_state, countdown_seconds=0.0)
    server._match_player_count = 4

    first_id, first_addr = players[0]
    fallen_id, _fallen_addr = players[1]
    behind_id, _behind_addr = players[3]

    server.eliminate_player(fallen_id)
    server.handle_goal(protocol.pack_goal(first_id), first_addr)
    server.eliminate_player(behind_id)

    placements = {player_id: placement for player_id, placement, _name in room_state.standings()}
    assert placements[first_id] == 1
    assert placements[fallen_id] == 4
    assert placements[behind_id] == 3


def test_eliminated_host_disconnect_closes_room_for_remaining_clients():
    server, room_state, sock, (host_id, host_addr), (alive_id, alive_addr), (
        observer_id,
        observer_addr,
    ) = _server_with_started_room()
    server.eliminate_player(host_id)
    server.eliminate_player(observer_id)
    sock.sent.clear()

    server.handle_disconnect(protocol.pack_packet(protocol.DISCONNECT, 0.0, 0.0, host_id), host_addr)

    assert not server.running
    sent_by_addr = {
        addr: [protocol.tag_of(payload) for payload, sent_addr in sock.sent if sent_addr == addr]
        for addr in (alive_addr, observer_addr)
    }
    assert protocol.KICKED in sent_by_addr[alive_addr]
    assert protocol.KICKED in sent_by_addr[observer_addr]
