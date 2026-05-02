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
        AVATAR_CHUNK,
        AVATAR_HEADER,
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
        MATCH_PAUSE,
        MATCH_RESUME,
        PLAYER_TIMEOUT_SECONDS,
        PLAYER_STATE,
        POSITION,
        PROTO_VERSION,
        READY,
        RECV_BUF,
        RECONNECT,
        RECONNECT_DENY_BAD_TOKEN,
        RECONNECT_DENY_EXPIRED,
        RECONNECT_DENY_NOT_IN_GAME,
        RECONNECT_DENY_NO_SLOT,
        RECONNECT_GRACE_SECONDS,
        START,
        STATE_COUNTDOWN,
        STATE_IN_GAME,
        STATE_LOBBY,
        STATE_PAUSED,
        UINT32_MAX,
        is_valid_player_name,
        is_valid_room_name,
        pack_cdwn,
        pack_cdwnx,
        pack_avatar_chunk,
        pack_avatar_header,
        pack_conno,
        pack_conok,
        pack_elim,
        pack_gend,
        pack_gstart,
        pack_kicked,
        pack_list,
        pack_match_pause,
        pack_match_resume,
        pack_packet,
        pack_player_state,
        pack_reconnect_no,
        pack_reconnect_ok,
        pack_session,
        safe_unpack,
        safe_unpack_avatar_chunk,
        safe_unpack_avatar_header,
        safe_unpack_conn,
        safe_unpack_dead,
        safe_unpack_kick,
        safe_unpack_player_state,
        safe_unpack_ready,
        safe_unpack_reconnect,
        safe_unpack_start,
        tag_of,
    )
    from network.room_state import RoomState
except ModuleNotFoundError:
    from beacon import BeaconBroadcaster  # type: ignore
    from cooldown import KickCooldownTable  # type: ignore
    from end_policy import GameEndPolicy  # type: ignore
    from protocol import (  # type: ignore
        AVATAR_CHUNK,
        AVATAR_HEADER,
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
        MATCH_PAUSE,
        MATCH_RESUME,
        PLAYER_TIMEOUT_SECONDS,
        PLAYER_STATE,
        POSITION,
        PROTO_VERSION,
        READY,
        RECV_BUF,
        RECONNECT,
        RECONNECT_DENY_BAD_TOKEN,
        RECONNECT_DENY_EXPIRED,
        RECONNECT_DENY_NOT_IN_GAME,
        RECONNECT_DENY_NO_SLOT,
        RECONNECT_GRACE_SECONDS,
        START,
        STATE_COUNTDOWN,
        STATE_IN_GAME,
        STATE_LOBBY,
        STATE_PAUSED,
        UINT32_MAX,
        is_valid_player_name,
        is_valid_room_name,
        pack_cdwn,
        pack_cdwnx,
        pack_avatar_chunk,
        pack_avatar_header,
        pack_conno,
        pack_conok,
        pack_elim,
        pack_gend,
        pack_gstart,
        pack_kicked,
        pack_list,
        pack_match_pause,
        pack_match_resume,
        pack_packet,
        pack_player_state,
        pack_reconnect_no,
        pack_reconnect_ok,
        pack_session,
        safe_unpack,
        safe_unpack_avatar_chunk,
        safe_unpack_avatar_header,
        safe_unpack_conn,
        safe_unpack_dead,
        safe_unpack_kick,
        safe_unpack_player_state,
        safe_unpack_ready,
        safe_unpack_reconnect,
        safe_unpack_start,
        tag_of,
    )
    from room_state import RoomState  # type: ignore

LOGGER = logging.getLogger(__name__)
CLOSE_ROOM_TARGET = -1


