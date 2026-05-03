from world.shapes import platform as plat
from world.shapes import powerup as pw

def create_level_4():
    platforms = []
    powerups = []

    # Ground
    platforms.append(plat.Platform(800, 40, (0, 560)))

    # Side-by-side low platforms
    platforms.append(plat.Platform(140, 20, (120, 500)))
    platforms.append(plat.Platform(140, 20, (300, 450)))
    platforms.append(plat.Platform(140, 20, (500, 400)))

    # Short vertical jump section
    platforms.append(plat.Platform(100, 20, (190, 360)))
    platforms.append(plat.Platform(100, 20, (370, 320)))
    platforms.append(plat.Platform(100, 20, (560, 280)))

    # Final high platform
    platforms.append(plat.Platform(120, 20, (680, 220)))

    powerups.append(pw.PowerUp((150, 460), effect="speed", duration=6))
    powerups.append(pw.PowerUp((560, 250), effect="jump", duration=6))

    return platforms, powerups
