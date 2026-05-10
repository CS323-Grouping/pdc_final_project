import pygame

from states.common import ScreenState
from ui.results_table import draw_results_table
from ui.theme import DEFAULT_THEME
from world.assets import load_world_assets


RESULTS_AUTO_HIDE_SECONDS = 5.0
RESULTS_MIN_VISIBLE_SECONDS = 1.0


class ResultsState(ScreenState):
    def __init__(self, machine, context, **kwargs):
        super().__init__(machine, context, **kwargs)
        self._auto_hide = RESULTS_AUTO_HIDE_SECONDS
        self._elapsed = 0.0

    def enter(self):
        self._auto_hide = RESULTS_AUTO_HIDE_SECONDS
        self._elapsed = 0.0
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
        # Avatars are already populated by InGameState. We still drain so that
        # late-arriving avatar packets (e.g. server replay after a join) feed
        # the receiver, and so common events like ConnectionLost / Kicked are
        # handled while results is on screen.
        drain = getattr(self.context, "drain_network_events", None)
        network = getattr(self.context, "network", None)
        receiver = getattr(self.context, "avatar_receiver", None)
        if drain is None or network is None:
            return
        my_id = network.id
        for event in drain():
            if self.handle_common_network_event(event):
                continue
            if receiver is not None:
                receiver.handle_event(event, my_id)

    def draw(self, surface):
        super().draw(surface)
        w, h = surface.get_size()
        theme = DEFAULT_THEME

        my_id = self.context.network.id if self.context.network is not None else None
        avatar = self.context.avatar_window_surface
        bottom_reserve = self.context.reserved_bottom_message_strip_px()

        draw_results_table(
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
            remote_avatars=self.context.remote_avatar_surfaces,
        )

        hint_text = f"Press any key to continue  ·  {max(0, int(self._auto_hide + 0.99))}s"
        hint = self.context.small_font.render(hint_text, True, theme.text_muted)
        hint_margin = max(18, min(44, h // 16))
        surface.blit(hint, hint.get_rect(midbottom=(w // 2, h - bottom_reserve - hint_margin)))
