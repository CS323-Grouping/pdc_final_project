import zlib
from pathlib import Path
from types import SimpleNamespace

import pygame

from network import network_handler as nw
from network import protocol
from network.avatar_receiver import AvatarReceiver
from states.room_lobby_ui import RoomLobbyUi


def test_avatar_receiver_accepts_compressed_avatar_payload():
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((1, 1))
    surfaces = {}
    receiver = AvatarReceiver(surfaces)
    source = pygame.Surface((protocol.NETWORK_AVATAR_SIZE, protocol.NETWORK_AVATAR_SIZE), pygame.SRCALPHA)
    source.fill((12, 34, 56, 255))
    raw = pygame.image.tobytes(source, "RGBA")
    payload = zlib.compress(raw, level=6)

    receiver.handle_event(
        nw.AvatarHeaderEvent(
            player_id=4,
            avatar_id=99,
            total_chunks=1,
            payload_size=len(payload),
            model_type=protocol.DEFAULT_MODEL_TYPE,
            model_color="Green",
        ),
        local_player_id=1,
    )
    receiver.handle_event(
        nw.AvatarChunkEvent(
            player_id=4,
            avatar_id=99,
            chunk_index=0,
            total_chunks=1,
            payload=payload,
        ),
        local_player_id=1,
    )

    assert 4 in surfaces
    assert surfaces[4].get_at((0, 0)) == (12, 34, 56, 255)


def test_room_lobby_enter_preserves_remote_avatar_cache_between_matches():
    surfaces = {2: pygame.Surface((protocol.NETWORK_AVATAR_SIZE, protocol.NETWORK_AVATAR_SIZE), pygame.SRCALPHA)}
    receiver = AvatarReceiver(surfaces)
    receiver.handle_event(
        nw.AvatarHeaderEvent(
            player_id=2,
            avatar_id=11,
            total_chunks=0,
            payload_size=0,
            model_type=protocol.DEFAULT_MODEL_TYPE,
            model_color="Black",
        ),
        local_player_id=1,
    )
    context = SimpleNamespace(
        project_root=Path.cwd(),
        avatar_receiver=receiver,
        model_type=protocol.DEFAULT_MODEL_TYPE,
        model_color=protocol.DEFAULT_MODEL_COLOR,
    )
    lobby = RoomLobbyUi(context)
    lobby._load_assets = lambda: {}
    lobby._load_player_preview_frame = lambda: None
    lobby._make_avatar_payload = lambda: b""

    lobby.enter()

    assert 2 in surfaces
    assert receiver.get_model(2) == (protocol.DEFAULT_MODEL_TYPE, "Black")
