class MockSr201:
    def __init__(self, ip_address):
        self.ip_address = ip_address
        # Assuming a single relay for simplicity. Expand as needed.
        self.relay_status = "00000000"

    def do_return_status(self, command):
        # Simulate returning the status of the relay
        if command == 'status':
            return self.relay_status

    def do_close(self, command):
        # Simulate closing the relay
        if command.startswith('close:'):
            pass
            #self.relay_status = False
            #return "Relay closed"
        else:
            pass

    def do_open(self, command):
        # Simulate opening the relay
        if command.startswith('open:'):
            pass
            #self.relay_status = True
            #return "Relay opened"
        else:
            pass

    def close(self):
        # Simulate closing any connections, if necessary
        pass
