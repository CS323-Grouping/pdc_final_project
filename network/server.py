import socket
import threading
import struct

FRMT_PACKET = "!4sffi" #command, x, y, id
CONNECTION = b"CONN"
POSITION = b"POSI"
DISCONNECT = b"DISC"
DISCOVER = b'DSCV'

server = "0.0.0.0"
port = 5555

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind((server, port))


print("Waiting for a connection, Server Started")

pos = {}

# lock = threading.Lock()
curr_player = 0

Known_Addresses = {}

start_position = (100, 100)

id = 0

server = "0.0.0.0"
port = 5555

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind((server, port))

print("Server started, waiting for connections...")

curr_player = 0
known_addresses = {}   # addr -> player_id
player_positions = {}  # player_id -> (x, y)

PACKET_SIZE = struct.calcsize(FRMT_PACKET)


def handle_messages(data, addr):
    global curr_player

    if len(data) != PACKET_SIZE:
        return

    cmd, x, y, recv_id = struct.unpack(FRMT_PACKET, data)

    if cmd == DISCOVER:
        reply = struct.pack(FRMT_PACKET, DISCOVER, 0.0, 0.0, 0)
        s.sendto(reply, addr)
        return

    if addr not in known_addresses:
        player_id = curr_player
        curr_player += 1

        known_addresses[addr] = player_id
        player_positions[player_id] = (100.0, 100.0)

        print(f"New connection {addr} -> id {player_id}")

        reply = struct.pack(FRMT_PACKET, CONNECTION, 100.0, 100.0, player_id)
        s.sendto(reply, addr)
        return

    player_id = known_addresses[addr]

    if cmd == POSITION:
        player_positions[player_id] = (x, y)

        msg = struct.pack(FRMT_PACKET, POSITION, x, y, player_id)

        for other_addr, other_id in known_addresses.items():
            if other_addr == addr:
                continue
            s.sendto(msg, other_addr)

    elif cmd == DISCONNECT:
        print(f"Player {player_id} disconnected")

        del known_addresses[addr]
        del player_positions[player_id]


while True:
    data, addr = s.recvfrom(1024)
    handle_messages(data, addr)
