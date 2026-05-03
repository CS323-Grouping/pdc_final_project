import pygame
import random
from enum import Enum
from dataclasses import dataclass
from typing import Optional


class PowerUpType(Enum):
    DOUBLE_JUMP = "double_jump"
    SPEED_BOOST = "speed_boost"
    LOW_GRAVITY = "low_gravity"
    SHOCKWAVE = "shockwave"
    PLATFORM_BREAKER = "platform_breaker"
    FREEZE_TRAP = "freeze_trap"
    SHIELD_BUBBLE = "shield_bubble"
    REVIVE_TOKEN = "revive_token"
    FALL_SLOW = "fall_slow"
    PLATFORM_SPAWNER = "platform_spawner"
    SWAP_POSITION = "swap_position"
    BUFF_STEAL = "buff_steal"


# Color mapping for each power-up type
POWERUP_COLORS = {
    PowerUpType.DOUBLE_JUMP: (0, 255, 255),        # Cyan
    PowerUpType.SPEED_BOOST: (255, 0, 255),        # Magenta
    PowerUpType.LOW_GRAVITY: (255, 255, 0),        # Yellow
    PowerUpType.SHOCKWAVE: (255, 165, 0),          # Orange
    PowerUpType.PLATFORM_BREAKER: (255, 0, 0),    # Red
    PowerUpType.FREEZE_TRAP: (100, 200, 255),     # Light Blue
    PowerUpType.SHIELD_BUBBLE: (0, 255, 0),        # Green
    PowerUpType.REVIVE_TOKEN: (200, 100, 255),    # Purple
    PowerUpType.FALL_SLOW: (200, 200, 200),       # Gray
    PowerUpType.PLATFORM_SPAWNER: (255, 200, 0),  # Gold
    PowerUpType.SWAP_POSITION: (255, 100, 200),   # Pink
    PowerUpType.BUFF_STEAL: (100, 100, 255),      # Blue
}

POWERUP_NAMES = {
    PowerUpType.DOUBLE_JUMP: "Double Jump",
    PowerUpType.SPEED_BOOST: "Speed Boost",
    PowerUpType.LOW_GRAVITY: "Low Gravity",
    PowerUpType.SHOCKWAVE: "Shockwave",
    PowerUpType.PLATFORM_BREAKER: "Platform Breaker",
    PowerUpType.FREEZE_TRAP: "Freeze Trap",
    PowerUpType.SHIELD_BUBBLE: "Shield",
    PowerUpType.REVIVE_TOKEN: "Revive Token",
    PowerUpType.FALL_SLOW: "Fall Slow",
    PowerUpType.PLATFORM_SPAWNER: "Platform Spawner",
    PowerUpType.SWAP_POSITION: "Swap Position",
    PowerUpType.BUFF_STEAL: "Buff Steal",
}


@dataclass
class PowerUp:
    """Represents a power-up in the game world"""
    type: PowerUpType
    pos: pygame.Vector2
    radius: int = 15
    active: bool = True
    
    def draw(self, surface, camera=None):
        """Draw the power-up"""
        if not self.active:
            return
        
        color = POWERUP_COLORS[self.type]
        x, y = int(self.pos.x), int(self.pos.y)
        
        if camera:
            screen_pos = camera.apply_point(x, y)
            x, y = int(screen_pos[0]), int(screen_pos[1])
        
        # Draw outer circle
        pygame.draw.circle(surface, color, (x, y), self.radius, 3)
        # Draw inner circle
        pygame.draw.circle(surface, color, (x, y), self.radius - 5)
    
    def get_rect(self):
        """Get collision rect for this power-up"""
        return pygame.Rect(
            self.pos.x - self.radius,
            self.pos.y - self.radius,
            self.radius * 2,
            self.radius * 2
        )


@dataclass
class ActivePowerUp:
    """A power-up effect active on a player"""
    type: PowerUpType
    duration: float  # seconds, 0 = permanent until used
    acquired_time: float = 0.0
    
    def is_expired(self, current_time: float) -> bool:
        if self.duration == 0:
            return False
        return (current_time - self.acquired_time) > self.duration
