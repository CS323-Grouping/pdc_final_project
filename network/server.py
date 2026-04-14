import socket
import threading
import pickle

server = "0.0.0.0"
port = 5555

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.bind((server, port))
s.listen()

print("Waiting for a connection, Server Started")

pos = {}
lock = threading.Lock()
curr_player = 0


def threaded_client(conn, player):
    global pos

    try:
        conn.send(str(player).encode())
    except:
        conn.close()
        return

    with lock:
        pos[player] = (320, 320)

    try:
        conn.send(pickle.dumps(pos[player]))
    except:
        conn.close()
        return

    while True:
        try:
            data = conn.recv(2048)
            if not data:
                break

            data = pickle.loads(data)

            with lock:
                pos[player] = data
                reply = dict(pos)

            conn.sendall(pickle.dumps(reply))

        except:
            break

    print("Lost connection:", player)

    with lock:
        if player in pos:
            del pos[player]

    conn.close()


while True:
    conn, addr = s.accept()
    print("Connected to:", addr)

    threading.Thread(target=threaded_client, args=(conn, curr_player), daemon=True).start()
    curr_player += 1