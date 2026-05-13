"""Single source of truth for assembling chunked remote-player avatars.

Replaces the per-state ``AvatarAssembly`` + ``_handle_avatar_*`` machinery that
previously lived in ``in_game``, ``room_lobby_ui``, and (transiently) ``results``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import zlib
from typing import Iterable, Optional

import pygame

from network import network_handler as nw
from network import protocol


@dataclass
class _Assembly:
    total_chunks: int
    payload_size: int = 0
    chunks: dict[int, bytes] = field(default_factory=dict)


class AvatarReceiver:
    """Reassemble avatar header+chunk packets into a ``pygame.Surface`` per player.

    The completed surface is written into the ``surfaces`` dict passed at
    construction, so callers that already hold a reference (e.g. UI draw code)
    pick up the new value automatically.
    """

    def __init__(self, surfaces: dict[int, pygame.Surface]):
        self._surfaces = surfaces
        self._models: dict[int, tuple[str, str]] = {}
        self._assemblies: dict[tuple[int, int], _Assembly] = {}

    def get_model(self, player_id: int) -> Optional[tuple[str, str]]:
        return self._models.get(player_id)

    def handle_event(self, event, local_player_id: int) -> bool:
        if isinstance(event, nw.AvatarHeaderEvent):
            self._on_header(event, local_player_id)
            return True
        if isinstance(event, nw.AvatarChunkEvent):
            self._on_chunk(event, local_player_id)
            return True
        return False

    def _on_header(self, event: nw.AvatarHeaderEvent, local_player_id: int) -> None:
        if event.player_id == local_player_id:
            return
        self._models[event.player_id] = (event.model_type, event.model_color)
        key = (event.player_id, event.avatar_id)
        assembly = self._assemblies.setdefault(key, _Assembly(total_chunks=event.total_chunks))
        assembly.total_chunks = event.total_chunks
        assembly.payload_size = event.payload_size
        self._try_complete(key)

    def _on_chunk(self, event: nw.AvatarChunkEvent, local_player_id: int) -> None:
        if event.player_id == local_player_id:
            return
        key = (event.player_id, event.avatar_id)
        assembly = self._assemblies.setdefault(key, _Assembly(total_chunks=event.total_chunks))
        assembly.total_chunks = event.total_chunks
        assembly.chunks[event.chunk_index] = event.payload
        self._try_complete(key)

    def _try_complete(self, key: tuple[int, int]) -> None:
        player_id, _avatar_id = key
        assembly = self._assemblies.get(key)
        if assembly is None:
            return
        if assembly.payload_size < 0:
            return
        if len(assembly.chunks) < assembly.total_chunks:
            return
        try:
            raw = b"".join(assembly.chunks[i] for i in range(assembly.total_chunks))
        except KeyError:
            return
        raw = raw[: assembly.payload_size]
        if assembly.payload_size == 0 and assembly.total_chunks == 0:
            return
        if len(raw) != protocol.NETWORK_AVATAR_BYTES:
            try:
                raw = zlib.decompress(raw)
            except zlib.error:
                return
            if len(raw) != protocol.NETWORK_AVATAR_BYTES:
                return
        try:
            avatar = pygame.image.frombytes(
                raw,
                (protocol.NETWORK_AVATAR_SIZE, protocol.NETWORK_AVATAR_SIZE),
                "RGBA",
            ).convert_alpha()
        except (ValueError, pygame.error):
            return
        self._surfaces[player_id] = avatar
        for old in [k for k in self._assemblies if k[0] == player_id]:
            self._assemblies.pop(old, None)

    def clear(self) -> None:
        self._surfaces.clear()
        self._models.clear()
        self._assemblies.clear()

    def clear_player(self, player_id: int) -> None:
        self._surfaces.pop(player_id, None)
        self._models.pop(player_id, None)
        for key in [k for k in self._assemblies if k[0] == player_id]:
            self._assemblies.pop(key, None)

    def retain(self, active_player_ids: Iterable[int]) -> None:
        keep = set(active_player_ids)
        for player_id in list(self._surfaces.keys()) + list(self._models.keys()):
            if player_id not in keep:
                self.clear_player(player_id)
