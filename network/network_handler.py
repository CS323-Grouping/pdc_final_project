import socket
import struct

FRMT_PACKET = "!4sffi" #Command, x, y, #id
CONNECTION = b"CONN"
POSITION = b"POSI"
DISCONNECT = b"DISC"
DISCOVER = b'DSCV'

class Network:
    def __init__(self, IP="", PORT=5555):
        self.client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.client.settimeout(0.1)

        self.server = IP
        self.port = PORT
        self.addr = (self.server, self.port)
        self.id = 0

    def connect(self):
        try:
            discover_msg = struct.pack(FRMT_PACKET, DISCOVER, 0.0, 0.0, 0)
            self.client.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.client.settimeout(2)

            self.client.sendto(discover_msg, ("255.255.255.255", 5555))

            print("Searching for servers...")

            servers = []

            while True:
                try:
                    data, addr = self.client.recvfrom(128)

                    if len(data) != struct.calcsize(FRMT_PACKET):
                        continue

                    cmd, x, y, sid = struct.unpack(FRMT_PACKET, data)

                    if cmd == DISCOVER:
                        print(f"Found server at {addr}")
                        servers.append(addr)

                except socket.timeout:
                    break

            if not servers:
                print("No servers found.")
                return None

            self.addr = servers[0]
            print(f"Connecting to {self.addr}...")

            conn_msg = struct.pack(FRMT_PACKET, CONNECTION, 0.0, 0.0, self.id)
            self.client.sendto(conn_msg, self.addr)

            data, addr = self.client.recvfrom(128)

            cmd, x, y, new_id = struct.unpack(FRMT_PACKET, data)

            if cmd != CONNECTION:
                print(f"Unexpected response: {cmd}")
                return None

            self.id = new_id

            print("Connection successful")
            return (x, y)

        except Exception as e:
            print(f"Connection Error: {e}")

    def update_pos(self, x, y):
        try:
            msg = struct.pack(FRMT_PACKET, POSITION, x, y, self.id)
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
            msg = struct.pack(FRMT_PACKET, DISCONNECT, 0, 0, self.id)
            self.client.sendto(msg, self.addr)
        except Exception as e:
            print(f"Error disconnecting: {e}")

