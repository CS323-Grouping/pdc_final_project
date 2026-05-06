"""Round-trip and rejection tests for `network/protocol.py` wire format."""

import struct

import pytest

from network import protocol


def test_pack_unpack_round_trip_pos():
    packet = protocol.pack_packet(protocol.POSITION, 12.5, -3.25, 7)
    unpacked = protocol.safe_unpack(packet)

    assert unpacked is not None
    cmd, x, y, player_id = unpacked
    assert cmd == protocol.POSITION
    assert x == pytest.approx(12.5)
    assert y == pytest.approx(-3.25)
    assert player_id == 7


def test_safe_unpack_rejects_malformed_packet():
    assert protocol.safe_unpack(b"bad-data") is None
    assert protocol.safe_unpack(b"") is None


def test_tag_of():
    assert protocol.tag_of(b"abcdextra") == b"abcd"
    assert protocol.tag_of(b"ab") is None
    assert protocol.tag_of(b"") is None


def test_beacon_round_trip():
    packet = protocol.pack_beacon(
        protocol.PROTO_VERSION,
        cur_players=3,
        max_players=5,
        room_state=protocol.STATE_LOBBY,
        game_port=5555,
        room_name="AlphaRoom",
    )
    unpacked = protocol.safe_unpack_beacon(packet)

    assert unpacked is not None
    tag, version, cur, max_players, state, game_port, room_name = unpacked
    assert tag == protocol.BEACON
    assert version == protocol.PROTO_VERSION
    assert cur == 3
    assert max_players == 5
    assert state == protocol.STATE_LOBBY
    assert game_port == 5555
    assert room_name == "AlphaRoom"


def test_safe_unpack_beacon_rejects_malformed_packet():
    assert protocol.safe_unpack_beacon(b"bad-data") is None


def _pad_name(name: str) -> bytes:
    encoded = name.encode("ascii", errors="ignore")[: protocol.MAX_NAME_LEN]
    return encoded.ljust(protocol.MAX_NAME_LEN, b"\0")


def test_beacon_wrong_tag_rejected():
    raw = struct.pack(
        protocol.FRMT_BEACON,
        b"NOPE",
        protocol.PROTO_VERSION,
        1,
        5,
        0,
        5555,
        _pad_name("X"),
    )
    assert protocol.safe_unpack_beacon(raw) is None


def test_conn_round_trip():
    packet = protocol.pack_conn("PlayerOne")
    unpacked = protocol.safe_unpack_conn(packet)
    assert unpacked is not None
    _tag, proto_version, name = unpacked
    assert proto_version == protocol.PROTO_VERSION
    assert name == "PlayerOne"


def test_conn_wrong_tag():
    raw = struct.pack(protocol.FRMT_CONN, b"XXXX", protocol.PROTO_VERSION, _pad_name("A"))
    assert protocol.safe_unpack_conn(raw) is None


def test_conok_round_trip():
    p = protocol.pack_conok(2, "MyRoom")
    u = protocol.safe_unpack_conok(p)
    assert u is not None
    assert u[1] == 2
    assert u[2] == "MyRoom"


def test_conno_round_trip():
    p = protocol.pack_conno(protocol.CONNO_REASON_FULL, 0)
    u = protocol.safe_unpack_conno(p)
    assert u is not None
    assert u[1] == protocol.CONNO_REASON_FULL
    assert u[2] == 0


def test_list_round_trip_empty_and_multi():
    assert protocol.safe_unpack_list(protocol.pack_list([])) == []
    rows = [(0, True, "Host"), (1, False, "Join")]
    p = protocol.pack_list(rows)
    u = protocol.safe_unpack_list(p)
    assert u == rows


def test_list_rejects_truncated_body():
    head = struct.pack(protocol.FRMT_LIST_HEAD, protocol.LIST, 2)
    assert protocol.safe_unpack_list(head) is None


def test_ready_round_trip():
    p = protocol.pack_ready(3, True)
    u = protocol.safe_unpack_ready(p)
    assert u is not None
    assert u[1] == 3
    assert u[2] is True


def test_start_round_trip():
    p = protocol.pack_start(0)
    u = protocol.safe_unpack_start(p)
    assert u is not None
    assert u[1] == 0


def test_cdwn_round_trip():
    p = protocol.pack_cdwn(4.5)
    u = protocol.safe_unpack_cdwn(p)
    assert u is not None
    assert u[1] == pytest.approx(4.5)


def test_cdwnx_round_trip():
    p = protocol.pack_cdwnx(protocol.CDWNX_REASON_HOST_CANCELLED)
    u = protocol.safe_unpack_cdwnx(p)
    assert u is not None
    assert u[1] == protocol.CDWNX_REASON_HOST_CANCELLED


def test_gstart_round_trip():
    p = protocol.pack_gstart()
    u = protocol.safe_unpack_gstart(p)
    assert u is not None
    assert u[0] == protocol.GSTART


def test_dead_elim_round_trip():
    p = protocol.pack_dead(2, 0)
    u = protocol.safe_unpack_dead(p)
    assert u is not None
    assert u[1] == 2
    assert u[2] == 0
    p2 = protocol.pack_elim(2, 3)
    u2 = protocol.safe_unpack_elim(p2)
    assert u2 is not None
    assert u2[1:] == (2, 3)


def test_gend_round_trip():
    standings = [(0, 1, "W"), (1, 2, "L")]
    p = protocol.pack_gend(protocol.GEND_REASON_NORMAL, standings)
    u = protocol.safe_unpack_gend(p)
    assert u is not None
    reason, back = u
    assert reason == protocol.GEND_REASON_NORMAL
    assert back == standings


def test_gend_rejects_wrong_count():
    head = struct.pack(protocol.FRMT_GEND_HEAD, protocol.GEND, 0, 1)
    assert protocol.safe_unpack_gend(head) is None


def test_kick_kicked_round_trip():
    p = protocol.pack_kick(0, 2)
    u = protocol.safe_unpack_kick(p)
    assert u is not None
    assert u[1:] == (0, 2)
    p2 = protocol.pack_kicked(protocol.KICKED_REASON_KICKED)
    u2 = protocol.safe_unpack_kicked(p2)
    assert u2 is not None
    assert u2[1] == protocol.KICKED_REASON_KICKED


def test_room_and_player_name_validation():
    assert protocol.is_valid_room_name("Room123")
    assert not protocol.is_valid_room_name("Room 123")
    assert not protocol.is_valid_room_name("ab")
    assert protocol.is_valid_player_name("Player123")
