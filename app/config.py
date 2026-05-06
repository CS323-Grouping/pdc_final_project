from enum import Enum


class LobbyPlayerStatus(Enum):
    HOST = "HOST"
    READY = "READY"
    WAITING = "WAITING"


def lobby_player_status(is_host: bool, ready: bool) -> LobbyPlayerStatus:
    if is_host:
        return LobbyPlayerStatus.HOST
    return LobbyPlayerStatus.READY if ready else LobbyPlayerStatus.WAITING


def lobby_player_status_label(is_host: bool, ready: bool) -> str:
    return lobby_player_status(is_host, ready).value
