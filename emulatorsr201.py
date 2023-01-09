import socket

HOST = "127.0.0.1"  # Standard loopback interface address (localhost)
PORT = 6722  # Port to listen on (non-privileged ports are > 1023)
currentstatus = 000000

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind((HOST, PORT))
    s.listen()
    conn, addr = s.accept()
    with conn:
        print(f"Connected by {addr}")
        while True:
            data = conn.recv(8)
            print(type(data))
            if not data:
                print(f"No data")
                break
            #conn.sendall(data)
            print(data)
            if data == "00":
                conn.sendall(currentstatus)
