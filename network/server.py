import argparse
import logging
import socket
import time
from typing import Optional

try:
    from network.beacon import BeaconBroadcaster
    from network.cooldown import KickCooldownTable
    from network.end_policy import GameEndPolicy
    from network.protocol import (
        BEACON_INTERVAL,
        CDWN,
        CONNECTION,
        CONNO_REASON_COOLDOWN,
        CONNO_REASON_FULL,
        CONNO_REASON_IN_GAME,
        CONNO_REASON_INVALID_NAME,
        CONNO_REASON_VERSION,
        COUNTDOWN_SECONDS,
        CDWNX_REASON_HOST_CANCELLED,
        CDWNX_REASON_HOST_LEFT,
        CDWNX_REASON_NOT_ENOUGH_PLAYERS,
        DEAD,
        DISCOVER,
        DISCOVERY_PORT,
        DISCONNECT,
        ELIM,
        GEND,
        GEND_REASON_FORFEIT,
        GEND_REASON_NORMAL,
        GSTART,
        KICK,
        KICKED_REASON_KICKED,
        KICKED_REASON_NOT_READY,
        KICKED_REASON_ROOM_CLOSED,
        MIN_PLAYERS,
        POSITION,
        PROTO_VERSION,
        READY,
        RECV_BUF,
        START,
        STATE_COUNTDOWN,
        STATE_IN_GAME,
        STATE_LOBBY,
        UINT32_MAX,
        is_valid_player_name,
        is_valid_room_name,
        pack_cdwn,
        pack_cdwnx,
        pack_conno,
        pack_conok,
        pack_elim,
        pack_gend,
        pack_gstart,
        pack_kicked,
        pack_list,
        pack_packet,
        safe_unpack,
        safe_unpack_conn,
        safe_unpack_dead,
        safe_unpack_kick,
        safe_unpack_ready,
        safe_unpack_start,
        tag_of,
    )
    from network.room_state import RoomState
except ModuleNotFoundError:
    from beacon import BeaconBroadcaster  # type: ignore
    from cooldown import KickCooldownTable  # type: ignore
    from end_policy import GameEndPolicy  # type: ignore
    from protocol import (  # type: ignore
        BEACON_INTERVAL,
        CDWN,
        CONNECTION,
        CONNO_REASON_COOLDOWN,
        CONNO_REASON_FULL,
        CONNO_REASON_IN_GAME,
        CONNO_REASON_INVALID_NAME,
        CONNO_REASON_VERSION,
        COUNTDOWN_SECONDS,
        CDWNX_REASON_HOST_CANCELLED,
        CDWNX_REASON_HOST_LEFT,
        CDWNX_REASON_NOT_ENOUGH_PLAYERS,
        DEAD,
        DISCOVER,
        DISCOVERY_PORT,
        DISCONNECT,
        ELIM,
        GEND,
        GEND_REASON_FORFEIT,
        GEND_REASON_NORMAL,
        GSTART,
        KICK,
        KICKED_REASON_KICKED,
        KICKED_REASON_NOT_READY,
        KICKED_REASON_ROOM_CLOSED,
        MIN_PLAYERS,
        POSITION,
        PROTO_VERSION,
        READY,
        RECV_BUF,
        START,
        STATE_COUNTDOWN,
        STATE_IN_GAME,
        STATE_LOBBY,
        UINT32_MAX,
        is_valid_player_name,
        is_valid_room_name,
        pack_cdwn,
        pack_cdwnx,
        pack_conno,
        pack_conok,
        pack_elim,
        pack_gend,
        pack_gstart,
        pack_kicked,
        pack_list,
        pack_packet,
        safe_unpack,
        safe_unpack_conn,
        safe_unpack_dead,
        safe_unpack_kick,
        safe_unpack_ready,
        safe_unpack_start,
        tag_of,
    )
    from room_state import RoomState  # type: ignore

LOGGER = logging.getLogger(__name__)
CLOSE_ROOM_TARGET = -1


