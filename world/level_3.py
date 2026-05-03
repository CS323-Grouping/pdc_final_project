from world.shapes import platform as plat
from world.shapes import powerup as pw

def create_level_3():
    platforms = []
    powerups = []

    # Ground
    platforms.append(plat.Platform(800, 40, (0, 560)))

    # Lower stepping platforms
    platforms.append(plat.Platform(120, 20, (100, 500)))
    platforms.append(plat.Platform(120, 20, (280, 430)))
    platforms.append(plat.Platform(120, 20, (450, 360)))

    # Upper precision platforms
    platforms.append(plat.Platform(90, 20, (230, 280)))
    platforms.append(plat.Platform(90, 20, (520, 220)))
    platforms.append(plat.Platform(90, 20, (680, 160)))

    # Final jump platforms
    platforms.append(plat.Platform(120, 20, (140, 180)))
    platforms.append(plat.Platform(120, 20, (360, 140)))

    powerups.append(pw.PowerUp((120, 460), effect="speed", duration=5))
    powerups.append(pw.PowerUp((520, 190), effect="jump", duration=5))
    powerups.append(pw.PowerUp((560, 130), effect="double_jump", duration=15))

    return platforms, powerups
