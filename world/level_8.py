from world.shapes import platform as plat
from world.shapes import powerup as pw

def create_level_8():
    platforms = []
    powerups = []

    # Ground
    platforms.append(plat.Platform(800, 40, (0, 560)))

    # Long platform
    platforms.append(plat.Platform(700, 20, (50, 380)))

    # Single center platform above the long platform
    platforms.append(plat.Platform(120, 20, (340, 260)))

    # Debuff power-ups aligned horizontally with spacing
    powerups.append(pw.PowerUp((80, 520), effect="heavy", duration=10))
    powerups.append(pw.PowerUp((180, 520), effect="slow", duration=8))
    powerups.append(pw.PowerUp((280, 520), effect="ice", duration=12))
    powerups.append(pw.PowerUp((380, 520), effect="weak_jump", duration=6))
    powerups.append(pw.PowerUp((480, 520), effect="reverse_control", duration=15))

    return platforms, powerups