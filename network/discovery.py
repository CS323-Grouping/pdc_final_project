from dataclasses import dataclass
import logging
import socket
import threading
import time
from typing import Dict, List, Optional, Tuple

try:
    from network.protocol import BEACON_TTL, DISCOVERY_PORT, PROTO_VERSION, RECV_BUF, safe_unpack_beacon
except ModuleNotFoundError:
    from protocol import BEACON_TTL, DISCOVERY_PORT, PROTO_VERSION, RECV_BUF, safe_unpack_beacon  # type: ignore

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


class LobbyBrowser:
    def __init__(self, discovery_port: int = DISCOVERY_PORT, ttl: float = BEACON_TTL):
        self.discovery_port = discovery_port
        self.ttl = ttl
        self._rooms: Dict[Tuple[str, int], RoomEntry] = {}
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

    def _listen(self):
        while not self._stop_event.is_set():
            try:
                data, addr = self._socket.recvfrom(RECV_BUF)
            except socket.timeout:
                continue
            except OSError:
                break

            room_entry = beacon_to_room_entry(data, addr)
            if room_entry is None:
                continue

            with self._lock:
                self._rooms[(room_entry.addr, room_entry.game_port)] = room_entry
