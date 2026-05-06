from world.shapes import platform as plat

def create_level_1():
    platforms = []

    # Ground
    platforms.append(plat.Platform(800, 40, (0, 560)))

    # Floating platforms
    platforms.append(plat.Platform(120, 20, (150, 450)))
    platforms.append(plat.Platform(120, 20, (350, 380)))
    platforms.append(plat.Platform(120, 20, (550, 300)))

    # # Small challenge platforms
    # platforms.append(plat.Platform(80, 20, (300, 250)))
    # platforms.append(plat.Platform(80, 20, (450, 200)))

    return platforms