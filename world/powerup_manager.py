import random
import pygame
from typing import List, Optional
from world.powerup import PowerUp, PowerUpType, POWERUP_COLORS


class PowerUpManager:
    """Manages power-ups in the game world"""
    
    def __init__(self, world_height: int = 600, world_width: int = 1600):
        self.powerups: List[PowerUp] = []
        self.world_height = world_height
        self.world_width = world_width
        self.spawn_rate = 0.3  # Chance to spawn power-up at each spawn point
        self.last_spawn_y = 0
        
    def spawn_random_powerup(self, y: float) -> Optional[PowerUp]:
        """Spawn a random power-up at the given Y position"""
        if random.random() > self.spawn_rate:
            return None
        
        powerup_type = random.choice(list(PowerUpType))
        x = random.randint(50, self.world_width - 50)
        
        powerup = PowerUp(
            type=powerup_type,
            pos=pygame.Vector2(x, y),
            radius=15,
            active=True
        )
        self.powerups.append(powerup)
        return powerup
    
    def generate_powerups_above(self, camera_min_y: float, spawn_interval: float = 200):
        """Generate power-ups as camera moves up"""
        if camera_min_y < self.last_spawn_y:
            target_y = camera_min_y - 200
            while self.last_spawn_y > target_y:
                self.spawn_random_powerup(self.last_spawn_y)
                self.last_spawn_y -= spawn_interval
    
    def check_collisions(self, player_rect):
        """Check if player collides with any power-ups"""
        collected = []
        for powerup in self.powerups:
            if powerup.active and player_rect.colliderect(powerup.get_rect()):
                powerup.active = False
                collected.append(powerup.type)
        return collected
    
    def update_visible_powerups(self, camera_rect, buffer: int = 500):
        """Remove power-ups that are far off-screen"""
        min_y = camera_rect.y - buffer
        max_y = camera_rect.y + camera_rect.height + buffer
        
        self.powerups = [
            p for p in self.powerups
            if min_y < p.pos.y < max_y + 100 or p.active
        ]
    
    def draw_powerups(self, surface, camera=None):
        """Draw all active power-ups"""
        for powerup in self.powerups:
            if powerup.active:
                powerup.draw(surface, camera)
    
    def get_all_powerups(self):
        """Get all power-ups (for networking)"""
        return self.powerups
