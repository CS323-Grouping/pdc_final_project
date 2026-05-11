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
    CONNO_REASON_NAME_TAKEN,
    CONNO_REASON_VERSION,
    CONOK,
    CDWN,
    CDWNX,
    DEAD,
    GOAL,
    DISCOVER,
    DISCONNECT,
    ELIM,
    GEND,
    GSTART,
    HEARTBEAT_ACK,
    HEARTBEAT_INTERVAL_SECONDS,
    KICK,
    KICKED,
    LEVEL_SELECT,
    LIST,
    MATCH_PAUSE,
    MATCH_RESUME,
    PLAYER_STATE,
    POSITION,
    PROTO_VERSION,
    READY,
    ORB_COLLECT,
    PLATFORM_PROGRESS,
    RECV_BUF,
    RECONNECT_NO,
    RECONNECT_OK,
    ROOM_NAME_UPDATE,
    SESSION,
    START,
    START_ACTION_CANCEL,
    START_ACTION_START,
    DEFAULT_LEVEL_ID,
    UINT32_MAX,
    pack_conn,
    pack_avatar_chunk,
    pack_avatar_header,
    pack_dead,
    pack_goal,
    pack_heartbeat,
    pack_kick,
    pack_packet,
    pack_player_state,
    pack_ready,
    pack_reconnect,
    pack_level_select,
    pack_room_name_update,
    pack_orb_collect,
    pack_platform_progress,
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
    safe_unpack_gstart,
    safe_unpack_goal,
    safe_unpack_heartbeat_ack,
    safe_unpack_kicked,
    safe_unpack_list,
    safe_unpack_match_pause,
    safe_unpack_match_resume,
    safe_unpack_orb_collect,
    safe_unpack_platform_progress,
    safe_unpack_player_state,
    safe_unpack_reconnect_no,
    safe_unpack_reconnect_ok,
    safe_unpack_level_select,
    safe_unpack_room_name_update,
    safe_unpack_session,
    tag_of,
)

LOGGER = logging.getLogger(__name__)


def _packet_tag_name(payload: bytes) -> str:
    tag = tag_of(payload)
    if tag is None:
        return "UNKNOWN"
    try:
        return tag.decode("ascii")
    except UnicodeDecodeError:
        return repr(tag)


def _event_log_level(event: "NetworkEvent") -> int:
    if isinstance(event, (PositionEvent, PlayerStateEvent, AvatarChunkEvent, OrbCollectEvent, PlatformProgressEvent)):
        return logging.DEBUG
    if isinstance(event, ErrorEvent):
        return logging.WARNING
    return logging.INFO


