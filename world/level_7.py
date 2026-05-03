from world.shapes import platform as plat
from world.shapes import powerup as pw

def create_level_7():
    platforms = []
    powerups = []

    # Ground
    platforms.append(plat.Platform(800, 40, (0, 560)))

    # Long platform
    platforms.append(plat.Platform(700, 20, (50, 380)))

    # Single center platform above the long platform
    platforms.append(plat.Platform(120, 20, (340, 260)))

    #All power ups Are here
    powerups.append(pw.PowerUp((100, 520), effect="speed", duration=6))
    powerups.append(pw.PowerUp((220, 520), effect="jump", duration=6))
    powerups.append(pw.PowerUp((340, 220), effect="slowfall", duration=12))
    powerups.append(pw.PowerUp((460, 520), effect="double_jump", duration=15))
    powerups.append(pw.PowerUp((580, 520), effect="shield", duration=10))
    powerups.append(pw.PowerUp((100, 420), effect="lunch_boost", duration=10))
    powerups.append(pw.PowerUp((250, 420), effect="low_gravity", duration=12))
    powerups.append(pw.PowerUp((520, 420), effect="dash", duration=8))

    return platforms, powerups
