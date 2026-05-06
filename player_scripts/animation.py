from dataclasses import dataclass
from pathlib import Path

import pygame

from world.constants import PLAYER_FRAME_HEIGHT, PLAYER_FRAME_SIZE, PLAYER_FRAME_WIDTH


ANIMATIONS = {
    "idle_front": {"row": 0, "frames": 8, "fps": 8, "loop": True},
    "walk_left": {"row": 1, "frames": 8, "fps": 10, "loop": True},
    "walk_right": {"row": 2, "frames": 8, "fps": 10, "loop": True},
    "jump_front": {"row": 3, "frames": 8, "fps": 12, "loop": False},
    "jump_left": {"row": 4, "frames": 8, "fps": 12, "loop": False},
    "jump_right": {"row": 5, "frames": 8, "fps": 12, "loop": False},
}


def load_spritesheet_frames(sheet_path: str | Path) -> dict[str, list[pygame.Surface]]:
    sheet = pygame.image.load(str(sheet_path)).convert_alpha()
    frames_by_state: dict[str, list[pygame.Surface]] = {}
    for name, metadata in ANIMATIONS.items():
        row = metadata["row"]
        frame_count = metadata["frames"]
        frames = []
        for column in range(frame_count):
            frame = pygame.Surface(PLAYER_FRAME_SIZE, pygame.SRCALPHA)
            source_rect = pygame.Rect(
                column * PLAYER_FRAME_WIDTH,
                row * PLAYER_FRAME_HEIGHT,
                PLAYER_FRAME_WIDTH,
                PLAYER_FRAME_HEIGHT,
            )
            frame.blit(sheet, (0, 0), source_rect)
            frames.append(frame)
        frames_by_state[name] = frames
    return frames_by_state


@dataclass
class AnimationState:
    frames_by_state: dict[str, list[pygame.Surface]]
    state: str = "idle_front"
    elapsed: float = 0.0
    frame_index: int = 0

    def set_state(self, state: str) -> None:
        if state == self.state:
            return
        if state not in self.frames_by_state:
            raise KeyError(f"Unknown animation state: {state}")
        self.state = state
        self.elapsed = 0.0
        self.frame_index = 0

    def update(self, dt: float) -> None:
        metadata = ANIMATIONS[self.state]
        frames = self.frames_by_state[self.state]
        if len(frames) <= 1:
            self.frame_index = 0
            return
        self.elapsed += dt
        frame_duration = 1.0 / metadata["fps"]
        while self.elapsed >= frame_duration:
            self.elapsed -= frame_duration
            if metadata.get("loop", True):
                self.frame_index = (self.frame_index + 1) % len(frames)
            else:
                self.frame_index = min(self.frame_index + 1, len(frames) - 1)
                if self.frame_index == len(frames) - 1:
                    self.elapsed = 0.0
                    break

    @property
    def image(self) -> pygame.Surface:
        return self.frames_by_state[self.state][self.frame_index]
