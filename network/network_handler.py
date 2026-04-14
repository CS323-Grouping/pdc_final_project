import socket
import pickle


class Network:
    def __init__(self):
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client.settimeout(0.1)
        self.server = "192.168.1.2"
        self.port = 5555
        self.addr = (self.server, self.port)
        self.id = self.connect()

    def connect(self):
        try:
            self.client.connect(self.addr)
            data = self.client.recv(2048)
            if not data:
                return None
            return int(data.decode())
        except Exception as e:
            print(f"Connection Error: {e}")
            return None

    def get_pos(self):
        try:
            data = self.client.recv(2048)
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
            self.client.send(pickle.dumps(data))
            data = self.client.recv(2048)
            if not data:
                return None
            return pickle.loads(data)
        except socket.timeout:
            return None
        except Exception as e:
            print(f"send error: {e}")
            return None