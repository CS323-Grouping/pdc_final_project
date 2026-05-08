import pygame

from player_scripts.avatar_sprite import AVATAR_RECT, compose_player_frames, prepare_avatar
from world.constants import PLAYER_FRAME_SIZE


def test_prepare_avatar_square_crops_and_resizes():
    source = pygame.Surface((20, 10), pygame.SRCALPHA)
    source.fill((10, 20, 30, 255))

    avatar = prepare_avatar(source)

    assert avatar.get_size() == AVATAR_RECT.size


def test_compose_player_frames_returns_cached_frame_surfaces():
    body_frame = pygame.Surface(PLAYER_FRAME_SIZE, pygame.SRCALPHA)
    body_frame.fill((0, 0, 0, 0))
    avatar = pygame.Surface(AVATAR_RECT.size, pygame.SRCALPHA)
    avatar.fill((255, 0, 0, 255))

    composed = compose_player_frames({"idle_front": [body_frame]}, avatar)

    assert composed["idle_front"][0].get_size() == PLAYER_FRAME_SIZE
    assert composed["idle_front"][0] is not body_frame


def test_compose_player_frames_replaces_default_head_pixels_with_avatar():
    body_frame = pygame.Surface(PLAYER_FRAME_SIZE, pygame.SRCALPHA)
    body_frame.fill((0, 0, 0, 0))
    body_frame.fill((20, 200, 40, 255), AVATAR_RECT)
    body_frame.set_at((0, PLAYER_FRAME_SIZE[1] - 1), (10, 20, 30, 255))
    avatar = pygame.Surface(AVATAR_RECT.size, pygame.SRCALPHA)
    avatar.fill((240, 30, 20, 255))

    composed = compose_player_frames({"idle_front": [body_frame]}, avatar)["idle_front"][0]

    assert composed.get_at(AVATAR_RECT.center) == (240, 30, 20, 255)
    assert composed.get_at((0, PLAYER_FRAME_SIZE[1] - 1)) == (10, 20, 30, 255)
