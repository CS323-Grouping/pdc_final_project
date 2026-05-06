from dataclasses import dataclass
import threading
from typing import Dict, List, Optional, Tuple

try:
    from network.protocol import MAX_PLAYERS, MIN_PLAYERS, STATE_LOBBY
except ModuleNotFoundError:
    from protocol import MAX_PLAYERS, MIN_PLAYERS, STATE_LOBBY  # type: ignore

Address = Tuple[str, int]
Position = Tuple[float, float]


@dataclass
class PlayerEntry:
    player_id: int
    name: str
    ready: bool
    alive: bool
    connected: bool
    placement: Optional[int]


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

    def snapshot(self) -> RoomSnapshot:
        with self.lock:
            return RoomSnapshot(
                room_name=self.room_name,
                current_players=len(self._addr_to_id),
                max_players=self.max_players,
                state=self.state,
                game_port=self.game_port,
            )

    def connected_count(self) -> int:
        with self.lock:
            return len(self._addr_to_id)

    def get_player_id_by_addr(self, addr: Address) -> Optional[int]:
        with self.lock:
            return self._addr_to_id.get(addr)

    def get_addr_by_player_id(self, player_id: int) -> Optional[Address]:
        with self.lock:
            for addr, pid in self._addr_to_id.items():
                if pid == player_id:
                    return addr
            return None

    def add_or_get_player(self, addr: Address, name: str) -> Tuple[int, bool]:
        with self.lock:
            if addr in self._addr_to_id:
                return self._addr_to_id[addr], False

            player_id = self._next_player_id
            self._next_player_id += 1
            self._addr_to_id[addr] = player_id
            self._positions[player_id] = self.start_position

            self._players[player_id] = PlayerEntry(
                player_id=player_id,
                name=name,
                ready=False,
                alive=False,
                connected=True,
                placement=None,
            )
            if self.host_id is None:
                self.host_id = player_id
            return player_id, True

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

    def mark_disconnected(self, player_id: int):
        with self.lock:
            player = self._players.get(player_id)
            if player is None:
                return
            player.connected = False
            for addr, pid in list(self._addr_to_id.items()):
                if pid == player_id:
                    del self._addr_to_id[addr]
                    break

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
            for player in self._players.values():
                if player.connected:
                    player.alive = True
                    player.placement = None

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
