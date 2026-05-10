from dataclasses import dataclass

import pygame

from network import network_handler as nw
from network import protocol
from states.common import ScreenState
from ui import components as ui
from ui.theme import DEFAULT_THEME
from world.assets import load_world_assets


RESULTS_AUTO_HIDE_SECONDS = 5.0
RESULTS_MIN_VISIBLE_SECONDS = 1.0


@dataclass
class AvatarAssembly:
    total_chunks: int
    payload_size: int = 0
    chunks: dict = None

    def __post_init__(self):
        if self.chunks is None:
            self.chunks = {}


class ResultsState(ScreenState):
    def __init__(self, machine, context, **kwargs):
        super().__init__(machine, context, **kwargs)
        self._auto_hide = RESULTS_AUTO_HIDE_SECONDS
        self._elapsed = 0.0
        self._avatar_assemblies: dict[tuple[int, int], AvatarAssembly] = {}

    def enter(self):
        self._auto_hide = RESULTS_AUTO_HIDE_SECONDS
        self._elapsed = 0.0
        self._avatar_assemblies = {}
        self.context.countdown_remaining = None
        self.context.dock_global_messages_bottom = True
        root = getattr(self.context, "project_root", None)
        if root is not None:
            try:
                self._world_assets = load_world_assets(root)
            except pygame.error:
                self._world_assets = None
        else:
            self._world_assets = None

    def exit(self):
        self.context.dock_global_messages_bottom = False

    def _placement_label(self, placement: int) -> str:
        if placement == 1:
            return "WINNER"
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(placement % 10 if placement % 100 not in (11, 12, 13) else 0, "th")
        return f"{placement}{suffix} place"

    def handle_event(self, event):
        super().handle_event(event)
        if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
            if self._elapsed < RESULTS_MIN_VISIBLE_SECONDS:
                return
            self._finish()

    def _finish(self):
        nxt = self.context.return_state_after_results or "menu"
        self.switch(nxt)

    def update(self, dt: float):
        self._elapsed += dt
        self._auto_hide -= dt
        self._drain_network()
        if self._auto_hide <= 0:
            self._finish()

    def _drain_network(self):
        drain = getattr(self.context, "drain_network_events", None)
        if drain is None:
            return
        for event in drain():
            self.handle_common_network_event(event)
            if isinstance(event, nw.AvatarHeaderEvent):
                self._handle_avatar_header(event)
            elif isinstance(event, nw.AvatarChunkEvent):
                self._handle_avatar_chunk(event)

    def _local_player_id(self):
        net = self.context.network
        return net.id if net is not None else None

    def _handle_avatar_header(self, event: nw.AvatarHeaderEvent):
        if event.player_id == self._local_player_id():
            return
        key = (event.player_id, event.avatar_id)
        assembly = self._avatar_assemblies.get(key)
        if assembly is None:
            assembly = AvatarAssembly(total_chunks=event.total_chunks)
            self._avatar_assemblies[key] = assembly
        assembly.total_chunks = event.total_chunks
        assembly.payload_size = event.payload_size
        self._try_complete_avatar(event.player_id, event.avatar_id)

    def _handle_avatar_chunk(self, event: nw.AvatarChunkEvent):
        if event.player_id == self._local_player_id():
            return
        key = (event.player_id, event.avatar_id)
        assembly = self._avatar_assemblies.get(key)
        if assembly is None:
            assembly = AvatarAssembly(total_chunks=event.total_chunks)
            self._avatar_assemblies[key] = assembly
        assembly.total_chunks = event.total_chunks
        assembly.chunks[event.chunk_index] = event.payload

        self._try_complete_avatar(event.player_id, event.avatar_id)

    def _try_complete_avatar(self, player_id: int, avatar_id: int):
        key = (player_id, avatar_id)
        assembly = self._avatar_assemblies.get(key)
        if assembly is None:
            return
        if assembly.payload_size != protocol.NETWORK_AVATAR_BYTES:
            return
        if len(assembly.chunks) < assembly.total_chunks:
            return
        try:
            raw = b"".join(assembly.chunks[index] for index in range(assembly.total_chunks))
        except KeyError:
            return
        raw = raw[: assembly.payload_size]
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
        self.context.remote_avatar_surfaces[player_id] = avatar
        for old_key in list(self._avatar_assemblies.keys()):
            if old_key[0] == player_id:
                self._avatar_assemblies.pop(old_key, None)

    def draw(self, surface):
        super().draw(surface)
        w, h = surface.get_size()
        theme = DEFAULT_THEME

        my_id = self.context.network.id if self.context.network is not None else None
        avatar = self.context.avatar_window_surface
        bottom_reserve = self.context.reserved_bottom_message_strip_px()
        remote_avatars = getattr(self.context, "remote_avatar_surfaces", None) or {}

        ui.draw_results_table(
            surface,
            (self.context.title_font, self.context.font, self.context.small_font),
            self.context.results_standings,
            self._elapsed,
            self._placement_label,
            theme,
            local_player_id=my_id,
            local_avatar=avatar,
            world_assets=self._world_assets,
            footer_reserve_extra=bottom_reserve,
            remote_avatars=remote_avatars,
        )

        hint_text = f"Press any key to continue  ·  {max(0, int(self._auto_hide + 0.99))}s"
        hint = self.context.small_font.render(hint_text, True, theme.text_muted)
        hint_margin = max(18, min(44, h // 16))
        surface.blit(hint, hint.get_rect(midbottom=(w // 2, h - bottom_reserve - hint_margin)))