class LobbyServer:
    def __init__(
        self,
        sock: socket.socket,
        room_state: RoomState,
        countdown_seconds: float,
        reconnect_grace_seconds: float = RECONNECT_GRACE_SECONDS,
        player_timeout_seconds: float = PLAYER_TIMEOUT_SECONDS,
    ):
        self.sock = sock
        self.room_state = room_state
        self.countdown_seconds = countdown_seconds
        self.reconnect_grace_seconds = reconnect_grace_seconds
        self.player_timeout_seconds = player_timeout_seconds
        self.cooldowns = KickCooldownTable()
        self.end_policy = GameEndPolicy()
        self.running = True
        self._last_cdwn_broadcast = 0.0
        self._last_pause_broadcast = 0.0

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

    def broadcast_pause(self):
        now = time.monotonic()
        disconnected_ids = self.room_state.disconnected_alive_ids()
        for player_id in disconnected_ids:
            remaining = self.room_state.disconnect_remaining(player_id, now)
            self.broadcast(pack_match_pause(player_id, remaining))
        self._last_pause_broadcast = now

    def pause_for_disconnect(self, player_id: int, now: Optional[float] = None):
        if not self.room_state.is_alive(player_id):
            return
        now = time.monotonic() if now is None else now
        self.room_state.mark_disconnected(player_id, now, self.reconnect_grace_seconds)
        self.room_state.state = STATE_PAUSED
        self.broadcast_pause()

    def resume_if_ready(self):
        if self.room_state.state != STATE_PAUSED:
            return
        if self.room_state.has_disconnected_alive_players():
            return
        self.room_state.state = STATE_IN_GAME
        self._last_pause_broadcast = 0.0
        self.broadcast(pack_match_resume())

    def broadcast_match_snapshot(self):
        for player_id, (x, y) in self.room_state.connected_positions().items():
            self.broadcast(pack_player_state(x, y, player_id, "idle_front"))

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
        if self.room_state.state in (STATE_COUNTDOWN, STATE_IN_GAME, STATE_PAUSED):
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
        session_token = self.room_state.session_token(player_id) or 0
        self.sock.sendto(pack_session(player_id, session_token), addr)
        self.sock.sendto(pack_conok(player_id, self.room_state.room_name), addr)
        # Legacy client compatibility: existing main.py expects CONN with coordinates.
        self.sock.sendto(pack_packet(CONNECTION, start_x, start_y, player_id), addr)
        self.broadcast_roster()

    def handle_reconnect(self, data: bytes, addr):
        unpacked = safe_unpack_reconnect(data)
        if unpacked is None:
            self.sock.sendto(pack_reconnect_no(RECONNECT_DENY_NO_SLOT), addr)
            return

        _tag, proto_version, player_id, session_token, player_name = unpacked
        if proto_version != PROTO_VERSION:
            self.sock.sendto(pack_reconnect_no(RECONNECT_DENY_NOT_IN_GAME), addr)
            return
        if not is_valid_player_name(player_name):
            self.sock.sendto(pack_reconnect_no(RECONNECT_DENY_NO_SLOT), addr)
            return
        if self.room_state.state not in (STATE_IN_GAME, STATE_PAUSED):
            self.sock.sendto(pack_reconnect_no(RECONNECT_DENY_NOT_IN_GAME), addr)
            return
        if not self.room_state.player_exists(player_id):
            self.sock.sendto(pack_reconnect_no(RECONNECT_DENY_NO_SLOT), addr)
            return
        expected = self.room_state.session_token(player_id)
        if expected != session_token:
            self.sock.sendto(pack_reconnect_no(RECONNECT_DENY_BAD_TOKEN), addr)
            return
        if self.room_state.disconnect_remaining(player_id) <= 0:
            self.sock.sendto(pack_reconnect_no(RECONNECT_DENY_EXPIRED), addr)
            return

        position = self.room_state.reconnect_player(addr, player_id, session_token)
        if position is None:
            self.sock.sendto(pack_reconnect_no(RECONNECT_DENY_EXPIRED), addr)
            return

        LOGGER.info("Reconnected player %s (%s) as id %s", player_name, addr, player_id)
        self.sock.sendto(pack_session(player_id, session_token), addr)
        self.sock.sendto(pack_reconnect_ok(player_id, position[0], position[1], self.room_state.room_name), addr)
        self.resume_if_ready()
        if self.room_state.state == STATE_PAUSED:
            self.broadcast_pause()

    def handle_ready(self, data: bytes, addr):
        unpacked = safe_unpack_ready(data)
        if unpacked is None:
            return
        _tag, player_id, ready_flag = unpacked
        addr_player_id = self.room_state.get_player_id_by_addr(addr)
        if addr_player_id != player_id:
            return
        self.room_state.touch_player(player_id)
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
        self.room_state.touch_player(host_id)
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
        self.room_state.touch_player(player_id)
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
        self.room_state.touch_player(host_id)

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
        if self.room_state.state not in (STATE_IN_GAME, STATE_PAUSED):
            return
        player_id = self.room_state.get_player_id_by_addr(addr)
        if player_id is None or player_id != recv_id:
            return
        self.room_state.touch_player(player_id)
        if self.room_state.state == STATE_PAUSED:
            return
        self.room_state.update_position(player_id, x, y)
        self.broadcast(pack_packet(POSITION, x, y, player_id), exclude_addr=addr)

    def handle_player_state(self, data: bytes, addr):
        unpacked = safe_unpack_player_state(data)
        if unpacked is None:
            return
        _cmd, x, y, recv_id, state_id = unpacked
        if self.room_state.state not in (STATE_IN_GAME, STATE_PAUSED):
            return
        player_id = self.room_state.get_player_id_by_addr(addr)
        if player_id is None or player_id != recv_id:
            return
        self.room_state.touch_player(player_id)
        if self.room_state.state == STATE_PAUSED:
            return
        self.room_state.update_position(player_id, x, y)
        self.broadcast(pack_player_state(x, y, player_id, state_id), exclude_addr=addr)

    def handle_avatar_header(self, data: bytes, addr):
        unpacked = safe_unpack_avatar_header(data)
        if unpacked is None:
            return
        _cmd, recv_id, avatar_id, total_chunks, payload_size = unpacked
        player_id = self.room_state.get_player_id_by_addr(addr)
        if player_id is None or player_id != recv_id:
            return
        self.room_state.touch_player(player_id)
        self.broadcast(
            pack_avatar_header(player_id, avatar_id, total_chunks, payload_size),
            exclude_addr=addr,
        )

    def handle_avatar_chunk(self, data: bytes, addr):
        unpacked = safe_unpack_avatar_chunk(data)
        if unpacked is None:
            return
        _cmd, recv_id, avatar_id, chunk_index, total_chunks, payload = unpacked
        player_id = self.room_state.get_player_id_by_addr(addr)
        if player_id is None or player_id != recv_id:
            return
        self.room_state.touch_player(player_id)
        self.broadcast(
            pack_avatar_chunk(player_id, avatar_id, chunk_index, total_chunks, payload),
            exclude_addr=addr,
        )

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

        self.room_state.touch_player(player_id)

        if player_id == self.room_state.host_id and self.room_state.state not in (STATE_IN_GAME, STATE_PAUSED):
            self.close_room()
            return

        if self.room_state.state in (STATE_IN_GAME, STATE_PAUSED):
            if self.room_state.is_alive(player_id):
                self.pause_for_disconnect(player_id)
            else:
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
        if tag == RECONNECT:
            self.handle_reconnect(data, addr)
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
        if tag == PLAYER_STATE:
            self.handle_player_state(data, addr)
            return
        if tag == AVATAR_HEADER:
            self.handle_avatar_header(data, addr)
            return
        if tag == AVATAR_CHUNK:
            self.handle_avatar_chunk(data, addr)
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
        self.broadcast_match_snapshot()

    def tick_in_game(self):
        if self.room_state.state != STATE_IN_GAME:
            return
        now = time.monotonic()
        timed_out = self.room_state.timed_out_connected_alive_ids(now, self.player_timeout_seconds)
        if timed_out:
            self.pause_for_disconnect(timed_out[0], now)
            return
        alive_positions = self.room_state.alive_positions()
        for player_id in self.end_policy.left_behind_candidates(alive_positions):
            self.eliminate_player(player_id)

    def tick_paused(self):
        if self.room_state.state != STATE_PAUSED:
            return
        now = time.monotonic()
        for player_id in self.room_state.timed_out_connected_alive_ids(now, self.player_timeout_seconds):
            self.pause_for_disconnect(player_id, now)
            if self.room_state.state != STATE_PAUSED:
                return

        if self._last_pause_broadcast == 0.0 or (now - self._last_pause_broadcast) >= 1.0:
            self.broadcast_pause()

        expired_ids = self.room_state.expired_reconnect_ids(now)
        for player_id in expired_ids:
            self.eliminate_player(player_id)
            if self.room_state.state != STATE_PAUSED:
                return

        self.resume_if_ready()

    def tick(self):
        self.tick_countdown()
        self.tick_in_game()
        self.tick_paused()


