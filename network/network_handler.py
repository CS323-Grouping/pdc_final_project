import socket
import pickle



class Network:
    def __init__(self):
        self.client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.client.settimeout(0.1)

        self.server = "192.168.1.5"
        self.port = 5555
        self.addr = (self.server, self.port)

        self.id = self.connect()

    def connect(self):
        try:
            self.client.sendto(b"connect", self.addr)
            data, _ = self.client.recvfrom(2048)
            return int(data.decode())

        except Exception as e:
            print(f"Connection Error: {e}")
            return None

    def get_pos(self):
        try:
            data = self.client.recvfrom(128)
            if not data:
                return None
            return pickle.loads(data)
        except socket.timeout:
            return None
        except Exception as e:
            print(f"get_pos error: {e}")
            return None

    def send(self, data):
        try:
            self.client.sendto(pickle.dumps(data), self.addr)
            data, _ = self.client.recvfrom(2048)
            if not data:
                return None
            return pickle.loads(data)
        except socket.timeout:
            return None
        except Exception as e:
            print(f"send error: {e}")
            return None