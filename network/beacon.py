import logging
import socket
import threading
from typing import Optional

try:
    from network.protocol import BEACON_INTERVAL, DISCOVERY_PORT, PROTO_VERSION, pack_beacon
    from network.room_state import RoomState
except ModuleNotFoundError:
    from protocol import BEACON_INTERVAL, DISCOVERY_PORT, PROTO_VERSION, pack_beacon  # type: ignore
    from room_state import RoomState  # type: ignore

LOGGER = logging.getLogger(__name__)


class BeaconBroadcaster:
    def __init__(
        self,
        room_state: RoomState,
        discovery_port: int = DISCOVERY_PORT,
        interval: float = BEACON_INTERVAL,
    ):
        self.room_state = room_state
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
        self._thread = threading.Thread(target=self._run, daemon=True, name="beacon-broadcaster")
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
            snapshot = self.room_state.snapshot()
            packet = pack_beacon(
                PROTO_VERSION,
                snapshot.current_players,
                snapshot.max_players,
                snapshot.state,
                snapshot.game_port,
                snapshot.room_name,
            )
            try:
                self._socket.sendto(packet, ("255.255.255.255", self.discovery_port))
            except OSError as error:
                LOGGER.debug("Beacon broadcast failed: %s", error)

            self._stop_event.wait(self.interval)
