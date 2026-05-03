import logging

import pygame

from network import network_handler as nw
from player_scripts import player as pl
from states.common import ScreenState
from ui import components as ui
from ui.theme import DEFAULT_THEME
from world.level_1 import create_level_1
from player_scripts import camera

LOGGER = logging.getLogger(__name__)


class InGameState(ScreenState):
    def __init__(self, machine, context, **kwargs):
        super().__init__(machine, context, **kwargs)
        self.hero: pl.Player | None = None
        self.platforms = []
        self._last_pos = None
        self._name_by_id: dict[int, str] = {}
        self._remote_positions: dict[int, tuple[float, float]] = {}
        self._elimination_feed: list[str] = []
        self._dead_sent = False



    def enter(self):
        self.camera = camera.Camera(640, 640)  # NEEDS UPDATE FOR SCREEN SIZES
        self.platforms = create_level_1()
        self._dead_sent = False
        self._elimination_feed = []
        self._remote_positions = {}
        self._name_by_id = {pid: name for pid, _r, name in self.context.roster}
        sp = self.context.start_pos
        if isinstance(sp, (list, tuple)) and len(sp) >= 2:
            start = (float(sp[0]), float(sp[1]))
        else:
            start = (100.0, 100.0)
        sprite = str(self.context.project_root / "assets" / "characters" / "placeholder_AI_Knight.png")
        try:
            self.hero = pl.Player(start, sprite)
        except (FileNotFoundError, pygame.error) as err:
            LOGGER.warning("Player sprite missing: %s", err)
            self.hero = None
        self._last_pos = None

    def _drain_network(self) -> bool:
        for event in self.context.drain_network_events():
            if self.handle_common_network_event(event):
                continue
            if isinstance(event, nw.PositionEvent):
                self._remote_positions[event.player_id] = (event.x, event.y)
            elif isinstance(event, nw.EliminationEvent):
                name = self._name_by_id.get(event.player_id, f"id {event.player_id}")
                self._elimination_feed.append(f"{name} eliminated — place {event.placement}")
            elif isinstance(event, nw.GameEndEvent):
                self.context.results_standings = list(event.standings)
                self.context.return_state_after_results = "host_lobby" if self.context.is_host else "joined_lobby"
                self.switch("results")
                return True
            elif isinstance(event, nw.RosterEvent):
                self.context.roster = list(event.entries)
                for pid, _ready, name in event.entries:
                    self._name_by_id[pid] = name
        return False

    def update(self, dt: float):
        net = self.context.network
        if net is None or self.hero is None:
            return

        if self._drain_network():
            return

        w, h = self.context.screen.get_size()
        self.hero.update(dt, w, h, self.platforms)

        if not self._dead_sent and self.hero.pos.y > h + 80:
            self._dead_sent = True
            net.send_dead()

        # Send position update every frame for responsive jump/movement feedback
        net.update_pos(self.hero.pos.x, self.hero.pos.y)

        if self.hero and self.camera:
            self.camera.update(self.hero)

    def draw(self, surface):
        super().draw(surface)
        theme = DEFAULT_THEME

        camera = self.camera

        if self.hero is None:
            surface.blit(
                self.context.font.render("Missing player asset", True, theme.text_warn),
                (32, 32),
            )
            return

        w, h = surface.get_size()

        for platform in self.platforms:
            original_rect = platform.rect.copy()

            platform.rect.x += camera.camera_rect.x
            platform.rect.y += camera.camera_rect.y

            platform.draw(surface)

            platform.rect = original_rect

        ow, oh = 64, 128
        my_id = self.context.network.id if self.context.network else -1

        for p_id, p_pos in self._remote_positions.items():
            if int(p_id) == my_id:
                continue

            world_x = p_pos[0] - ow / 2
            world_y = p_pos[1] - oh / 2

            draw_x = int(world_x + camera.camera_rect.x)
            draw_y = int(world_y + camera.camera_rect.y)

            pygame.draw.rect(surface, (60, 100, 220), (draw_x, draw_y, ow, oh), border_radius=4)
            pygame.draw.rect(surface, theme.border, (draw_x, draw_y, ow, oh), width=1, border_radius=4)

        if hasattr(self.hero, "rect"):
            screen_rect = self.hero.rect.move(camera.camera_rect.x, camera.camera_rect.y)
            surface.blit(self.hero.image, screen_rect)
        else:
            self.hero.draw(surface, camera)

        ui.draw_elimination_feed(
            surface,
            self.context.tiny_font,
            self._elimination_feed,
            theme
        )