def _event_summary(event: "NetworkEvent") -> str:
    if isinstance(event, RosterEvent):
        return f"RosterEvent entries={event.entries}"
    if isinstance(event, CountdownEvent):
        return f"CountdownEvent id={event.countdown_id} seconds={event.seconds_until_start:.2f}"
    if isinstance(event, CountdownCancelEvent):
        return f"CountdownCancelEvent id={event.countdown_id} reason={event.reason_code}"
    if isinstance(event, GameStartEvent):
        return (
            "GameStartEvent "
            f"countdown_id={event.countdown_id} "
            f"match_id={event.match_id} "
            f"level={event.selected_level} "
            f"seed={event.level_seed}"
        )
    if isinstance(event, EliminationEvent):
        return f"EliminationEvent player_id={event.player_id} placement={event.placement}"
    if isinstance(event, GameEndEvent):
        return f"GameEndEvent match_id={event.match_id} reason={event.reason_code} standings={event.standings}"
    if isinstance(event, KickedEvent):
        return f"KickedEvent reason={event.reason_code}"
    if isinstance(event, PositionEvent):
        return f"PositionEvent player_id={event.player_id} x={event.x:.1f} y={event.y:.1f}"
    if isinstance(event, PlayerStateEvent):
        return (
            f"PlayerStateEvent player_id={event.player_id} "
            f"x={event.x:.1f} y={event.y:.1f} state={event.animation_state_id}"
        )
    if isinstance(event, AvatarHeaderEvent):
        return (
            f"AvatarHeaderEvent player_id={event.player_id} avatar_id={event.avatar_id} "
            f"chunks={event.total_chunks} bytes={event.payload_size} "
            f"model={event.model_type}/{event.model_color}"
        )
    if isinstance(event, AvatarChunkEvent):
        return (
            f"AvatarChunkEvent player_id={event.player_id} avatar_id={event.avatar_id} "
            f"chunk={event.chunk_index + 1}/{event.total_chunks} bytes={len(event.payload)}"
        )
    if isinstance(event, SessionEvent):
        return f"SessionEvent player_id={event.player_id} token={event.session_token}"
    if isinstance(event, MatchPauseEvent):
        return f"MatchPauseEvent player_id={event.player_id} remaining={event.seconds_remaining:.2f}"
    if isinstance(event, MatchResumeEvent):
        return "MatchResumeEvent"
    if isinstance(event, HeartbeatAckEvent):
        return f"HeartbeatAckEvent state={event.server_state} countdown_id={event.countdown_id} match_id={event.match_id}"
    if isinstance(event, RoomNameEvent):
        return f"RoomNameEvent room_name={event.room_name}"
    if isinstance(event, LevelSelectEvent):
        return f"LevelSelectEvent level={event.level_id}"
    if isinstance(event, OrbCollectEvent):
        return (
            f"OrbCollectEvent player_id={event.player_id} orb_index={event.orb_index} "
            f"cooldown_sec={event.cooldown_sec}"
        )
    if isinstance(event, GoalEvent):
        return f"GoalEvent player_id={event.player_id}"
    if isinstance(event, PlatformProgressEvent):
        return f"PlatformProgressEvent player_id={event.player_id} platforms_reached={event.platforms_reached}"
    if isinstance(event, ConnectDeniedEvent):
        return f"ConnectDeniedEvent reason={event.reason_code} extra={event.extra}"
    if isinstance(event, ConnectionLostEvent):
        return f"ConnectionLostEvent message={event.message}"
    if isinstance(event, ErrorEvent):
        return f"ErrorEvent message={event.message}"
    return event.__class__.__name__


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
    countdown_id: int
    seconds_until_start: float


@dataclass(frozen=True)
class CountdownCancelEvent:
    countdown_id: int
    reason_code: int


@dataclass(frozen=True)
class GameStartEvent:
    countdown_id: int = 0
    match_id: int = 0
    selected_level: int = DEFAULT_LEVEL_ID
    level_seed: int = 0
    match_start_unix_sec: int = 0


@dataclass(frozen=True)
class EliminationEvent:
    player_id: int
    placement: int


@dataclass(frozen=True)
class GoalEvent:
    player_id: int


@dataclass(frozen=True)
class PlatformProgressEvent:
    player_id: int
    platforms_reached: int


@dataclass(frozen=True)
class GameEndEvent:
    match_id: int
    reason_code: int
    standings: List[Tuple[int, int, str, int, int]]


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
    model_type: str
    model_color: str


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
class HeartbeatAckEvent:
    server_state: int
    countdown_id: int
    match_id: int


@dataclass(frozen=True)
class RoomNameEvent:
    room_name: str


@dataclass(frozen=True)
class LevelSelectEvent:
    level_id: int


