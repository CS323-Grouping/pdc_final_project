import argparse
import logging
from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from network.discovery import LobbyBrowser

LOGGER = logging.getLogger(__name__)

STATE_LABELS = {
    0: "LOBBY",
    1: "COUNTDOWN",
    2: "IN_GAME",
}


def parse_args():
    parser = argparse.ArgumentParser(description="List LAN rooms discovered via beacons")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between room list refreshes")
    parser.add_argument("--ttl", type=float, default=3.0, help="Room expiration TTL in seconds")
    parser.add_argument("--port", type=int, default=5556, help="Discovery UDP port")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging verbosity",
    )
    return parser.parse_args()


def configure_logging(log_level: str):
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="[%(levelname)s] %(name)s: %(message)s",
    )


def print_rooms(browser: LobbyBrowser):
    rooms = browser.snapshot()
    print("-" * 80)
    if not rooms:
        print("No rooms found.")
        return

    for room in rooms:
        state_name = STATE_LABELS.get(room.state, f"UNKNOWN({room.state})")
        print(
            f"{room.room_name:<24} "
            f"{room.current_players}/{room.max_players:<5} "
            f"{state_name:<10} "
            f"{room.addr}:{room.game_port}",
        )


def main():
    args = parse_args()
    configure_logging(args.log_level)
    browser = LobbyBrowser(discovery_port=args.port, ttl=args.ttl)
    browser.start()

    LOGGER.info("Listening for room beacons on UDP port %s", args.port)

    try:
        while True:
            print_rooms(browser)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        LOGGER.info("Stopping room browser...")
    finally:
        browser.stop()


if __name__ == "__main__":
    main()
