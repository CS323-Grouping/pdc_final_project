import socket
import threading
import struct

FRMT_PACKET = "!4sffi" #command, x, y, id
CONNECTION = b"CONN"
GET_POS = b"GPOS"
POS = b"POSI"
DISC = B"DISC"

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

def handle_messages(data, addr):
    global curr_player

    cmd, x, y, recv_id = struct.unpack(FRMT_PACKET, data)

    if addr not in Known_Addresses:
        print(f"Connection from {addr}")

        player_id = curr_player
        Known_Addresses[addr] = player_id
        curr_player += 1


        reply = struct.pack(FRMT_PACKET, CONNECTION, 100, 100, player_id)
        s.sendto(reply, addr)

        return


    if cmd == POS:
        msg = struct.pack(FRMT_PACKET, POS, x, y, id)
        for addrs in Known_Addresses:
            if addr == addrs:
                continue

            s.sendto(msg, addrs)

    if cmd == DISC:
        print(f"{addr} disconnected")
        del Known_Addresses[addr]





while True:
    data, addr = s.recvfrom(128)
    handle_messages(data, addr)