@dataclass(frozen=True)
class OrbCollectEvent:
    player_id: int
    orb_index: int
    cooldown_sec: int


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
    GoalEvent,
    PlatformProgressEvent,
    GameEndEvent,
    KickedEvent,
    PositionEvent,
    PlayerStateEvent,
    AvatarHeaderEvent,
    AvatarChunkEvent,
    SessionEvent,
    MatchPauseEvent,
    MatchResumeEvent,
    HeartbeatAckEvent,
    RoomNameEvent,
    LevelSelectEvent,
    OrbCollectEvent,
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
        self.selected_level = DEFAULT_LEVEL_ID
        self.session_token = 0
        self._closed = False
        self._client_state = 0
        self._countdown_id = 0
        self._match_id = 0
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._heartbeat_lock = threading.Lock()

        self.events: "queue.Queue[NetworkEvent]" = queue.Queue()
        self._recv_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        LOGGER.info("Network socket initialized default_addr=%s", self.addr)

    @property
    def is_open(self) -> bool:
        return not self._closed

    def _mark_connection_lost(self, message: str) -> ConnectionLostEvent:
        LOGGER.warning("Connection lost: %s", message)
        self._closed = True
        return ConnectionLostEvent(message)

    def _sendto(self, payload: bytes, addr: Optional[Tuple[str, int]] = None, report_error: bool = True) -> bool:
        if self._closed:
            return False
        target = addr or self.addr
        tag = _packet_tag_name(payload)
        try:
            self.client.sendto(payload, target)
            LOGGER.debug("send packet tag=%s bytes=%s target=%s player_id=%s", tag, len(payload), target, self.id)
            return True
        except OSError as error:
            LOGGER.warning("send failed tag=%s target=%s error=%s", tag, target, error)
            if report_error:
                self.events.put(self._mark_connection_lost(f"Network send failed: {error}"))
            else:
                self._closed = True
            return False

    def _set_remote_addr(self, addr: str, port: int) -> bool:
        try:
            infos = socket.getaddrinfo(addr, port, socket.AF_INET, socket.SOCK_DGRAM)
        except OSError as error:
            LOGGER.warning("Address resolution failed addr=%s port=%s error=%s", addr, port, error)
            return False
        if not infos:
            LOGGER.warning("Address resolution returned no results addr=%s port=%s", addr, port)
            return False
        remote_host, remote_port = infos[0][4][:2]
        self.server = remote_host
        self.port = int(remote_port)
        self.addr = (self.server, self.port)
        if remote_host != addr:
            LOGGER.info("Resolved room host %s:%s -> %s:%s", addr, port, remote_host, remote_port)
        return True

    def close(self):
        LOGGER.info("Closing network socket player_id=%s addr=%s", self.id, self.addr)
        self.stop_receiver()
        self._closed = True
        try:
            self.client.close()
        except OSError:
            pass

    def _recv_event_loop(self):
        LOGGER.info("Network receiver started player_id=%s addr=%s", self.id, self.addr)
        while not self._stop_event.is_set() and not self._closed:
            event = self.receive_one()
            if event is None:
                continue
            if isinstance(event, SessionEvent):
                self.id = event.player_id
                self.session_token = event.session_token
            elif isinstance(event, CountdownEvent):
                with self._heartbeat_lock:
                    self._countdown_id = event.countdown_id
            elif isinstance(event, CountdownCancelEvent):
                with self._heartbeat_lock:
                    if event.countdown_id == 0 or event.countdown_id >= self._countdown_id:
                        self._countdown_id = event.countdown_id
            elif isinstance(event, GameStartEvent):
                with self._heartbeat_lock:
                    self._countdown_id = event.countdown_id
                    self._match_id = event.match_id
            elif isinstance(event, GameEndEvent):
                with self._heartbeat_lock:
                    self._match_id = max(self._match_id, event.match_id)
            elif isinstance(event, HeartbeatAckEvent):
                with self._heartbeat_lock:
                    self._countdown_id = max(self._countdown_id, event.countdown_id)
                    self._match_id = max(self._match_id, event.match_id)
            LOGGER.log(_event_log_level(event), "recv %s", _event_summary(event))
            self.events.put(event)
        LOGGER.info("Network receiver stopped player_id=%s addr=%s", self.id, self.addr)

    def _heartbeat_loop(self):
        while not self._stop_event.is_set() and not self._closed:
            self.send_heartbeat()
            self._stop_event.wait(HEARTBEAT_INTERVAL_SECONDS)

    def set_client_state(self, client_state: int):
        with self._heartbeat_lock:
            self._client_state = max(0, min(255, int(client_state)))

    def send_heartbeat(self):
        if self.id < 0:
            return
        with self._heartbeat_lock:
            payload = pack_heartbeat(
                self.id,
                self.session_token,
                self._client_state,
                self._countdown_id,
                self._match_id,
            )
        self._sendto(payload, report_error=False)

    def start_receiver(self):
        if self._closed:
            return
        if self._recv_thread and self._recv_thread.is_alive():
            return
        self._stop_event.clear()
        self._recv_thread = threading.Thread(target=self._recv_event_loop, daemon=True, name="network-receiver")
        self._recv_thread.start()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True, name="network-heartbeat")
        self._heartbeat_thread.start()
        LOGGER.info("Started network receiver thread addr=%s", self.addr)

    def stop_receiver(self, timeout: float = 2.0):
        self._stop_event.set()
        if self._recv_thread and self._recv_thread.is_alive():
            self._recv_thread.join(timeout=timeout)
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=timeout)

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
        if not self._set_remote_addr(addr, port):
            return ConnectResult(ok=False, reason_code=CONNO_REASON_VERSION)
        self.client.settimeout(2.0)
        LOGGER.info("Connecting to room addr=%s player_name=%s", self.addr, player_name)
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
                    LOGGER.info(
                        "Connected to room=%s player_id=%s token=%s start_pos=%s",
                        room_name,
                        player_id,
                        self.session_token,
                        start_pos,
                    )
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
                    LOGGER.info("Connection denied reason=%s extra=%s", reason_code, extra)
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
            LOGGER.warning("Connection timed out addr=%s", self.addr)
            return ConnectResult(ok=False, reason_code=CONNO_REASON_VERSION)

    def reconnect_to_room(
        self,
        addr: str,
        port: int,
        player_id: int,
        session_token: int,
        player_name: str,
    ) -> ConnectResult:
        if not self._set_remote_addr(addr, port):
            return ConnectResult(ok=False, reason_code=CONNO_REASON_VERSION)
        self.client.settimeout(2.0)
        payload = pack_reconnect(player_id, session_token, player_name, PROTO_VERSION)
        LOGGER.info(
            "Reconnecting to room addr=%s player_id=%s token=%s player_name=%s",
            self.addr,
            player_id,
            session_token,
            player_name,
        )
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
                    LOGGER.info(
                        "Reconnect accepted room=%s player_id=%s token=%s start_pos=(%.1f, %.1f)",
                        room_name,
                        reconnected_id,
                        self.session_token,
                        x,
                        y,
                    )
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
                    LOGGER.info("Reconnect denied reason=%s", reason)
                    return ConnectResult(ok=False, reason_code=reason)

                parsed = self._parse_event(data)
                if parsed is not None:
                    self.events.put(parsed)
        except socket.timeout:
            self.client.settimeout(0.1)
            LOGGER.warning("Reconnect timed out addr=%s", self.addr)
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
            elif result.reason_code == CONNO_REASON_NAME_TAKEN:
                LOGGER.error("Connection rejected: player name already in room")
            else:
                LOGGER.error("Connection rejected.")
            return None
        return result.start_pos

    def send_ready(self, flag: bool):
        if self.id < 0:
            return
        LOGGER.info("send READY player_id=%s ready=%s", self.id, flag)
        self._sendto(pack_ready(self.id, flag))

    def send_start(self):
        if self.id < 0:
            return
        LOGGER.info("send START player_id=%s", self.id)
        self._sendto(pack_start(self.id, START_ACTION_START))

    def cancel_countdown(self):
        if self.id < 0:
            return
        LOGGER.info("send CANCEL player_id=%s", self.id)
        self._sendto(pack_start(self.id, START_ACTION_CANCEL))

    def send_kick(self, target_id: int):
        if self.id < 0:
            return
        LOGGER.info("send KICK host_id=%s target_id=%s", self.id, target_id)
        self._sendto(pack_kick(self.id, target_id))

    def send_room_name(self, room_name: str):
        if self.id < 0:
            return
        LOGGER.info("send ROOM_NAME player_id=%s room_name=%s", self.id, room_name)
        self._sendto(pack_room_name_update(self.id, room_name))

    def send_level_select(self, level_id: int):
        if self.id < 0:
            return
        LOGGER.info("send LEVEL_SELECT player_id=%s level=%s", self.id, level_id)
        self._sendto(pack_level_select(self.id, level_id))

    def send_dead(self):
        if self.id < 0:
            return
        LOGGER.info("send DEAD player_id=%s", self.id)
        self._sendto(pack_dead(self.id, 0))

    def send_goal(self):
        if self.id < 0:
            return
        LOGGER.info("send GOAL player_id=%s", self.id)
        self._sendto(pack_goal(self.id))

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

    def send_orb_collect(self, orb_index: int, cooldown_sec: int):
        if self.id < 0:
            return
        self._sendto(pack_orb_collect(self.id, int(orb_index), int(cooldown_sec)))

    def send_platform_progress(self, platforms_reached: int):
        if self.id < 0:
            return
        self._sendto(pack_platform_progress(self.id, int(platforms_reached)))

    def send_avatar(
        self,
        avatar_id: int,
        payload: bytes,
        model_type: str = "Default",
        model_color: str = "Blue",
    ):
        if self.id < 0 or not payload:
            return
        LOGGER.info(
            "send AVATAR player_id=%s avatar_id=%s bytes=%s model=%s/%s",
            self.id,
            avatar_id,
            len(payload),
            model_type,
            model_color,
        )
        chunks = [
            payload[index : index + AVATAR_CHUNK_PAYLOAD_SIZE]
            for index in range(0, len(payload), AVATAR_CHUNK_PAYLOAD_SIZE)
        ]
        if not self._sendto(pack_avatar_header(self.id, avatar_id, len(chunks), len(payload), model_type, model_color)):
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
            _tag, countdown_id, seconds_until_start = unpacked
            return CountdownEvent(countdown_id=countdown_id, seconds_until_start=seconds_until_start)
        if tag == CDWNX:
            unpacked = safe_unpack_cdwnx(data)
            if unpacked is None:
                return ErrorEvent("Malformed CDWNX packet")
            _tag, countdown_id, reason_code = unpacked
            return CountdownCancelEvent(countdown_id=countdown_id, reason_code=reason_code)
        if tag == GSTART:
            unpacked = safe_unpack_gstart(data)
            if unpacked is None:
                return ErrorEvent("Malformed GSTR packet")
            _tag, countdown_id, match_id, selected_level, level_seed, match_start_unix_sec = unpacked
            return GameStartEvent(
                countdown_id=countdown_id,
                match_id=match_id,
                selected_level=selected_level,
                level_seed=level_seed,
                match_start_unix_sec=int(match_start_unix_sec) & UINT32_MAX,
            )
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
            match_id, reason_code, standings = unpacked
            return GameEndEvent(match_id=match_id, reason_code=reason_code, standings=standings)
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
        if tag == HEARTBEAT_ACK:
            unpacked = safe_unpack_heartbeat_ack(data)
            if unpacked is None:
                return ErrorEvent("Malformed HBAK packet")
            _tag, server_state, countdown_id, match_id = unpacked
            return HeartbeatAckEvent(server_state=server_state, countdown_id=countdown_id, match_id=match_id)
        if tag == ROOM_NAME_UPDATE:
            unpacked = safe_unpack_room_name_update(data)
            if unpacked is None:
                return ErrorEvent("Malformed RNAM packet")
            _tag, _host_id, room_name = unpacked
            self.room_name = room_name
            return RoomNameEvent(room_name=room_name)
        if tag == LEVEL_SELECT:
            unpacked = safe_unpack_level_select(data)
            if unpacked is None:
                return ErrorEvent("Malformed LVSL packet")
            _tag, _host_id, level_id = unpacked
            self.selected_level = level_id
            return LevelSelectEvent(level_id=level_id)
        if tag == ORB_COLLECT:
            unpacked = safe_unpack_orb_collect(data)
            if unpacked is None:
                return ErrorEvent("Malformed ORBC packet")
            _tag, picker_id, orb_index, cooldown_sec = unpacked
            return OrbCollectEvent(player_id=picker_id, orb_index=orb_index, cooldown_sec=cooldown_sec)
        if tag == GOAL:
            unpacked = safe_unpack_goal(data)
            if unpacked is None:
                return ErrorEvent("Malformed GOAL packet")
            _tag, player_id = unpacked
            return GoalEvent(player_id=player_id)
        if tag == PLATFORM_PROGRESS:
            unpacked = safe_unpack_platform_progress(data)
            if unpacked is None:
                return ErrorEvent("Malformed PLAT packet")
            _tag, player_id, platforms_reached = unpacked
            return PlatformProgressEvent(player_id=player_id, platforms_reached=platforms_reached)
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
            _tag, player_id, avatar_id, total_chunks, payload_size, model_type, model_color = unpacked
            return AvatarHeaderEvent(
                player_id=player_id,
                avatar_id=avatar_id,
                total_chunks=total_chunks,
                payload_size=payload_size,
                model_type=model_type,
                model_color=model_color,
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
            if getattr(error, "winerror", None) == 10054:
                LOGGER.debug("UDP recv WinError 10054 ignored (transient ICMP)")
                return None
            return self._mark_connection_lost(f"Network receive failed: {error}")
        LOGGER.debug("recv packet tag=%s bytes=%s", _packet_tag_name(data), len(data))
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
            LOGGER.info("send DISCONNECT player_id=%s addr=%s", self.id, self.addr)
            self._sendto(msg, report_error=False)
        except OSError as error:
            LOGGER.error("Error disconnecting: %s", error)
