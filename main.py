import pygame

pygame.init()

screen = pygame.display.set_mode((640,640), pygame.RESIZABLE)
clock = pygame.time.Clock()
p_pos = pygame.Vector2(screen.get_width() / 2, screen.get_height() / 2)
player = pygame.image.load("assets/characters/placeholder_AI_Knight.png").convert_alpha()
player = pygame.transform.scale(player, (128, 128))
dt = 0


def check_border(position):
    if position.x > screen.get_width():
        position.x = screen.get_width()
    if position.x < 0:
        position.x = 0
    if position.y > screen.get_height():
        position.y = screen.get_height()
    if position.y < 0:
        position.y = 0


    return position

running = True
while running:
    WIDTH, HEIGHT = screen.get_size()

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    rect = player.get_rect(center=p_pos)

    screen.blit(player, rect)

    keys = pygame.key.get_pressed()
    if keys[pygame.K_w]: # needs normalization along the diagonal
        p_pos.y -= 300 * dt
    if keys[pygame.K_s]:
        p_pos.y += 300 * dt
    if keys[pygame.K_a]:
        p_pos.x -= 300 * dt
    if keys[pygame.K_d]:
        p_pos.x += 300 * dt
    pygame.display.flip()
    dt = clock.tick(60) / 1000

    p_pos = check_border(p_pos)



    screen.fill((0,0,0))





pygame.quit()
