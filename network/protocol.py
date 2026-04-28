import re
import struct
from typing import List, Optional, Tuple

PROTO_VERSION = 1
MAX_PLAYERS = 5
MIN_PLAYERS = 2
MAX_NAME_LEN = 32
RECV_BUF = 1024

DISCOVERY_PORT = 5556
BEACON_INTERVAL = 1.0
BEACON_TTL = 3.0
COUNTDOWN_SECONDS = 5.0
LEFT_BEHIND_DISTANCE = 720.0

STATE_LOBBY = 0
STATE_COUNTDOWN = 1
STATE_IN_GAME = 2

ROOM_NAME_REGEX = re.compile(r"^[A-Za-z0-9]{3,24}$")

CONNO_REASON_FULL = 0
CONNO_REASON_VERSION = 1
CONNO_REASON_IN_GAME = 2
CONNO_REASON_COOLDOWN = 3
CONNO_REASON_INVALID_NAME = 4
UINT32_MAX = 0xFFFFFFFF

CDWNX_REASON_HOST_CANCELLED = 0
CDWNX_REASON_NOT_ENOUGH_PLAYERS = 1
CDWNX_REASON_HOST_LEFT = 2

KICKED_REASON_KICKED = 0
KICKED_REASON_ROOM_CLOSED = 1
KICKED_REASON_NOT_READY = 2

GEND_REASON_NORMAL = 0
GEND_REASON_FORFEIT = 1

CONNECTION = b"CONN"  # Legacy handshake response compatibility
POSITION = b"POSI"
DISCONNECT = b"DISC"
DISCOVER = b"DSCV"

BEACON = b"BCON"
CONOK = b"CONO"
CONNO = b"CNOO"
LIST = b"LIST"
READY = b"REDY"
START = b"STRT"
CDWN = b"CDWN"
CDWNX = b"CANX"
GSTART = b"GSTR"
DEAD = b"DEAD"
ELIM = b"ELIM"
GEND = b"GEND"
KICK = b"KICK"
KICKED = b"KDED"

FRMT_PACKET = "!4sffi"  # Legacy packet: command, x, y, player_id
PACKET_SIZE = struct.calcsize(FRMT_PACKET)
Packet = Tuple[bytes, float, float, int]

FRMT_BEACON = "!4sBBBBH32s"
BEACON_PACKET_SIZE = struct.calcsize(FRMT_BEACON)
BeaconPacket = Tuple[bytes, int, int, int, int, int, str]

FRMT_CONN = "!4sB32s"
FRMT_CONOK = "!4si32s"
FRMT_CONNO = "!4sBI"
FRMT_LIST_HEAD = "!4sB"
FRMT_LIST_ITEM = "!iB32s"
FRMT_READY = "!4siB"
FRMT_START = "!4si"
FRMT_CDWN = "!4sf"
FRMT_CDWNX = "!4sB"
FRMT_GSTART = "!4s"
FRMT_DEAD = "!4siB"
FRMT_ELIM = "!4siB"
FRMT_GEND_HEAD = "!4sBB"
FRMT_GEND_ITEM = "!iB32s"
FRMT_KICK = "!4sii"
FRMT_KICKED = "!4sB"


def _pack_name(name: str) -> bytes:
    encoded = name.encode("ascii", errors="ignore")[:MAX_NAME_LEN]
    return encoded.ljust(MAX_NAME_LEN, b"\0")


