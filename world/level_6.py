from world.shapes import platform as plat
from world.shapes import powerup as pw

def create_level_6():
    platforms = []
    powerups = []

    # Ground
    platforms.append(plat.Platform(800, 40, (0, 560)))

    # Ascending mid-level platforms
    platforms.append(plat.Platform(140, 20, (100, 480)))
    platforms.append(plat.Platform(140, 20, (280, 420)))
    platforms.append(plat.Platform(140, 20, (460, 360)))
    platforms.append(plat.Platform(140, 20, (240, 300)))
    platforms.append(plat.Platform(140, 20, (520, 260)))

    # Challenge section
    platforms.append(plat.Platform(120, 20, (360, 220)))
    platforms.append(plat.Platform(120, 20, (580, 180)))

    powerups.append(pw.PowerUp((130, 440), effect="lunch_boost", duration=10))
    powerups.append(pw.PowerUp((300, 380), effect="low_gravity", duration=12))
    powerups.append(pw.PowerUp((560, 230), effect="dash", duration=8))

    return platforms, powerups
