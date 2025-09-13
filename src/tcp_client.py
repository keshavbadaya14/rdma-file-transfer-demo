# tcp_client.py
import socket
import time

def send_file(file_path, host, port=12345):
    start_time = time.time()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((host, port))
        with open(file_path, 'rb') as f:
            while chunk := f.read(4096):
                s.sendall(chunk)
    elapsed = time.time() - start_time
    print(f"TCP Transfer completed in {elapsed:.4f} seconds")
    return elapsed

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python tcp_client.py <file_path> <server_ip>")
    else:
        send_file(sys.argv[1], sys.argv[2])
