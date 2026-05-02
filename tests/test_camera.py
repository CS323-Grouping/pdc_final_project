import pygame

from player_scripts.camera import Camera


class Target:
    def __init__(self, rect):
        self.rect = rect


def test_camera_moves_up_when_target_crosses_upper_threshold():
    camera = Camera(320, 180, upper_follow_threshold=64)
    target = Target(pygame.Rect(100, 30, 16, 28))

    camera.update(target)

    assert camera.y < 0


def test_camera_does_not_move_down_after_upward_progress():
    camera = Camera(320, 180, upper_follow_threshold=64)
    camera.y = -80
    target = Target(pygame.Rect(100, 120, 16, 28))

    camera.update(target)

    assert camera.y == -80


def test_camera_fall_check_uses_camera_bottom_and_margin():
    camera = Camera(320, 180, fall_margin=32)
    camera.y = -100

    safe = Target(pygame.Rect(100, 100, 16, 28))
    fallen = Target(pygame.Rect(100, 113, 16, 28))

    assert not camera.has_fallen_below(safe)
    assert camera.has_fallen_below(fallen)
