import socket
import struct

FRMT_PACKET = "!4sii"
CONNECTION = b"CONN"
GET_POS = b"GPOS"
POS = b"POSI"

class Network:
    def __init__(self):
        self.client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.client.settimeout(0.1)

        self.server = "192.168.1.13"
        self.port = 5555
        self.addr = (self.server, self.port)

        self.connect()

    def connect(self):
        try:
            msg = struct.pack(FRMT_PACKET, CONNECTION, 0, 0)
            self.client.sendto(msg, self.addr)
            data, addr = self.client.recvfrom(128)
            cmd, x, y = struct.unpack(FRMT_PACKET, data)

            if cmd == CONNECTION:
                print("connection successful")
        except Exception as e:
            print(f"Connection Error: {e}")

    def get_pos(self):
        try:
            msg = struct.pack(FRMT_PACKET, GET_POS, 0, 0)
            self.client.sendto(msg, self.addr)

            data, addr = self.client.recvfrom(128)
            cmd, x, y = struct.unpack(FRMT_PACKET, data)

            if cmd == POS:
                return (x, y)

        except Exception as e:
            print(f"Error: {e}")
            return None