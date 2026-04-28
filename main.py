

import pygame
import threading
import queue
import struct

from random import randint

from player_scripts import player as pl
from network import network_handler as nw
from world.level_1 import create_level_1

server_data = {}

lock = threading.Lock()

server_queue = queue.Queue()
def network_thread(network_obj):
    global server_data
    while True:
        data = network_obj.receive()
        if not data:
            continue
        # def __init__(self, start_pos, image_path, color=(255,0,255)):
        cmd, x, y, player_id = data
        print("Received:", data)
        if cmd == nw.POSITION:
            with lock:
                server_data[player_id] = (x, y)

pygame.init()
screen = pygame.display.set_mode((640, 640), pygame.RESIZABLE)
clock = pygame.time.Clock()

n = nw.Network()

start_pos = n.connect()
if not start_pos:
    start_pos = (100, 100)

hero = pl.Player(start_pos, "assets/characters/placeholder_AI_Knight.png")

Network_thread = threading.Thread(target=network_thread, args=(n,), daemon=True)
Network_thread.start()

running = True
dt = 0

platforms = create_level_1() # CHANGE TO DYNAMICALLY CHANGE LEVELS

last_position = None

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    WIDTH, HEIGHT = screen.get_size()
    hero.update(dt, WIDTH, HEIGHT, platforms)
    if last_position is None or hero.pos != last_position:
        n.update_pos(hero.pos.x, hero.pos.y)
        last_position = hero.pos.copy()

    screen.fill((0, 0, 0))

    for platform in platforms:
        platform.draw(screen)

    with lock:
        positions = dict(server_data)
    width = 64
    height = 128

    for p_id, p_pos in positions.items():
        if int(p_id) != n.id:
            draw_x = int(p_pos[0] - width / 2)
            draw_y = int(p_pos[1] - height / 2)

            pygame.draw.rect(
                screen,
                (0, 0, 255),
                (draw_x, draw_y, width, height)
            )

    hero.draw(screen)

    pygame.display.flip()
    dt = clock.tick(60) / 1000

# print("disconnecting...")
n.disconnect()

pygame.quit()