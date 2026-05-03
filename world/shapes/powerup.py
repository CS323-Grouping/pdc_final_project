import pygame

class PowerUp():
    def __init__(self, pos, size=20, effect="speed", duration=5):
        self.size = size
        self.color = (255, 255, 0)  # yellow
        self.pos = pygame.Vector2(pos)
        self.rect = pygame.Rect(self.pos.x, self.pos.y, self.size, self.size)
        self.effect = effect
        self.duration = duration
        self.active = True

        if self.effect == "shield":
            self.color = (0, 150, 255)
        elif self.effect == "jump":
            self.color = (0, 255, 0)  # green
        elif self.effect == "double_jump":
            self.color = (150, 0, 255)
        elif self.effect == "lunch_boost":
            self.color = (255, 0, 0)  # red
        elif self.effect == "low_gravity":
            self.color = (173, 216, 230)  # light blue
        elif self.effect == "slowfall":
            self.color = (255, 255, 255)  # white
        elif self.effect == "dash":
            #DebuFF
            self.color = (0, 0, 255)  # blue
        elif self.effect == "heavy":
            self.color = (139, 0, 0)  # dark red
        elif self.effect == "slow":
            self.color = (75, 0, 130)  # dark purple
        elif self.effect == "ice":
            self.color = (135, 206, 235)  # sky blue
        elif self.effect == "weak_jump":
            self.color = (128, 128, 128)  # gray
        elif self.effect == "reverse_control":
            self.color = (0, 100, 0)  # dark green

    def draw(self, surface):
        if self.active:
            pygame.draw.rect(surface, self.color, self.rect)

    def apply(self, player):
        if self.effect == "speed":
            player.apply_effect("speed", 1.5, self.duration)
        elif self.effect == "jump":
            player.apply_effect("jump", 1.5, self.duration)
        elif self.effect == "shield":
            player.apply_effect("shield", None, self.duration)
        elif self.effect == "double_jump":
            player.apply_effect("double_jump", None, self.duration)
        elif self.effect == "lunch_boost":
            player.apply_effect("lunch_boost", 1.6, self.duration)
        elif self.effect == "low_gravity":
            player.apply_effect("low_gravity", None, self.duration)
        elif self.effect == "slowfall":
            player.apply_effect("slowfall", None, self.duration)
        elif self.effect == "dash":
            player.apply_effect("dash", None, self.duration)
        elif self.effect == "heavy":
            player.apply_effect("heavy", None, self.duration)
        elif self.effect == "slow":
            player.apply_effect("slow", None, self.duration)
        elif self.effect == "ice":
            player.apply_effect("ice", None, self.duration)
        elif self.effect == "weak_jump":
            player.apply_effect("weak_jump", None, self.duration)
        elif self.effect == "reverse_control":
            player.apply_effect("reverse_control", None, self.duration)

        self.active = False  # remove after use