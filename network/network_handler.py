from dataclasses import dataclass
import logging
import queue
import socket
import threading
from typing import List, Optional, Tuple, Union

from network.protocol import (
    AVATAR_CHUNK,
    AVATAR_CHUNK_PAYLOAD_SIZE,
    AVATAR_HEADER,
    CONNECTION,
    CONNO,
    CONNO_REASON_COOLDOWN,
    CONNO_REASON_FULL,
    CONNO_REASON_IN_GAME,
    CONNO_REASON_INVALID_NAME,
    CONNO_REASON_VERSION,
    CONOK,
    CDWN,
    CDWNX,
    DEAD,
    DISCOVER,
    DISCONNECT,
    ELIM,
    GEND,
    GSTART,
    KICK,
    KICKED,
    LIST,
    MATCH_PAUSE,
    MATCH_RESUME,
    PLAYER_STATE,
    POSITION,
    PROTO_VERSION,
    READY,
    RECV_BUF,
    RECONNECT_NO,
    RECONNECT_OK,
    SESSION,
    START,
    UINT32_MAX,
    pack_conn,
    pack_avatar_chunk,
    pack_avatar_header,
    pack_dead,
    pack_kick,
    pack_packet,
    pack_player_state,
    pack_ready,
    pack_reconnect,
    pack_start,
    safe_unpack,
    safe_unpack_avatar_chunk,
    safe_unpack_avatar_header,
    safe_unpack_cdwn,
    safe_unpack_cdwnx,
    safe_unpack_conno,
    safe_unpack_conok,
    safe_unpack_elim,
    safe_unpack_gend,
    safe_unpack_kicked,
    safe_unpack_list,
    safe_unpack_match_pause,
    safe_unpack_match_resume,
    safe_unpack_player_state,
    safe_unpack_reconnect_no,
    safe_unpack_reconnect_ok,
    safe_unpack_session,
    tag_of,
)

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConnectResult:
    ok: bool
    player_id: Optional[int] = None
    room_name: str = ""
    reason_code: Optional[int] = None
    extra: int = 0
    start_pos: Optional[Tuple[float, float]] = None
    session_token: int = 0


@dataclass(frozen=True)
class RosterEvent:
    entries: List[Tuple[int, bool, str]]


@dataclass(frozen=True)
class CountdownEvent:
    seconds_until_start: float


@dataclass(frozen=True)
class CountdownCancelEvent:
    reason_code: int


@dataclass(frozen=True)
class GameStartEvent:
    pass


@dataclass(frozen=True)
class EliminationEvent:
    player_id: int
    placement: int


@dataclass(frozen=True)
class GameEndEvent:
    reason_code: int
    standings: List[Tuple[int, int, str]]


@dataclass(frozen=True)
class KickedEvent:
    reason_code: int


@dataclass(frozen=True)
class PositionEvent:
    x: float
    y: float
    player_id: int


@dataclass(frozen=True)
class PlayerStateEvent:
    x: float
    y: float
    player_id: int
    animation_state_id: int


@dataclass(frozen=True)
class AvatarHeaderEvent:
    player_id: int
    avatar_id: int
    total_chunks: int
    payload_size: int


@dataclass(frozen=True)
class AvatarChunkEvent:
    player_id: int
    avatar_id: int
    chunk_index: int
    total_chunks: int
    payload: bytes


@dataclass(frozen=True)
class SessionEvent:
    player_id: int
    session_token: int


@dataclass(frozen=True)
class MatchPauseEvent:
    player_id: int
    seconds_remaining: float


@dataclass(frozen=True)
class MatchResumeEvent:
    pass


@dataclass(frozen=True)
class ConnectDeniedEvent:
    reason_code: int
    extra: int


@dataclass(frozen=True)
class ConnectionLostEvent:
    message: str


@dataclass(frozen=True)
class ErrorEvent:
    message: str


NetworkEvent = Union[
    RosterEvent,
    CountdownEvent,
    CountdownCancelEvent,
    GameStartEvent,
    EliminationEvent,
    GameEndEvent,
    KickedEvent,
    PositionEvent,
    PlayerStateEvent,
    AvatarHeaderEvent,
    AvatarChunkEvent,
    SessionEvent,
    MatchPauseEvent,
    MatchResumeEvent,
    ConnectDeniedEvent,
    ConnectionLostEvent,
    ErrorEvent,
]


