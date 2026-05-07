from dataclasses import dataclass
import secrets
import threading
import time
from typing import Dict, List, Optional, Tuple

try:
    from network.protocol import MAX_PLAYERS, MIN_PLAYERS, RECONNECT_GRACE_SECONDS, STATE_LOBBY, normalize_player_name
except ModuleNotFoundError:
    from protocol import MAX_PLAYERS, MIN_PLAYERS, RECONNECT_GRACE_SECONDS, STATE_LOBBY, normalize_player_name  # type: ignore

Address = Tuple[str, int]
Position = Tuple[float, float]


@dataclass
class PlayerEntry:
    player_id: int
    name: str
    session_token: int
    ready: bool
    alive: bool
    connected: bool
    placement: Optional[int]
    last_seen: float
    disconnected_at: Optional[float] = None
    reconnect_deadline: Optional[float] = None


@dataclass(frozen=True)
class RoomSnapshot:
    room_name: str
    current_players: int
    max_players: int
    state: int
    game_port: int


class RoomState:
    def __init__(self, room_name: str, game_port: int):
        self.lock = threading.Lock()
        self.room_name = room_name
        self.state = STATE_LOBBY
        self.game_port = game_port
        self.max_players = MAX_PLAYERS
        self.min_players = MIN_PLAYERS
        self.start_position: Position = (100.0, 100.0)
        self.countdown_deadline: Optional[float] = None
        self.host_id: Optional[int] = None

        self._next_player_id = 0
        self._players: Dict[int, PlayerEntry] = {}
        self._addr_to_id: Dict[Address, int] = {}
        self._positions: Dict[int, Position] = {}

    def _spawn_position_for_index(self, index: int) -> Position:
        start_x, start_y = self.start_position
        return (start_x + (12.0 * index), start_y)

    def snapshot(self) -> RoomSnapshot:
        with self.lock:
            return RoomSnapshot(
                room_name=self.room_name,
                current_players=len(self._addr_to_id),
                max_players=self.max_players,
                state=self.state,
                game_port=self.game_port,
            )

    def set_room_name(self, room_name: str):
        with self.lock:
            self.room_name = room_name

    def connected_count(self) -> int:
        with self.lock:
            return len(self._addr_to_id)

    def get_player_id_by_addr(self, addr: Address) -> Optional[int]:
        with self.lock:
            return self._addr_to_id.get(addr)

    def connected_player_name_taken(self, name: str, exclude_addr: Optional[Address] = None) -> bool:
        with self.lock:
            requested_name = normalize_player_name(name)
            excluded_player_id = self._addr_to_id.get(exclude_addr) if exclude_addr is not None else None
            for player_id, player in self._players.items():
                if player_id == excluded_player_id:
                    continue
                if player.connected and normalize_player_name(player.name) == requested_name:
                    return True
            return False

    def get_addr_by_player_id(self, player_id: int) -> Optional[Address]:
        with self.lock:
            for addr, pid in self._addr_to_id.items():
                if pid == player_id:
                    return addr
            return None

    def add_or_get_player(self, addr: Address, name: str) -> Tuple[int, bool]:
        with self.lock:
            if addr in self._addr_to_id:
                player_id = self._addr_to_id[addr]
                player = self._players.get(player_id)
                if player is not None:
                    player.last_seen = time.monotonic()
                return player_id, False

            player_id = self._next_player_id
            self._next_player_id += 1
            self._addr_to_id[addr] = player_id
            self._positions[player_id] = self.start_position
            token = secrets.randbits(32) or 1
            now = time.monotonic()

            self._players[player_id] = PlayerEntry(
                player_id=player_id,
                name=name,
                session_token=token,
                ready=False,
                alive=False,
                connected=True,
                placement=None,
                last_seen=now,
            )
            if self.host_id is None:
                self.host_id = player_id
            return player_id, True

    def session_token(self, player_id: int) -> Optional[int]:
        with self.lock:
            player = self._players.get(player_id)
            return None if player is None else player.session_token

    def touch_player(self, player_id: int, now: Optional[float] = None):
        with self.lock:
            player = self._players.get(player_id)
            if player is not None and player.connected:
                player.last_seen = time.monotonic() if now is None else now

    def touch_addr(self, addr: Address, now: Optional[float] = None) -> Optional[int]:
        with self.lock:
            player_id = self._addr_to_id.get(addr)
            if player_id is None:
                return None
            player = self._players.get(player_id)
            if player is not None and player.connected:
                player.last_seen = time.monotonic() if now is None else now
            return player_id

    def update_position(self, player_id: int, x: float, y: float):
        with self.lock:
            if player_id in self._players:
                self._positions[player_id] = (x, y)

    def get_position(self, player_id: int) -> Optional[Position]:
        with self.lock:
            return self._positions.get(player_id)

    def player_name(self, player_id: int) -> Optional[str]:
        with self.lock:
            player = self._players.get(player_id)
            return None if player is None else player.name

    def player_exists(self, player_id: int) -> bool:
        with self.lock:
            return player_id in self._players

    def mark_disconnected(
        self,
        player_id: int,
        now: Optional[float] = None,
        grace_seconds: float = RECONNECT_GRACE_SECONDS,
    ):
        with self.lock:
            player = self._players.get(player_id)
            if player is None:
                return
            now = time.monotonic() if now is None else now
            player.connected = False
            player.disconnected_at = now
            player.reconnect_deadline = now + max(0.0, grace_seconds)
            for addr, pid in list(self._addr_to_id.items()):
                if pid == player_id:
                    del self._addr_to_id[addr]
                    break

    def reconnect_player(
        self,
        addr: Address,
        player_id: int,
        session_token: int,
        now: Optional[float] = None,
    ) -> Optional[Position]:
        with self.lock:
            player = self._players.get(player_id)
            if player is None:
                return None
            now = time.monotonic() if now is None else now
            if player.session_token != session_token:
                return None
            if player.connected:
                return None
            if not player.alive:
                return None
            if player.reconnect_deadline is not None and now > player.reconnect_deadline:
                return None
            for old_addr, pid in list(self._addr_to_id.items()):
                if old_addr == addr or pid == player_id:
                    del self._addr_to_id[old_addr]
            self._addr_to_id[addr] = player_id
            player.connected = True
            player.ready = False
            player.last_seen = now
            player.disconnected_at = None
            player.reconnect_deadline = None
            return self._positions.get(player_id, self.start_position)

    def reconnect_player_by_name(
        self,
        addr: Address,
        player_name: str,
        now: Optional[float] = None,
    ) -> Optional[Tuple[int, Position, int]]:
        with self.lock:
            now = time.monotonic() if now is None else now
            requested_name = normalize_player_name(player_name)
            matches = []
            for player_id, player in self._players.items():
                if normalize_player_name(player.name) != requested_name:
                    continue
                if not player.alive or player.connected:
                    continue
                if player.reconnect_deadline is not None and now > player.reconnect_deadline:
                    continue
                matches.append(player_id)

            if len(matches) != 1:
                return None

            player_id = matches[0]
            player = self._players[player_id]
            for old_addr, pid in list(self._addr_to_id.items()):
                if old_addr == addr or pid == player_id:
                    del self._addr_to_id[old_addr]
            self._addr_to_id[addr] = player_id
            player.connected = True
            player.ready = False
            player.last_seen = now
            player.disconnected_at = None
            player.reconnect_deadline = None
            return player_id, self._positions.get(player_id, self.start_position), player.session_token

    def remove_player(self, player_id: int):
        with self.lock:
            self._players.pop(player_id, None)
            self._positions.pop(player_id, None)
            for addr, pid in list(self._addr_to_id.items()):
                if pid == player_id:
                    del self._addr_to_id[addr]
                    break
            if self.host_id == player_id:
                self.host_id = None

    def disconnect_remaining(self, player_id: int, now: Optional[float] = None) -> float:
        with self.lock:
            player = self._players.get(player_id)
            if player is None or player.reconnect_deadline is None:
                return 0.0
            now = time.monotonic() if now is None else now
            return max(0.0, player.reconnect_deadline - now)

    def disconnected_alive_ids(self) -> List[int]:
        with self.lock:
            return sorted(
                player_id
                for player_id, player in self._players.items()
                if player.alive and not player.connected
            )

    def has_disconnected_alive_players(self) -> bool:
        with self.lock:
            return any(player.alive and not player.connected for player in self._players.values())

    def timed_out_connected_alive_ids(self, now: float, timeout_seconds: float) -> List[int]:
        with self.lock:
            output: List[int] = []
            for player_id, player in self._players.items():
                if not player.alive or not player.connected:
                    continue
                if (now - player.last_seen) > timeout_seconds:
                    output.append(player_id)
            return sorted(output)

    def expired_reconnect_ids(self, now: float) -> List[int]:
        with self.lock:
            output: List[int] = []
            for player_id, player in self._players.items():
                if not player.alive or player.connected:
                    continue
                if player.reconnect_deadline is not None and now >= player.reconnect_deadline:
                    output.append(player_id)
            return sorted(output)

    def peers(self, exclude_addr: Optional[Address] = None) -> List[Address]:
        with self.lock:
            if exclude_addr is None:
                return list(self._addr_to_id.keys())
            return [addr for addr in self._addr_to_id.keys() if addr != exclude_addr]

    def connected_roster_entries(self) -> List[Tuple[int, bool, str]]:
        with self.lock:
            entries: List[Tuple[int, bool, str]] = []
            for player_id in sorted(self._players.keys()):
                player = self._players[player_id]
                if player.connected:
                    entries.append((player.player_id, player.ready, player.name))
            return entries

    def set_ready(self, player_id: int, ready_flag: bool):
        with self.lock:
            player = self._players.get(player_id)
            if player is None or not player.connected:
                return
            player.ready = ready_flag

    def all_non_host_ready(self) -> bool:
        with self.lock:
            if self.host_id is None:
                return False
            for player in self._players.values():
                if not player.connected:
                    continue
                if player.player_id == self.host_id:
                    continue
                if not player.ready:
                    return False
            return True

    def can_start(self) -> bool:
        with self.lock:
            if self.host_id is None:
                return False
            if len(self._addr_to_id) < self.min_players:
                return False
            for player in self._players.values():
                if not player.connected:
                    continue
                if player.player_id == self.host_id:
                    continue
                if not player.ready:
                    return False
            return True

    def begin_countdown(self, deadline_monotonic: float):
        with self.lock:
            self.countdown_deadline = deadline_monotonic

    def cancel_countdown(self):
        with self.lock:
            self.countdown_deadline = None

    def non_ready_non_host_connected_ids(self) -> List[int]:
        with self.lock:
            if self.host_id is None:
                return []
            output = []
            for player_id, player in self._players.items():
                if not player.connected:
                    continue
                if player_id == self.host_id:
                    continue
                if not player.ready:
                    output.append(player_id)
            return sorted(output)

    def enter_game(self):
        with self.lock:
            self.countdown_deadline = None
            now = time.monotonic()
            spawn_index = 0
            for player_id in sorted(self._players.keys()):
                player = self._players[player_id]
                if player.connected:
                    self._positions[player_id] = self._spawn_position_for_index(spawn_index)
                    spawn_index += 1
                    player.alive = True
                    player.placement = None
                    player.last_seen = now
                    player.disconnected_at = None
                    player.reconnect_deadline = None

    def connected_positions(self) -> Dict[int, Position]:
        with self.lock:
            positions: Dict[int, Position] = {}
            for player_id, player in self._players.items():
                if player.connected and player_id in self._positions:
                    positions[player_id] = self._positions[player_id]
            return positions

    def alive_ids(self) -> List[int]:
        with self.lock:
            return sorted([player_id for player_id, player in self._players.items() if player.alive])

    def alive_count(self) -> int:
        with self.lock:
            return sum(1 for player in self._players.values() if player.alive)

    def is_alive(self, player_id: int) -> bool:
        with self.lock:
            player = self._players.get(player_id)
            return False if player is None else player.alive

    def mark_eliminated(self, player_id: int, placement: int):
        with self.lock:
            player = self._players.get(player_id)
            if player is None:
                return
            player.alive = False
            player.placement = placement

    def set_placement(self, player_id: int, placement: int):
        with self.lock:
            player = self._players.get(player_id)
            if player is None:
                return
            player.placement = placement

    def standings(self) -> List[Tuple[int, int, str]]:
        with self.lock:
            rows: List[Tuple[int, int, str]] = []
            for player_id, player in self._players.items():
                placement = player.placement if player.placement is not None else 255
                rows.append((player_id, placement, player.name))
            rows.sort(key=lambda row: (row[1], row[0]))
            return rows

    def reset_for_lobby(self):
        with self.lock:
            self.countdown_deadline = None
            disconnected_ids = [player_id for player_id, player in self._players.items() if not player.connected]
            for player_id in disconnected_ids:
                self._players.pop(player_id, None)
                self._positions.pop(player_id, None)
            for player in self._players.values():
                player.ready = False
                player.alive = False
                player.placement = None

    def alive_positions(self) -> Dict[int, Position]:
        with self.lock:
            positions: Dict[int, Position] = {}
            for player_id, player in self._players.items():
                if player.alive and player_id in self._positions:
                    positions[player_id] = self._positions[player_id]
            return positions
