import pygame
import threading
from player_scripts import player as pl
from network import network_handler as nw

server_data = {}
lock = threading.Lock()

def network_thread(network_obj, hero_obj):
    global server_data
    while True:
        try:
            reply = network_obj.send((hero_obj.pos.x, hero_obj.pos.y))
            if reply:
                with lock:
                    server_data = reply
        except Exception as e:
            print(f"Network error: {e}")
            break

pygame.init()
screen = pygame.display.set_mode((640, 640), pygame.RESIZABLE)
clock = pygame.time.Clock()

n = nw.Network()
start_pos = n.get_pos()
if not start_pos:
    start_pos = (100, 100)

hero = pl.Player(start_pos, "assets/characters/placeholder_AI_Knight.png")

t = threading.Thread(target=network_thread, args=(n, hero), daemon=True)
t.start()

running = True
dt = 0

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    WIDTH, HEIGHT = screen.get_size()
    hero.update(dt, WIDTH, HEIGHT)

    screen.fill((0, 0, 0))


    with lock:
        positions = dict(server_data)

    for p_id, p_pos in positions.items():
        if int(p_id) != n.id:
            pygame.draw.circle(screen, (255, 0, 0), (int(p_pos[0]), int(p_pos[1])), 20)
    hero.draw(screen)

    hero.draw(screen)

    pygame.display.flip()
    dt = clock.tick(60) / 1000

pygame.quit()