class Network:
    def __init__(self, IP: str = "", PORT: int = 5555):
        self.client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.client.settimeout(0.1)

        self.server = IP
        self.port = PORT
        self.addr = (self.server, self.port)
        self.id = -1
        self.room_name = ""
        self.session_token = 0
        self._closed = False

        self.events: "queue.Queue[NetworkEvent]" = queue.Queue()
        self._recv_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    @property
    def is_open(self) -> bool:
        return not self._closed

    def _mark_connection_lost(self, message: str) -> ConnectionLostEvent:
        self._closed = True
        return ConnectionLostEvent(message)

    def _sendto(self, payload: bytes, addr: Optional[Tuple[str, int]] = None, report_error: bool = True) -> bool:
        if self._closed:
            return False
        try:
            self.client.sendto(payload, addr or self.addr)
            return True
        except OSError as error:
            if report_error:
                self.events.put(self._mark_connection_lost(f"Network send failed: {error}"))
            else:
                self._closed = True
            return False

    def close(self):
        self.stop_receiver()
        self._closed = True
        try:
            self.client.close()
        except OSError:
            pass

    def _recv_event_loop(self):
        while not self._stop_event.is_set() and not self._closed:
            event = self.receive_one()
            if event is None:
                continue
            if isinstance(event, SessionEvent):
                self.id = event.player_id
                self.session_token = event.session_token
            self.events.put(event)

    def start_receiver(self):
        if self._closed:
            return
        if self._recv_thread and self._recv_thread.is_alive():
            return
        self._stop_event.clear()
        self._recv_thread = threading.Thread(target=self._recv_event_loop, daemon=True, name="network-receiver")
        self._recv_thread.start()

    def stop_receiver(self, timeout: float = 2.0):
        self._stop_event.set()
        if self._recv_thread and self._recv_thread.is_alive():
            self._recv_thread.join(timeout=timeout)

    def discover_servers(self, timeout_seconds: float = 2.0) -> List[Tuple[str, int]]:
        discover_msg = pack_packet(DISCOVER, 0.0, 0.0, 0)
        self.client.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.client.settimeout(timeout_seconds)
        self.client.sendto(discover_msg, ("255.255.255.255", self.port))

        servers: List[Tuple[str, int]] = []
        seen = set()
        while True:
            try:
                data, addr = self.client.recvfrom(RECV_BUF)
            except socket.timeout:
                break
            unpacked = safe_unpack(data)
            if unpacked is None:
                continue
            cmd, _x, _y, _sid = unpacked
            if cmd != DISCOVER:
                continue
            server_addr = (addr[0], addr[1])
            if server_addr in seen:
                continue
            seen.add(server_addr)
            servers.append(server_addr)

        self.client.settimeout(0.1)
        return servers

    def connect_to_room(self, addr: str, port: int, player_name: str) -> ConnectResult:
        self.addr = (addr, port)
        self.client.settimeout(2.0)
        if not self._sendto(pack_conn(player_name, PROTO_VERSION), report_error=False):
            return ConnectResult(ok=False, reason_code=CONNO_REASON_VERSION)

        start_pos: Optional[Tuple[float, float]] = None
        try:
            while True:
                data, source_addr = self.client.recvfrom(RECV_BUF)
                if source_addr != self.addr:
                    continue

                tag = tag_of(data)
                if tag == SESSION:
                    unpacked = safe_unpack_session(data)
                    if unpacked is not None:
                        _tag, player_id, session_token = unpacked
                        self.id = player_id
                        self.session_token = session_token
                    continue

                if tag == CONOK:
                    unpacked = safe_unpack_conok(data)
                    if unpacked is None:
                        return ConnectResult(ok=False, reason_code=CONNO_REASON_VERSION)
                    _tag, player_id, room_name = unpacked
                    self.id = player_id
                    self.room_name = room_name
                    if start_pos is None:
                        start_pos = (100.0, 100.0)
                    self.client.settimeout(0.1)
                    return ConnectResult(
                        ok=True,
                        player_id=player_id,
                        room_name=room_name,
                        start_pos=start_pos,
                        session_token=self.session_token,
                    )

                if tag == CONNO:
                    unpacked = safe_unpack_conno(data)
                    if unpacked is None:
                        return ConnectResult(ok=False, reason_code=CONNO_REASON_VERSION)
                    _tag, reason_code, extra = unpacked
                    self.client.settimeout(0.1)
                    return ConnectResult(ok=False, reason_code=reason_code, extra=extra)

                # Legacy compatibility response carrying spawn coordinates.
                if tag == CONNECTION:
                    unpacked = safe_unpack(data)
                    if unpacked is not None:
                        _cmd, x, y, _pid = unpacked
                        start_pos = (x, y)
                    continue

                parsed = self._parse_event(data)
                if parsed is not None:
                    self.events.put(parsed)
        except socket.timeout:
            self.client.settimeout(0.1)
            return ConnectResult(ok=False, reason_code=CONNO_REASON_VERSION)

    def reconnect_to_room(
        self,
        addr: str,
        port: int,
        player_id: int,
        session_token: int,
        player_name: str,
    ) -> ConnectResult:
        self.addr = (addr, port)
        self.client.settimeout(2.0)
        payload = pack_reconnect(player_id, session_token, player_name, PROTO_VERSION)
        if not self._sendto(payload, report_error=False):
            return ConnectResult(ok=False, reason_code=CONNO_REASON_VERSION)

        try:
            while True:
                data, source_addr = self.client.recvfrom(RECV_BUF)
                if source_addr != self.addr:
                    continue

                tag = tag_of(data)
                if tag == SESSION:
                    unpacked = safe_unpack_session(data)
                    if unpacked is not None:
                        _tag, session_player_id, new_token = unpacked
                        self.id = session_player_id
                        self.session_token = new_token
                    continue

                if tag == RECONNECT_OK:
                    unpacked = safe_unpack_reconnect_ok(data)
                    if unpacked is None:
                        return ConnectResult(ok=False, reason_code=CONNO_REASON_VERSION)
                    _tag, reconnected_id, x, y, room_name = unpacked
                    self.id = reconnected_id
                    self.room_name = room_name
                    if self.session_token == 0:
                        self.session_token = session_token
                    self.client.settimeout(0.1)
                    return ConnectResult(
                        ok=True,
                        player_id=reconnected_id,
                        room_name=room_name,
                        start_pos=(x, y),
                        session_token=self.session_token,
                    )

                if tag == RECONNECT_NO:
                    unpacked = safe_unpack_reconnect_no(data)
                    reason = unpacked[1] if unpacked is not None else CONNO_REASON_VERSION
                    self.client.settimeout(0.1)
                    return ConnectResult(ok=False, reason_code=reason)

                parsed = self._parse_event(data)
                if parsed is not None:
                    self.events.put(parsed)
        except socket.timeout:
            self.client.settimeout(0.1)
            return ConnectResult(ok=False, reason_code=CONNO_REASON_VERSION)

    def connect(self):
        servers = self.discover_servers()
        if not servers:
            LOGGER.info("No servers found.")
            return None
        server_addr, server_port = servers[0]
        LOGGER.info("Connecting to %s:%s", server_addr, server_port)
        result = self.connect_to_room(server_addr, server_port, "Player")
        if not result.ok:
            if result.reason_code == CONNO_REASON_FULL:
                LOGGER.error("Connection rejected: room is full")
            elif result.reason_code == CONNO_REASON_IN_GAME:
                LOGGER.error("Connection rejected: room is in game/countdown")
            elif result.reason_code == CONNO_REASON_COOLDOWN:
                if result.extra == UINT32_MAX:
                    LOGGER.error("Connection rejected: on permanent cooldown")
                else:
                    LOGGER.error("Connection rejected: cooldown (%ss remaining)", result.extra)
            elif result.reason_code == CONNO_REASON_INVALID_NAME:
                LOGGER.error("Connection rejected: invalid player name")
            else:
                LOGGER.error("Connection rejected.")
            return None
        return result.start_pos

    def send_ready(self, flag: bool):
        if self.id < 0:
            return
        self._sendto(pack_ready(self.id, flag))

    def send_start(self):
        if self.id < 0:
            return
        self._sendto(pack_start(self.id))

    def cancel_countdown(self):
        self.send_start()

    def send_kick(self, target_id: int):
        if self.id < 0:
            return
        self._sendto(pack_kick(self.id, target_id))

    def send_dead(self):
        if self.id < 0:
            return
        self._sendto(pack_dead(self.id, 0))

    def close_room(self):
        self.send_kick(-1)

    def update_pos(self, x: float, y: float):
        if self.id < 0:
            return
        self._sendto(pack_packet(POSITION, x, y, self.id))

    def update_player_state(self, x: float, y: float, animation_state: str):
        if self.id < 0:
            return
        self._sendto(pack_player_state(x, y, self.id, animation_state))

    def send_avatar(self, avatar_id: int, payload: bytes):
        if self.id < 0 or not payload:
            return
        chunks = [
            payload[index : index + AVATAR_CHUNK_PAYLOAD_SIZE]
            for index in range(0, len(payload), AVATAR_CHUNK_PAYLOAD_SIZE)
        ]
        if not self._sendto(pack_avatar_header(self.id, avatar_id, len(chunks), len(payload))):
            return
        for index, chunk in enumerate(chunks):
            if not self._sendto(pack_avatar_chunk(self.id, avatar_id, index, len(chunks), chunk)):
                return

    def _parse_event(self, data: bytes) -> Optional[NetworkEvent]:
        tag = tag_of(data)
        if tag is None:
            return None
        if tag == LIST:
            entries = safe_unpack_list(data)
            if entries is None:
                return ErrorEvent("Malformed LIST packet")
            return RosterEvent(entries=entries)
        if tag == CDWN:
            unpacked = safe_unpack_cdwn(data)
            if unpacked is None:
                return ErrorEvent("Malformed CDWN packet")
            _tag, seconds_until_start = unpacked
            return CountdownEvent(seconds_until_start=seconds_until_start)
        if tag == CDWNX:
            unpacked = safe_unpack_cdwnx(data)
            if unpacked is None:
                return ErrorEvent("Malformed CDWNX packet")
            _tag, reason_code = unpacked
            return CountdownCancelEvent(reason_code=reason_code)
        if tag == GSTART:
            return GameStartEvent()
        if tag == ELIM:
            unpacked = safe_unpack_elim(data)
            if unpacked is None:
                return ErrorEvent("Malformed ELIM packet")
            _tag, player_id, placement = unpacked
            return EliminationEvent(player_id=player_id, placement=placement)
        if tag == GEND:
            unpacked = safe_unpack_gend(data)
            if unpacked is None:
                return ErrorEvent("Malformed GEND packet")
            reason_code, standings = unpacked
            return GameEndEvent(reason_code=reason_code, standings=standings)
        if tag == KICKED:
            unpacked = safe_unpack_kicked(data)
            if unpacked is None:
                return ErrorEvent("Malformed KICKED packet")
            _tag, reason_code = unpacked
            return KickedEvent(reason_code=reason_code)
        if tag == SESSION:
            unpacked = safe_unpack_session(data)
            if unpacked is None:
                return ErrorEvent("Malformed SESS packet")
            _tag, player_id, session_token = unpacked
            self.id = player_id
            self.session_token = session_token
            return SessionEvent(player_id=player_id, session_token=session_token)
        if tag == MATCH_PAUSE:
            unpacked = safe_unpack_match_pause(data)
            if unpacked is None:
                return ErrorEvent("Malformed PAUS packet")
            _tag, player_id, seconds_remaining = unpacked
            return MatchPauseEvent(player_id=player_id, seconds_remaining=seconds_remaining)
        if tag == MATCH_RESUME:
            unpacked = safe_unpack_match_resume(data)
            if unpacked is None:
                return ErrorEvent("Malformed RSUM packet")
            return MatchResumeEvent()
        if tag == CONNO:
            unpacked = safe_unpack_conno(data)
            if unpacked is None:
                return ErrorEvent("Malformed CONNO packet")
            _tag, reason_code, extra = unpacked
            return ConnectDeniedEvent(reason_code=reason_code, extra=extra)
        if tag == POSITION:
            unpacked = safe_unpack(data)
            if unpacked is None:
                return ErrorEvent("Malformed POSI packet")
            _cmd, x, y, player_id = unpacked
            return PositionEvent(x=x, y=y, player_id=player_id)
        if tag == PLAYER_STATE:
            unpacked = safe_unpack_player_state(data)
            if unpacked is None:
                return ErrorEvent("Malformed PSTA packet")
            _tag, x, y, player_id, state_id = unpacked
            return PlayerStateEvent(
                x=x,
                y=y,
                player_id=player_id,
                animation_state_id=state_id,
            )
        if tag == AVATAR_HEADER:
            unpacked = safe_unpack_avatar_header(data)
            if unpacked is None:
                return ErrorEvent("Malformed AVHD packet")
            _tag, player_id, avatar_id, total_chunks, payload_size = unpacked
            return AvatarHeaderEvent(
                player_id=player_id,
                avatar_id=avatar_id,
                total_chunks=total_chunks,
                payload_size=payload_size,
            )
        if tag == AVATAR_CHUNK:
            unpacked = safe_unpack_avatar_chunk(data)
            if unpacked is None:
                return ErrorEvent("Malformed AVCK packet")
            _tag, player_id, avatar_id, chunk_index, total_chunks, payload = unpacked
            return AvatarChunkEvent(
                player_id=player_id,
                avatar_id=avatar_id,
                chunk_index=chunk_index,
                total_chunks=total_chunks,
                payload=payload,
            )
        return None

    def receive_one(self) -> Optional[NetworkEvent]:
        try:
            data, _addr = self.client.recvfrom(RECV_BUF)
        except socket.timeout:
            return None
        except OSError as error:
            if self._stop_event.is_set() or self._closed:
                return None
            return self._mark_connection_lost(f"Network receive failed: {error}")
        return self._parse_event(data)

    # Legacy receive API for existing gameplay loop.
    def receive(self):
        event = self.receive_one()
        if isinstance(event, PositionEvent):
            return POSITION, event.x, event.y, event.player_id
        if isinstance(event, ErrorEvent):
            LOGGER.error(event.message)
        return None

    def disconnect(self):
        try:
            if self.id < 0 or not self.addr[0]:
                return
            msg = pack_packet(DISCONNECT, 0.0, 0.0, self.id)
            self._sendto(msg, report_error=False)
        except OSError as error:
            LOGGER.error("Error disconnecting: %s", error)
