from world.shapes import platform as plat
from world.shapes import powerup as pw

def create_level_5():
    platforms = []
    powerups = []

    # Ground
    platforms.append(plat.Platform(800, 40, (0, 560)))

    # Initial ascending platforms
    platforms.append(plat.Platform(120, 20, (100, 480)))
    platforms.append(plat.Platform(120, 20, (240, 420)))
    platforms.append(plat.Platform(120, 20, (380, 360)))

    # Zigzag challenge section
    platforms.append(plat.Platform(90, 20, (520, 300)))
    platforms.append(plat.Platform(90, 20, (420, 240)))
    platforms.append(plat.Platform(90, 20, (580, 180)))

    # Final high platform
    platforms.append(plat.Platform(120, 20, (700, 120)))

    powerups.append(pw.PowerUp((120, 440), effect="speed", duration=5))
    powerups.append(pw.PowerUp((420, 200), effect="jump", duration=5))

    return platforms, powerups