class LobbyServer:
    def __init__(self, sock: socket.socket, room_state: RoomState, countdown_seconds: float):
        self.sock = sock
        self.room_state = room_state
        self.countdown_seconds = countdown_seconds
        self.cooldowns = KickCooldownTable()
        self.end_policy = GameEndPolicy()
        self.running = True
        self._last_cdwn_broadcast = 0.0

    def broadcast(self, payload: bytes, exclude_addr=None):
        for other_addr in self.room_state.peers(exclude_addr=exclude_addr):
            try:
                self.sock.sendto(payload, other_addr)
            except OSError as error:
                LOGGER.debug("Broadcast failed to %s: %s", other_addr, error)

    def broadcast_roster(self):
        if self.room_state.state == STATE_IN_GAME:
            return
        payload = pack_list(self.room_state.connected_roster_entries())
        self.broadcast(payload)

    def close_room(self):
        host_id = self.room_state.host_id
        for other_addr in self.room_state.peers():
            player_id = self.room_state.get_player_id_by_addr(other_addr)
            if player_id is None or player_id == host_id:
                continue
            try:
                self.sock.sendto(pack_kicked(KICKED_REASON_ROOM_CLOSED), other_addr)
            except OSError as error:
                LOGGER.debug("Failed to notify room closure to %s: %s", other_addr, error)
        self.running = False

    def reject_connection(self, addr, reason_code: int, extra: int = 0):
        payload = pack_conno(reason_code, extra)
        self.sock.sendto(payload, addr)

    def handle_conn(self, data: bytes, addr):
        unpacked = safe_unpack_conn(data)
        if unpacked is None:
            return

        _tag, proto_version, player_name = unpacked
        if not is_valid_player_name(player_name):
            self.reject_connection(addr, CONNO_REASON_INVALID_NAME, 0)
            return
        if proto_version != PROTO_VERSION:
            self.reject_connection(addr, CONNO_REASON_VERSION, 0)
            return
        if self.room_state.state in (STATE_COUNTDOWN, STATE_IN_GAME):
            self.reject_connection(addr, CONNO_REASON_IN_GAME, 0)
            return
        if self.room_state.connected_count() >= self.room_state.max_players:
            self.reject_connection(addr, CONNO_REASON_FULL, 0)
            return

        blocked, extra = self.cooldowns.check(player_name)
        if blocked:
            self.reject_connection(addr, CONNO_REASON_COOLDOWN, extra)
            return

        player_id, is_new = self.room_state.add_or_get_player(addr, player_name)
        if is_new:
            LOGGER.info("Accepted player %s (%s) as id %s", player_name, addr, player_id)
        start_x, start_y = self.room_state.start_position
        self.sock.sendto(pack_conok(player_id, self.room_state.room_name), addr)
        # Legacy client compatibility: existing main.py expects CONN with coordinates.
        self.sock.sendto(pack_packet(CONNECTION, start_x, start_y, player_id), addr)
        self.broadcast_roster()

    def handle_ready(self, data: bytes, addr):
        unpacked = safe_unpack_ready(data)
        if unpacked is None:
            return
        _tag, player_id, ready_flag = unpacked
        addr_player_id = self.room_state.get_player_id_by_addr(addr)
        if addr_player_id != player_id:
            return
        if self.room_state.state not in (STATE_LOBBY, STATE_COUNTDOWN):
            return
        self.room_state.set_ready(player_id, ready_flag)
        self.broadcast_roster()

    def start_countdown(self):
        now = time.monotonic()
        self.room_state.state = STATE_COUNTDOWN
        self.room_state.begin_countdown(now + self.countdown_seconds)
        self._last_cdwn_broadcast = 0.0
        self.broadcast(pack_cdwn(self.countdown_seconds))

    def cancel_countdown(self, reason_code: int):
        self.room_state.state = STATE_LOBBY
        self.room_state.cancel_countdown()
        self.broadcast(pack_cdwnx(reason_code))
        self.broadcast_roster()

    def handle_start(self, data: bytes, addr):
        unpacked = safe_unpack_start(data)
        if unpacked is None:
            return
        _tag, host_id = unpacked
        addr_player_id = self.room_state.get_player_id_by_addr(addr)
        if addr_player_id != host_id:
            return
        if host_id != self.room_state.host_id:
            return

        if self.room_state.state == STATE_LOBBY:
            if self.room_state.can_start():
                self.start_countdown()
            return

        if self.room_state.state == STATE_COUNTDOWN:
            self.cancel_countdown(CDWNX_REASON_HOST_CANCELLED)

    def _check_game_end_after_elimination(self):
        alive_ids = self.room_state.alive_ids()
        if len(alive_ids) == 1:
            winner_id = alive_ids[0]
            self.room_state.set_placement(winner_id, 1)
            standings = self.room_state.standings()
            self.broadcast(pack_gend(GEND_REASON_NORMAL, standings))
            self.room_state.state = STATE_LOBBY
            self.room_state.reset_for_lobby()
            self.broadcast_roster()
            return
        if len(alive_ids) == 0:
            standings = self.room_state.standings()
            self.broadcast(pack_gend(GEND_REASON_FORFEIT, standings))
            self.room_state.state = STATE_LOBBY
            self.room_state.reset_for_lobby()
            self.broadcast_roster()

    def eliminate_player(self, player_id: int):
        if not self.room_state.is_alive(player_id):
            return
        alive_before = self.room_state.alive_count()
        placement = max(1, alive_before)
        self.room_state.mark_eliminated(player_id, placement)
        self.broadcast(pack_elim(player_id, placement))
        self._check_game_end_after_elimination()

    def handle_dead(self, data: bytes, addr):
        unpacked = safe_unpack_dead(data)
        if unpacked is None:
            return
        _tag, player_id, _cause = unpacked
        addr_player_id = self.room_state.get_player_id_by_addr(addr)
        if addr_player_id != player_id:
            return
        if self.room_state.state != STATE_IN_GAME:
            return
        self.eliminate_player(player_id)

    def kick_player(self, target_player_id: int, reason_code: int):
        target_addr = self.room_state.get_addr_by_player_id(target_player_id)
        if target_addr is not None:
            self.sock.sendto(pack_kicked(reason_code), target_addr)

        target_name = self.room_state.player_name(target_player_id)
        if target_name:
            self.cooldowns.register_kick(target_name)

        self.room_state.remove_player(target_player_id)
        if self.room_state.state == STATE_COUNTDOWN and self.room_state.connected_count() < MIN_PLAYERS:
            self.cancel_countdown(CDWNX_REASON_NOT_ENOUGH_PLAYERS)
        else:
            self.broadcast_roster()

    def handle_kick(self, data: bytes, addr):
        unpacked = safe_unpack_kick(data)
        if unpacked is None:
            return
        _tag, host_id, target_player_id = unpacked
        addr_player_id = self.room_state.get_player_id_by_addr(addr)
        if addr_player_id != host_id or host_id != self.room_state.host_id:
            return

        if target_player_id == CLOSE_ROOM_TARGET:
            self.close_room()
            return
        if target_player_id == self.room_state.host_id:
            return
        if not self.room_state.player_exists(target_player_id):
            return

        if self.room_state.state == STATE_IN_GAME and self.room_state.is_alive(target_player_id):
            self.eliminate_player(target_player_id)
        self.kick_player(target_player_id, KICKED_REASON_KICKED)

    def handle_position(self, data: bytes, addr):
        unpacked = safe_unpack(data)
        if unpacked is None:
            return
        cmd, x, y, recv_id = unpacked
        if cmd != POSITION:
            return
        if self.room_state.state != STATE_IN_GAME:
            return
        player_id = self.room_state.get_player_id_by_addr(addr)
        if player_id is None or player_id != recv_id:
            return
        self.room_state.update_position(player_id, x, y)
        self.broadcast(pack_packet(POSITION, x, y, player_id), exclude_addr=addr)

    def handle_disconnect(self, data: bytes, addr):
        unpacked = safe_unpack(data)
        if unpacked is None:
            return
        cmd, _x, _y, recv_id = unpacked
        if cmd != DISCONNECT:
            return

        player_id = self.room_state.get_player_id_by_addr(addr)
        if player_id is None or player_id != recv_id:
            return

        if player_id == self.room_state.host_id:
            self.close_room()
            return

        if self.room_state.state == STATE_IN_GAME:
            if self.room_state.is_alive(player_id):
                self.eliminate_player(player_id)
            self.room_state.mark_disconnected(player_id)
            return

        self.room_state.remove_player(player_id)
        if self.room_state.state == STATE_COUNTDOWN and self.room_state.connected_count() < MIN_PLAYERS:
            self.cancel_countdown(CDWNX_REASON_NOT_ENOUGH_PLAYERS)
        else:
            self.broadcast_roster()

    def handle_discover(self, data: bytes, addr):
        unpacked = safe_unpack(data)
        if unpacked is None:
            return
        cmd, _x, _y, _id = unpacked
        if cmd != DISCOVER:
            return
        self.sock.sendto(pack_packet(DISCOVER, 0.0, 0.0, 0), addr)

    def handle_packet(self, data: bytes, addr):
        tag = tag_of(data)
        if tag is None:
            return

        if tag == DISCOVER:
            self.handle_discover(data, addr)
            return
        if tag == CONNECTION:
            self.handle_conn(data, addr)
            return
        if tag == READY:
            self.handle_ready(data, addr)
            return
        if tag == START:
            self.handle_start(data, addr)
            return
        if tag == KICK:
            self.handle_kick(data, addr)
            return
        if tag == DEAD:
            self.handle_dead(data, addr)
            return
        if tag == POSITION:
            self.handle_position(data, addr)
            return
        if tag == DISCONNECT:
            self.handle_disconnect(data, addr)

    def tick_countdown(self):
        if self.room_state.state != STATE_COUNTDOWN:
            return
        deadline = self.room_state.countdown_deadline
        if deadline is None:
            return
        now = time.monotonic()
        remaining = max(0.0, deadline - now)

        if self._last_cdwn_broadcast == 0.0 or (now - self._last_cdwn_broadcast) >= 1.0:
            self.broadcast(pack_cdwn(remaining))
            self._last_cdwn_broadcast = now

        if remaining > 0:
            return

        for player_id in self.room_state.non_ready_non_host_connected_ids():
            target_addr = self.room_state.get_addr_by_player_id(player_id)
            if target_addr is not None:
                self.sock.sendto(pack_kicked(KICKED_REASON_NOT_READY), target_addr)
            self.room_state.remove_player(player_id)

        if self.room_state.connected_count() < MIN_PLAYERS:
            self.cancel_countdown(CDWNX_REASON_NOT_ENOUGH_PLAYERS)
            return

        self.room_state.state = STATE_IN_GAME
        self.room_state.enter_game()
        self.broadcast(pack_gstart())

    def tick_in_game(self):
        if self.room_state.state != STATE_IN_GAME:
            return
        alive_positions = self.room_state.alive_positions()
        for player_id in self.end_policy.left_behind_candidates(alive_positions):
            self.eliminate_player(player_id)

    def tick(self):
        self.tick_countdown()
        self.tick_in_game()


