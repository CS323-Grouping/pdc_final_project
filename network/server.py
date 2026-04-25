import socket
import threading
import struct

FRMT_PACKET = "!4sii"
CONNECTION = b"CONN"
GET_POS = b"GPOS"
POS = b"POSI"

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

def handle_messages(data, addr):
    global curr_player

    cmd, x, y = struct.unpack(FRMT_PACKET, data)

    if addr not in Known_Addresses:
        print(f"Connection from {addr}")
        Known_Addresses[addr] = curr_player
        curr_player += 1

        reply = struct.pack(FRMT_PACKET, CONNECTION, 0, 0)
        s.sendto(reply, addr)


    if cmd == GET_POS:
        reply = struct.pack(FRMT_PACKET, POS, 100, 100)
        s.sendto(reply, addr)

    # need to update so that it sends out positions of multiplayer guys


while True:
    data, addr = s.recvfrom(128)
    handle_messages(data, addr)




