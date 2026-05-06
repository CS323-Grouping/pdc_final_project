import argparse
import logging
import sys

import pygame

from app.display import DisplayManager
from app.logging_setup import configure_logging, create_instance_log_dir
from app.state_machine import AppContext, StateMachine
from network import network_handler as nw
from network import protocol

LOGGER = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Tower-jumping multiplayer (LAN lobby)")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging verbosity",
    )
    parser.add_argument(
        "--host",
        action="store_true",
        help="Skip main menu and go straight to host lobby",
    )
    parser.add_argument(
        "--name",
        default="",
        help=f"Player name ({protocol.PLAYER_NAME_MIN_LEN}-{protocol.PLAYER_NAME_MAX_LEN} chars; letters, numbers, _ or -)",
    )
    parser.add_argument(
        "--room",
        default="GameRoom",
        help=(
            f"Room name when using --host ({protocol.ROOM_NAME_MIN_LEN}-{protocol.ROOM_NAME_MAX_LEN} chars; "
            "letters, numbers, spaces, _ or -)"
        ),
    )
    parser.add_argument(
        "--server",
        default="",
        metavar="HOST:PORT",
        help="Emergency direct join (bypass discovery), e.g. 192.168.1.10:5555",
    )
    return parser.parse_args()


def _parse_server_option(value: str) -> tuple[str, int] | None:
    value = (value or "").strip()
    if not value:
        return None
    if ":" not in value:
        LOGGER.error("--server must be HOST:PORT")
        return None
    host, port_s = value.rsplit(":", 1)
    host = host.strip()
    try:
        port = int(port_s.strip())
    except ValueError:
        LOGGER.error("Invalid port in --server")
        return None
    if not host or port <= 0 or port > 65535:
        LOGGER.error("Invalid --server value")
        return None
    return host, port


def main():
    args = parse_args()

    pygame.init()
    pygame.key.set_repeat(350, 35)
    display_manager = DisplayManager.create_default()
    clock = pygame.time.Clock()
    ctx = AppContext(
        screen=display_manager.screen,
        clock=clock,
        log_level=args.log_level,
        display_manager=display_manager,
    )

    if args.name:
        ctx.player_name = args.name.strip() or ctx.player_name

    ctx.log_dir = create_instance_log_dir(ctx.project_root, ctx.player_name)
    configure_logging(args.log_level, ctx.log_dir / "client.log")
    LOGGER.info("Client log initialized for player=%s dir=%s", ctx.player_name, ctx.log_dir)

    if not protocol.is_valid_player_name(ctx.player_name):
        LOGGER.error(
            "Player name must be %s-%s chars and may contain letters, numbers, _ or -.",
            protocol.PLAYER_NAME_MIN_LEN,
            protocol.PLAYER_NAME_MAX_LEN,
        )
        pygame.quit()
        sys.exit(1)

    initial_state = "menu"
    machine = StateMachine(ctx)

    if args.host:
        if not protocol.is_valid_room_name(args.room):
            LOGGER.error(
                "Room name must be %s-%s chars and may contain letters, numbers, spaces, _ or -.",
                protocol.ROOM_NAME_MIN_LEN,
                protocol.ROOM_NAME_MAX_LEN,
            )
            pygame.quit()
            sys.exit(1)
        ctx.room_name = args.room
        initial_state = "host_lobby"
    elif args.server:
        parsed = _parse_server_option(args.server)
        if parsed is None:
            pygame.quit()
            sys.exit(1)
        host, port = parsed
        net = nw.Network()
        result = net.connect_to_room(host, port, ctx.player_name)
        if not result.ok:
            LOGGER.error("Direct join failed (reason=%s extra=%s)", result.reason_code, result.extra)
            net.close()
            pygame.quit()
            sys.exit(1)
        ctx.attach_network(net, is_host=False, room_name=result.room_name, start_pos=result.start_pos)
        initial_state = "joined_lobby"

    try:
        machine.run(initial_state=initial_state)
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
