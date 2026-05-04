from dataclasses import dataclass
import logging
import socket
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

try:
    from network.protocol import (
        BEACON_INTERVAL,
        BEACON_TTL,
        DISCOVERY_PORT,
        PRESENCE_STATUS_ONLINE,
        PROTO_VERSION,
        RECV_BUF,
        pack_presence,
        safe_unpack_beacon,
        safe_unpack_presence,
    )
except ModuleNotFoundError:
    from protocol import (  # type: ignore
        BEACON_INTERVAL,
        BEACON_TTL,
        DISCOVERY_PORT,
        PRESENCE_STATUS_ONLINE,
        PROTO_VERSION,
        RECV_BUF,
        pack_presence,
        safe_unpack_beacon,
        safe_unpack_presence,
    )

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RoomEntry:
    addr: str
    game_port: int
    room_name: str
    current_players: int
    max_players: int
    state: int
    last_seen: float


@dataclass(frozen=True)
class PresenceEntry:
    addr: str
    instance_id: int
    player_name: str
    status: int
    last_seen: float


def beacon_to_room_entry(data: bytes, source_addr: Tuple[str, int]) -> Optional[RoomEntry]:
    """Unpack a BCON datagram and validate protocol version (for tests + single call site)."""
    unpacked = safe_unpack_beacon(data)
    if unpacked is None:
        return None
    _tag, proto_version, cur, max_players, state, game_port, room_name = unpacked
    if proto_version != PROTO_VERSION:
        LOGGER.debug("Ignoring beacon with unsupported protocol version %s", proto_version)
        return None
    host_ip = source_addr[0]
    return RoomEntry(
        addr=host_ip,
        game_port=game_port,
        room_name=room_name,
        current_players=cur,
        max_players=max_players,
        state=state,
        last_seen=time.monotonic(),
    )


def presence_to_entry(data: bytes, source_addr: Tuple[str, int]) -> Optional[PresenceEntry]:
    unpacked = safe_unpack_presence(data)
    if unpacked is None:
        return None
    _tag, proto_version, instance_id, status, player_name = unpacked
    if proto_version != PROTO_VERSION:
        LOGGER.debug("Ignoring presence with unsupported protocol version %s", proto_version)
        return None
    if not player_name:
        return None
    return PresenceEntry(
        addr=source_addr[0],
        instance_id=instance_id,
        player_name=player_name,
        status=status,
        last_seen=time.monotonic(),
    )


class PresenceBroadcaster:
    def __init__(
        self,
        instance_id: int,
        player_name_provider: Callable[[], str],
        status_provider: Callable[[], int] | None = None,
        discovery_port: int = DISCOVERY_PORT,
        interval: float = BEACON_INTERVAL,
    ):
        self.instance_id = instance_id
        self.player_name_provider = player_name_provider
        self.status_provider = status_provider or (lambda: PRESENCE_STATUS_ONLINE)
        self.discovery_port = discovery_port
        self.interval = interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._socket: Optional[socket.socket] = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._thread = threading.Thread(target=self._run, daemon=True, name="presence-broadcaster")
        self._thread.start()

    def stop(self, timeout: float = 2.0):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def _run(self):
        if self._socket is None:
            return
        while not self._stop_event.is_set():
            name = self.player_name_provider()
            packet = pack_presence(PROTO_VERSION, self.instance_id, self.status_provider(), name)
            try:
                self._socket.sendto(packet, ("255.255.255.255", self.discovery_port))
            except OSError as error:
                LOGGER.debug("Presence broadcast failed: %s", error)
            self._stop_event.wait(self.interval)


class LobbyBrowser:
    def __init__(self, discovery_port: int = DISCOVERY_PORT, ttl: float = BEACON_TTL):
        self.discovery_port = discovery_port
        self.ttl = ttl
        self._rooms: Dict[Tuple[str, int], RoomEntry] = {}
        self._presence: Dict[Tuple[str, int], PresenceEntry] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind(("", self.discovery_port))
        self._socket.settimeout(0.5)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._listen, daemon=True, name="lobby-browser")
        self._thread.start()

    def stop(self, timeout: float = 2.0):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._socket.close()

    def snapshot(self) -> List[RoomEntry]:
        now = time.monotonic()
        with self._lock:
            stale_keys = [key for key, room in self._rooms.items() if now - room.last_seen > self.ttl]
            for key in stale_keys:
                del self._rooms[key]
            return sorted(self._rooms.values(), key=lambda room: (room.room_name, room.addr, room.game_port))

    def presence_snapshot(self) -> List[PresenceEntry]:
        now = time.monotonic()
        with self._lock:
            stale_keys = [key for key, entry in self._presence.items() if now - entry.last_seen > self.ttl]
            for key in stale_keys:
                del self._presence[key]
            return sorted(self._presence.values(), key=lambda entry: (entry.player_name, entry.addr, entry.instance_id))

    def _listen(self):
        while not self._stop_event.is_set():
            try:
                data, addr = self._socket.recvfrom(RECV_BUF)
            except socket.timeout:
                continue
            except OSError:
                break

            room_entry = beacon_to_room_entry(data, addr)
            if room_entry is not None:
                with self._lock:
                    self._rooms[(room_entry.addr, room_entry.game_port)] = room_entry
                continue

            presence_entry = presence_to_entry(data, addr)
            if presence_entry is not None:
                with self._lock:
                    self._presence[(presence_entry.addr, presence_entry.instance_id)] = presence_entry
