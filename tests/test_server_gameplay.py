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


def test_eliminated_player_state_is_not_rebroadcast():
    server, room_state, sock, (player_id, addr), (_other_id, other_addr), (_third_id, _third_addr) = _server_with_started_room()
    room_state.update_position(player_id, 20.0, 20.0)
    server.eliminate_player(player_id)
    sock.sent.clear()

    server.handle_player_state(protocol.pack_player_state(200.0, 200.0, player_id, "walk_right"), addr)

    assert room_state.get_position(player_id) == (20.0, 20.0)
    assert not any(protocol.tag_of(payload) == protocol.PLAYER_STATE and sent_addr == other_addr for payload, sent_addr in sock.sent)
