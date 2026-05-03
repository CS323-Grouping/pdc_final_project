from world.shapes import platform as plat
from world.shapes import powerup as pw

def create_level_2():
    platforms = []
    powerups = []

    # Ground
    platforms.append(plat.Platform(800, 40, (0, 560)))

    # Floating platforms
    platforms.append(plat.Platform(120, 20, (100, 450)))
    platforms.append(plat.Platform(120, 20, (260, 360)))
    platforms.append(plat.Platform(120, 20, (420, 280)))
    platforms.append(plat.Platform(120, 20, (540, 220)))

    # High challenge platforms
    platforms.append(plat.Platform(80, 20, (320, 200)))
    platforms.append(plat.Platform(80, 20, (520, 140)))

    powerups.append(pw.PowerUp((130, 410), effect="speed"))
    powerups.append(pw.PowerUp((420, 340), effect="shield", duration=6))
    powerups.append(pw.PowerUp((540, 110), effect="jump"))

    return platforms, powerups