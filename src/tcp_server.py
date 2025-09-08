# tcp_server.py
import socket

def start_server(host="0.0.0.0", port=12345):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, port))
        s.listen(1)
        print(f"TCP Server listening on {host}:{port}")
        conn, addr = s.accept()
        with conn:
            print(f"Connected by {addr}")
            with open("logs/tcp_received_file.txt", "wb") as f:
                while True:
                    data = conn.recv(4096)
                    if not data:
                        break
                    f.write(data)
            print("File received")

if __name__ == "__main__":
    start_server()