def parse_args():
    parser = argparse.ArgumentParser(description="UDP game server")
    parser.add_argument("--host", default="0.0.0.0", help="Server bind address")
    parser.add_argument("--port", type=int, default=5555, help="Server bind port")
    parser.add_argument("--room", default="CS323Room", help="Room name advertised in LAN beacons")
    parser.add_argument("--discovery-port", type=int, default=DISCOVERY_PORT, help="UDP port used for room beacons")
    parser.add_argument("--beacon-interval", type=float, default=BEACON_INTERVAL, help="Seconds between beacon broadcasts")
    parser.add_argument("--countdown-seconds", type=float, default=COUNTDOWN_SECONDS, help="Countdown duration before game start")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging verbosity",
    )
    return parser.parse_args()


def configure_logging(log_level: str):
    logging.basicConfig(level=getattr(logging, log_level), format="[%(levelname)s] %(name)s: %(message)s")


def create_server(args) -> Optional[LobbyServer]:
    if not is_valid_room_name(args.room):
        LOGGER.error("Invalid room name '%s'. Room names must match ^[A-Za-z0-9]{3,24}$", args.room)
        return None

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.host, args.port))
    sock.settimeout(0.1)

    room_state = RoomState(room_name=args.room, game_port=args.port)
    beacon_broadcaster = BeaconBroadcaster(
        room_state=room_state,
        discovery_port=args.discovery_port,
        interval=args.beacon_interval,
    )
    beacon_broadcaster.start()

    server = LobbyServer(sock=sock, room_state=room_state, countdown_seconds=args.countdown_seconds)
    server._beacon_broadcaster = beacon_broadcaster  # Internal lifecycle handle.
    return server


def main():
    args = parse_args()
    configure_logging(args.log_level)

    server = create_server(args)
    if server is None:
        raise SystemExit(1)

    LOGGER.info("Server started on %s:%s (room=%s)", args.host, args.port, args.room)
    try:
        while server.running:
            try:
                data, addr = server.sock.recvfrom(RECV_BUF)
                server.handle_packet(data, addr)
            except socket.timeout:
                pass
            except ConnectionResetError:
                # Windows UDP: ICMP "port unreachable" from a prior send can make recvfrom raise this.
                LOGGER.debug("UDP recv ConnectionResetError ignored (transient ICMP)")
                continue
            except OSError as err:
                if getattr(err, "winerror", None) == 10054:
                    LOGGER.debug("UDP recv WinError 10054 ignored")
                    continue
                raise
            server.tick()
    except KeyboardInterrupt:
        LOGGER.info("Server shutting down...")
    finally:
        server._beacon_broadcaster.stop()
        server.sock.close()


if __name__ == "__main__":
    main()
