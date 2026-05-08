from types import SimpleNamespace

import pygame

from player_scripts.avatar_sprite import AVATAR_RECT
from states.menu import MENU_ASSET_RECTS, MainMenuState
from states.room_lobby_ui import RoomLobbyUi
from world.constants import PLAYER_FRAME_HEIGHT, PLAYER_FRAME_SIZE, PLAYER_FRAME_WIDTH


def _body_frame() -> pygame.Surface:
    body = pygame.Surface(PLAYER_FRAME_SIZE, pygame.SRCALPHA)
    body.fill((0, 0, 0, 0))
    body.fill((20, 200, 40, 255), AVATAR_RECT)
    body.set_at((0, PLAYER_FRAME_HEIGHT - 1), (10, 20, 30, 255))
    return body


def _avatar_source() -> pygame.Surface:
    avatar = pygame.Surface((20, 10), pygame.SRCALPHA)
    avatar.fill((240, 30, 20, 255))
    return avatar


def test_main_menu_avatar_preview_draws_avatar_over_head_pixels():
    surface = pygame.Surface((320, 180), pygame.SRCALPHA)
    state = SimpleNamespace(
        _idle_body_frame=_body_frame(),
        _scale_rect=lambda rect: rect,
        _current_avatar_source=_avatar_source,
    )

    MainMenuState._draw_window_avatar_preview(state, surface)

    model_rect = MENU_ASSET_RECTS["avatar_model"]
    assert surface.get_at((model_rect.x + AVATAR_RECT.centerx, model_rect.y + AVATAR_RECT.centery)) == (240, 30, 20, 255)
    assert surface.get_at((model_rect.x, model_rect.y + PLAYER_FRAME_HEIGHT - 1)) == (10, 20, 30, 255)


def test_room_lobby_player_model_draws_avatar_over_head_pixels():
    surface = pygame.Surface((320, 180), pygame.SRCALPHA)
    ui = SimpleNamespace(_scale_rect=lambda rect: rect)
    logical_rect = pygame.Rect(12, 18, PLAYER_FRAME_WIDTH, PLAYER_FRAME_HEIGHT)

    RoomLobbyUi._draw_player_model(ui, surface, logical_rect, _avatar_source(), _body_frame())

    assert surface.get_at((logical_rect.x + AVATAR_RECT.centerx, logical_rect.y + AVATAR_RECT.centery)) == (240, 30, 20, 255)
    assert surface.get_at((logical_rect.x, logical_rect.y + PLAYER_FRAME_HEIGHT - 1)) == (10, 20, 30, 255)
