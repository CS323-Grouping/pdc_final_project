import socket
import struct

FRMT_PACKET = "!4sffi" #Command, x, y, #id
CONNECTION = b"CONN"
GET_POS = b"GPOS"
POS = b"POSI"
DISC = B"DISC"

class Network:
    def __init__(self):
        self.client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.client.settimeout(0.1)

        self.server = "192.168.1.13"
        self.port = 5555
        self.addr = (self.server, self.port)
        self.id = 0


    def connect(self):
        try:
            msg = struct.pack(FRMT_PACKET, CONNECTION, 0, 0, self.id)
            self.client.sendto(msg, self.addr)
            data, addr = self.client.recvfrom(128)
            cmd, x, y, id = struct.unpack(FRMT_PACKET, data)
            self.id = id

            if cmd != CONNECTION:
                print(f"Unexpected response: {cmd}")
                return None

            print("connection successful")
            return (x,y)
        except Exception as e:
            print(f"Connection Error: {e}")

    def update_pos(self, x, y):
        try:
            msg = struct.pack(FRMT_PACKET, POS, x, y, self.id)
            self.client.sendto(msg, self.addr)
        except Exception as e:
            print(f"Exception in update_pos: {e}")
    def receive(self):
        try:
            data, addr = self.client.recvfrom(128)
            cmd, x, y, recv_id = struct.unpack(FRMT_PACKET, data)

            return cmd, x, y, recv_id
        except socket.timeout:
            return None
        except Exception as e:
            print(f"Receive error: {e}")
            return None
    def disconnect(self):
        try:
            msg = struct.pack(FRMT_PACKET, DISC, 0, 0, self.id)
            self.client.sendto(msg, self.addr)
        except Exception as e:
            print(f"Error disconnecting: {e}")

