import pygame
import math


class PowerUp:
    def __init__(self, pos, effect_type="speed"):
        self.pos = pygame.Vector2(pos)
        self.effect_type = effect_type  # 'speed', 'jump', 'shield', 'double_jump', 'launch', 'reverse_control', 'slippery', 'slow_falling', 'heavy', 'weak_jump', 'orb'
        self.rect = pygame.Rect(int(self.pos.x - 8), int(self.pos.y - 8), 16, 16)
        self.collected = False
        self._pulse = 0.0

    def update(self, dt: float) -> None:
        self._pulse = (self._pulse + dt * 3.0) % (2 * math.pi)

    def draw(self, surface: pygame.Surface, camera=None) -> None:
        rect = self.rect
        if camera is not None:
            rect = rect.move(-int(round(camera.x)), -int(round(camera.y)))

        # Simple glowing circle for power up
        brightness = int(150 + 100 * math.sin(self._pulse))
        if self.effect_type == 'speed':
            color = (brightness, brightness // 2, brightness // 4)  # Orange for speed
        elif self.effect_type == 'jump':
            color = (brightness // 2, brightness, brightness // 4)  # Green for jump
        elif self.effect_type == 'shield':
            color = (brightness // 4, brightness // 2, brightness)  # Blue for shield
        elif self.effect_type == 'double_jump':
            color = (brightness, brightness // 4, brightness)  # Purple for double jump
        elif self.effect_type == 'launch':
            #Debuff
            color = (brightness, brightness // 2, brightness // 2)  # Yellow for launch
        elif self.effect_type == 'reverse_control':
            color = (brightness, brightness // 4, brightness // 4)  # Red for reverse control
        elif self.effect_type == 'slippery':
            color = (brightness // 2, brightness // 2, brightness)  # Cyan for slippery
        elif self.effect_type == 'slow_falling':
            color = (brightness // 4, brightness, brightness)  # Lime for slow falling
        elif self.effect_type == 'heavy':
            color = (brightness // 2, brightness // 4, brightness // 2)  # Brown for heavy
        elif self.effect_type == 'weak_jump':
            color = (brightness // 4, brightness // 2, brightness // 4)  # Teal for weak jump
        elif self.effect_type == 'orb':
            color = (brightness, brightness, brightness // 2)  # Gold-white orb
        else:
            color = (brightness, brightness // 2, brightness // 4)  # Default orange

        # Draw glow
        glow_rect = rect.inflate(4, 4)
        glow_color = (color[0] // 2, color[1] // 2, color[2] // 2)
        pygame.draw.ellipse(surface, glow_color, glow_rect)

        # Draw core
        pygame.draw.ellipse(surface, color, rect)

        # Draw symbol based on type
        center = rect.center
        if self.effect_type == 'speed':
            # Arrow right for speed
            pygame.draw.polygon(surface, (255, 255, 255), [
                (center[0] - 3, center[1] - 2), (center[0] - 3, center[1] + 2),
                (center[0] + 1, center[1] + 2), (center[0] + 1, center[1] + 4),
                (center[0] + 5, center[1]), (center[0] + 1, center[1] - 4),
                (center[0] + 1, center[1] - 2)
            ])
        elif self.effect_type == 'jump':
            # Up arrow for jump
            pygame.draw.polygon(surface, (255, 255, 255), [
                (center[0], center[1] + 3), (center[0] - 2, center[1] - 1),
                (center[0] - 1, center[1] - 1), (center[0] - 1, center[1] - 5),
                (center[0] + 1, center[1] - 5), (center[0] + 1, center[1] - 1),
                (center[0] + 2, center[1] - 1)
            ])
        elif self.effect_type == 'shield':
            # Shield shape
            pygame.draw.ellipse(surface, (255, 255, 255), pygame.Rect(center[0] - 3, center[1] - 4, 6, 8))
            pygame.draw.rect(surface, (255, 255, 255), pygame.Rect(center[0] - 1, center[1] - 4, 2, 4))
        elif self.effect_type == 'double_jump':
            # Two up arrows
            pygame.draw.polygon(surface, (255, 255, 255), [
                (center[0] - 2, center[1] + 3), (center[0] - 3, center[1] - 1),
                (center[0] - 1, center[1] - 1), (center[0] - 1, center[1] - 4),
                (center[0] + 1, center[1] - 4), (center[0] + 1, center[1] - 1),
                (center[0], center[1] - 1)
            ])
            pygame.draw.polygon(surface, (255, 255, 255), [
                (center[0] + 2, center[1] + 3), (center[0] + 1, center[1] - 1),
                (center[0] + 3, center[1] - 1), (center[0] + 3, center[1] - 4),
                (center[0] + 5, center[1] - 4), (center[0] + 5, center[1] - 1),
                (center[0] + 4, center[1] - 1)
            ])
        elif self.effect_type == 'launch':
            # Rocket or launch symbol
            pygame.draw.polygon(surface, (255, 255, 255), [
                (center[0] - 2, center[1] + 4), (center[0] + 2, center[1] + 4),
                (center[0] + 2, center[1] - 2), (center[0] + 3, center[1] - 2),
                (center[0], center[1] - 6), (center[0] - 3, center[1] - 2),
                (center[0] - 2, center[1] - 2)
            ]) #Debuff
        elif self.effect_type == 'reverse_control':
            # Left arrow for reverse
            pygame.draw.polygon(surface, (255, 255, 255), [
                (center[0] + 3, center[1] - 2), (center[0] + 3, center[1] + 2),
                (center[0] - 1, center[1] + 2), (center[0] - 1, center[1] + 4),
                (center[0] - 5, center[1]), (center[0] - 1, center[1] - 4),
                (center[0] - 1, center[1] - 2)
            ])
        elif self.effect_type == 'slippery':
            # Wavy line for slippery
            pygame.draw.arc(surface, (255, 255, 255), pygame.Rect(center[0] - 4, center[1] - 4, 8, 8), 0, math.pi, 2)
        elif self.effect_type == 'slow_falling':
            # Down arrow for slow falling
            pygame.draw.polygon(surface, (255, 255, 255), [
                (center[0], center[1] - 3), (center[0] - 2, center[1] + 1),
                (center[0] - 1, center[1] + 1), (center[0] - 1, center[1] + 5),
                (center[0] + 1, center[1] + 5), (center[0] + 1, center[1] + 1),
                (center[0] + 2, center[1] + 1)
            ])
        elif self.effect_type == 'heavy':
            # Weight symbol, like a dumbbell
            pygame.draw.line(surface, (255, 255, 255), (center[0] - 3, center[1]), (center[0] + 3, center[1]), 2)
            pygame.draw.circle(surface, (255, 255, 255), (center[0] - 3, center[1]), 1)
            pygame.draw.circle(surface, (255, 255, 255), (center[0] + 3, center[1]), 1)
        elif self.effect_type == 'weak_jump':
            # Small up arrow for weak jump
            pygame.draw.polygon(surface, (255, 255, 255), [
                (center[0], center[1] + 2), (center[0] - 1, center[1] - 1),
                (center[0] - 1, center[1] - 3), (center[0] + 1, center[1] - 3),
                (center[0] + 1, center[1] - 1), (center[0] + 2, center[1] - 1)
            ])
        elif self.effect_type == 'orb':
            # Orb shape
            pygame.draw.circle(surface, (255, 255, 255), center, 4, 1)
            pygame.draw.arc(surface, (255, 255, 255), pygame.Rect(center[0] - 3, center[1] - 3, 6, 6), math.pi / 4, 5 * math.pi / 4, 1)
        else:
            # Default +
            pygame.draw.line(surface, (255, 255, 255), (center[0] - 4, center[1]), (center[0] + 4, center[1]), 2)
            pygame.draw.line(surface, (255, 255, 255), (center[0], center[1] - 4), (center[0], center[1] + 4), 2)