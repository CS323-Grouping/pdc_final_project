import socket
import threading
import pickle

server = "0.0.0.0"
port = 5555

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind((server, port))


print("Waiting for a connection, Server Started")

pos = {}

lock = threading.Lock()
curr_player = 0

Known_Addresses = {}

while True:
    data, addr = s.recvfrom(128)
    if addr not in Known_Addresses:
        print(f"Connection from {addr}")
        s.sendto("Connection Successful".encode(), addr)
        Known_Addresses[addr] = curr_player
        curr_player + 1


    for address in Known_Addresses:
        if addr != address:
            s.sendto(data, address)


