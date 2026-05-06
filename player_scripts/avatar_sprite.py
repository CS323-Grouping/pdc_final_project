import pygame

from world.constants import PLAYER_FRAME_SIZE

HEAD_OUTER_RECT = pygame.Rect(4, 0, 16, 16)
AVATAR_RECT = pygame.Rect(5, 1, 14, 14)
VALID_AVATAR_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def crop_square(source: pygame.Surface) -> pygame.Surface:
    size = min(source.get_width(), source.get_height())
    crop_rect = pygame.Rect(0, 0, size, size)
    crop_rect.center = source.get_rect().center
    cropped = pygame.Surface((size, size), pygame.SRCALPHA)
    cropped.blit(source, (0, 0), crop_rect)
    return cropped


def prepare_avatar(source: pygame.Surface) -> pygame.Surface:
    cropped = crop_square(source)
    return pygame.transform.smoothscale(cropped, AVATAR_RECT.size)


def make_default_avatar() -> pygame.Surface:
    avatar = pygame.Surface(AVATAR_RECT.size, pygame.SRCALPHA)
    avatar.fill((74, 128, 212, 255))
    pygame.draw.rect(avatar, (236, 240, 255, 255), pygame.Rect(3, 2, 8, 5))
    pygame.draw.rect(avatar, (34, 52, 96, 255), pygame.Rect(2, 8, 10, 4))
    return avatar


def compose_player_frames(
    body_frames_by_state: dict[str, list[pygame.Surface]],
    avatar: pygame.Surface,
) -> dict[str, list[pygame.Surface]]:
    prepared_avatar = prepare_avatar(avatar)
    composed: dict[str, list[pygame.Surface]] = {}
    for state, frames in body_frames_by_state.items():
        composed[state] = []
        for body_frame in frames:
            frame = pygame.Surface(PLAYER_FRAME_SIZE, pygame.SRCALPHA)
            frame.blit(prepared_avatar, AVATAR_RECT.topleft)
            frame.blit(body_frame, (0, 0))
            composed[state].append(frame)
    return composed