def parse_args():
    parser = argparse.ArgumentParser(description="UDP game server")
    parser.add_argument("--host", default="0.0.0.0", help="Server bind address")
    parser.add_argument("--port", type=int, default=5555, help="Server bind port")
    parser.add_argument("--room", default="CS323Room", help="Room name advertised in LAN beacons")
    parser.add_argument("--discovery-port", type=int, default=DISCOVERY_PORT, help="UDP port used for room beacons")
    parser.add_argument("--beacon-interval", type=float, default=BEACON_INTERVAL, help="Seconds between beacon broadcasts")
    parser.add_argument("--countdown-seconds", type=float, default=COUNTDOWN_SECONDS, help="Countdown duration before game start")
    parser.add_argument(
        "--reconnect-grace-seconds",
        type=float,
        default=RECONNECT_GRACE_SECONDS,
        help="Seconds an in-game player slot is reserved for reconnect",
    )
    parser.add_argument(
        "--player-timeout-seconds",
        type=float,
        default=PLAYER_TIMEOUT_SECONDS,
        help="Seconds without in-game packets before pausing for reconnect",
    )
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

    server = LobbyServer(
        sock=sock,
        room_state=room_state,
        countdown_seconds=args.countdown_seconds,
        reconnect_grace_seconds=args.reconnect_grace_seconds,
        player_timeout_seconds=args.player_timeout_seconds,
    )
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
