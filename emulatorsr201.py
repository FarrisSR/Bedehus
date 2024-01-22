import socket

HOST = "127.0.0.1"  # Standard loopback interface address (localhost)
PORT = 6722  # Port to listen on (non-privileged ports are > 1023)
currentstatus = "000000"

class relay:
  def __init__(self, state, timer):
    self.state = state
    self.timer = timer

    def status(self):
        print(self.relay + self.timer)

class sr201board:
    def __init__(self,relays):
        i = 0
        board = []
        while i < relays:
            board.append(relay(0,0))
            i += 1



sr201b = sr201board(2)
print(sr201b)

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    try:
        s.bind((HOST, PORT))
        s.listen()
    except:
        print(f"Unable to bind to socket")

    while True:
        conn, addr = s.accept()

        with conn:
            print(f"Connected by {addr}")

            data = conn.recv(8)
            print(type(data))
            print(str(bytes(data)))
            print(type(currentstatus.encode('latin1')))
            if not data:
                print(f"No data")
                conn.detach()
                conn.close()
                #conn.sendall(data)
            if data.decode() == "00":
                print(f"Asking for Current status")
                returnstatus = str(currentstatus).encode()
                conn.settimeout(5)

                try:
                    sent = conn.send(returnstatus)
                except socket.timeout:
                    print("Client buffer full")
                    sent = 0

                if sent > 0:
                    print(f"Data sent successfully, sent: {sent}")
                else:
                    print(f"Error occured while sending data, sent: {sent}")

                conn.detach()

            else:
                print(f"Recived: {data.decode()}")
                conn.detach()

    conn.close()