def _unpack_name(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("ascii", errors="ignore")


def is_valid_room_name(name: str) -> bool:
    return ROOM_NAME_REGEX.fullmatch(name or "") is not None


def is_valid_player_name(name: str) -> bool:
    return is_valid_room_name(name)


def tag_of(data: bytes) -> Optional[bytes]:
    if len(data) < 4:
        return None
    return data[:4]


def pack_packet(command: bytes, x: float, y: float, player_id: int) -> bytes:
    return struct.pack(FRMT_PACKET, command, x, y, player_id)


def safe_unpack(data: bytes) -> Optional[Packet]:
    if len(data) != PACKET_SIZE:
        return None
    try:
        return struct.unpack(FRMT_PACKET, data)
    except struct.error:
        return None


def pack_beacon(proto_version: int, cur_players: int, max_players: int, room_state: int, game_port: int, room_name: str) -> bytes:
    return struct.pack(
        FRMT_BEACON,
        BEACON,
        proto_version,
        cur_players,
        max_players,
        room_state,
        game_port,
        _pack_name(room_name),
    )


def safe_unpack_beacon(data: bytes) -> Optional[BeaconPacket]:
    if len(data) != BEACON_PACKET_SIZE:
        return None
    try:
        tag, proto_version, cur_players, max_players, room_state, game_port, room_name = struct.unpack(FRMT_BEACON, data)
    except struct.error:
        return None
    if tag != BEACON:
        return None
    return (tag, proto_version, cur_players, max_players, room_state, game_port, _unpack_name(room_name))


def _safe_unpack_exact(data: bytes, fmt: str) -> Optional[Tuple]:
    if len(data) != struct.calcsize(fmt):
        return None
    try:
        return struct.unpack(fmt, data)
    except struct.error:
        return None


def pack_conn(player_name: str, proto_version: int = PROTO_VERSION) -> bytes:
    return struct.pack(FRMT_CONN, CONNECTION, proto_version, _pack_name(player_name))


def safe_unpack_conn(data: bytes) -> Optional[Tuple[bytes, int, str]]:
    unpacked = _safe_unpack_exact(data, FRMT_CONN)
    if unpacked is None:
        return None
    tag, proto_version, raw_name = unpacked
    if tag != CONNECTION:
        return None
    return tag, proto_version, _unpack_name(raw_name)


def pack_conok(player_id: int, room_name: str) -> bytes:
    return struct.pack(FRMT_CONOK, CONOK, player_id, _pack_name(room_name))


def safe_unpack_conok(data: bytes) -> Optional[Tuple[bytes, int, str]]:
    unpacked = _safe_unpack_exact(data, FRMT_CONOK)
    if unpacked is None:
        return None
    tag, player_id, raw_room_name = unpacked
    if tag != CONOK:
        return None
    return tag, player_id, _unpack_name(raw_room_name)


def pack_conno(reason_code: int, extra: int = 0) -> bytes:
    return struct.pack(FRMT_CONNO, CONNO, reason_code, extra)


def safe_unpack_conno(data: bytes) -> Optional[Tuple[bytes, int, int]]:
    unpacked = _safe_unpack_exact(data, FRMT_CONNO)
    if unpacked is None:
        return None
    tag, reason_code, extra = unpacked
    if tag != CONNO:
        return None
    return tag, reason_code, extra


def pack_list(entries: List[Tuple[int, bool, str]]) -> bytes:
    payload = struct.pack(FRMT_LIST_HEAD, LIST, len(entries))
    for player_id, ready, name in entries:
        payload += struct.pack(FRMT_LIST_ITEM, player_id, 1 if ready else 0, _pack_name(name))
    return payload


def safe_unpack_list(data: bytes) -> Optional[List[Tuple[int, bool, str]]]:
    head_size = struct.calcsize(FRMT_LIST_HEAD)
    if len(data) < head_size:
        return None
    try:
        tag, count = struct.unpack(FRMT_LIST_HEAD, data[:head_size])
    except struct.error:
        return None
    if tag != LIST:
        return None

    item_size = struct.calcsize(FRMT_LIST_ITEM)
    expected = head_size + (count * item_size)
    if len(data) != expected:
        return None

    entries: List[Tuple[int, bool, str]] = []
    offset = head_size
    for _ in range(count):
        player_id, ready, raw_name = struct.unpack(FRMT_LIST_ITEM, data[offset : offset + item_size])
        entries.append((player_id, bool(ready), _unpack_name(raw_name)))
        offset += item_size
    return entries


def pack_ready(player_id: int, ready_flag: bool) -> bytes:
    return struct.pack(FRMT_READY, READY, player_id, 1 if ready_flag else 0)


def safe_unpack_ready(data: bytes) -> Optional[Tuple[bytes, int, bool]]:
    unpacked = _safe_unpack_exact(data, FRMT_READY)
    if unpacked is None:
        return None
    tag, player_id, ready_flag = unpacked
    if tag != READY:
        return None
    return tag, player_id, bool(ready_flag)


def pack_start(host_id: int) -> bytes:
    return struct.pack(FRMT_START, START, host_id)


def safe_unpack_start(data: bytes) -> Optional[Tuple[bytes, int]]:
    unpacked = _safe_unpack_exact(data, FRMT_START)
    if unpacked is None:
        return None
    tag, host_id = unpacked
    if tag != START:
        return None
    return tag, host_id


def pack_cdwn(seconds_until_start: float) -> bytes:
    return struct.pack(FRMT_CDWN, CDWN, seconds_until_start)


def safe_unpack_cdwn(data: bytes) -> Optional[Tuple[bytes, float]]:
    unpacked = _safe_unpack_exact(data, FRMT_CDWN)
    if unpacked is None:
        return None
    tag, seconds_until_start = unpacked
    if tag != CDWN:
        return None
    return tag, seconds_until_start


def pack_cdwnx(reason_code: int) -> bytes:
    return struct.pack(FRMT_CDWNX, CDWNX, reason_code)


def safe_unpack_cdwnx(data: bytes) -> Optional[Tuple[bytes, int]]:
    unpacked = _safe_unpack_exact(data, FRMT_CDWNX)
    if unpacked is None:
        return None
    tag, reason_code = unpacked
    if tag != CDWNX:
        return None
    return tag, reason_code


def pack_gstart() -> bytes:
    return struct.pack(FRMT_GSTART, GSTART)


def safe_unpack_gstart(data: bytes) -> Optional[Tuple[bytes]]:
    unpacked = _safe_unpack_exact(data, FRMT_GSTART)
    if unpacked is None:
        return None
    (tag,) = unpacked
    if tag != GSTART:
        return None
    return (tag,)


def pack_dead(player_id: int, cause: int = 0) -> bytes:
    return struct.pack(FRMT_DEAD, DEAD, player_id, cause)


def safe_unpack_dead(data: bytes) -> Optional[Tuple[bytes, int, int]]:
    unpacked = _safe_unpack_exact(data, FRMT_DEAD)
    if unpacked is None:
        return None
    tag, player_id, cause = unpacked
    if tag != DEAD:
        return None
    return tag, player_id, cause


def pack_elim(player_id: int, placement: int) -> bytes:
    return struct.pack(FRMT_ELIM, ELIM, player_id, placement)


def safe_unpack_elim(data: bytes) -> Optional[Tuple[bytes, int, int]]:
    unpacked = _safe_unpack_exact(data, FRMT_ELIM)
    if unpacked is None:
        return None
    tag, player_id, placement = unpacked
    if tag != ELIM:
        return None
    return tag, player_id, placement


def pack_gend(reason_code: int, standings: List[Tuple[int, int, str]]) -> bytes:
    payload = struct.pack(FRMT_GEND_HEAD, GEND, reason_code, len(standings))
    for player_id, placement, name in standings:
        payload += struct.pack(FRMT_GEND_ITEM, player_id, placement, _pack_name(name))
    return payload


def safe_unpack_gend(data: bytes) -> Optional[Tuple[int, List[Tuple[int, int, str]]]]:
    head_size = struct.calcsize(FRMT_GEND_HEAD)
    if len(data) < head_size:
        return None
    try:
        tag, reason_code, count = struct.unpack(FRMT_GEND_HEAD, data[:head_size])
    except struct.error:
        return None
    if tag != GEND:
        return None

    item_size = struct.calcsize(FRMT_GEND_ITEM)
    expected = head_size + (count * item_size)
    if len(data) != expected:
        return None

    standings: List[Tuple[int, int, str]] = []
    offset = head_size
    for _ in range(count):
        player_id, placement, raw_name = struct.unpack(FRMT_GEND_ITEM, data[offset : offset + item_size])
        standings.append((player_id, placement, _unpack_name(raw_name)))
        offset += item_size
    return reason_code, standings


def pack_kick(host_id: int, target_player_id: int) -> bytes:
    return struct.pack(FRMT_KICK, KICK, host_id, target_player_id)


def safe_unpack_kick(data: bytes) -> Optional[Tuple[bytes, int, int]]:
    unpacked = _safe_unpack_exact(data, FRMT_KICK)
    if unpacked is None:
        return None
    tag, host_id, target_player_id = unpacked
    if tag != KICK:
        return None
    return tag, host_id, target_player_id


def pack_kicked(reason_code: int) -> bytes:
    return struct.pack(FRMT_KICKED, KICKED, reason_code)


def safe_unpack_kicked(data: bytes) -> Optional[Tuple[bytes, int]]:
    unpacked = _safe_unpack_exact(data, FRMT_KICKED)
    if unpacked is None:
        return None
    tag, reason_code = unpacked
    if tag != KICKED:
        return None
    return tag, reason_code
