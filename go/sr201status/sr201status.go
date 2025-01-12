package sr201status

import (
	"fmt"
	"net"
	"strings"
	"time"
)

// SR201 struct to handle the relay device
type SR201 struct {
	IP      string
	Port    string
	Conn    net.Conn
	Timeout time.Duration
}

// NewSR201Status initializes a new SR201 instance
func NewSR201Status(ip string, port string) (*SR201, error) {
	conn, err := net.DialTimeout("tcp", fmt.Sprintf("%s:%s", ip, port), 5*time.Second)
	if err != nil {
		return nil, err
	}
	return &SR201{
		IP:      ip,
		Port:    port,
		Conn:    conn,
		Timeout: 5 * time.Second,
	}, nil
}

// Close closes the connection
func (s *SR201) Close() error {
	if s.Conn != nil {
		return s.Conn.Close()
	}
	return nil
}

// Send sends a command to the relay
func (s *SR201) Send(command string) (string, error) {
	_, err := s.Conn.Write([]byte(command))
	if err != nil {
		return "", err
	}

	buffer := make([]byte, 4096)
	s.Conn.SetReadDeadline(time.Now().Add(s.Timeout))
	n, err := s.Conn.Read(buffer)
	if err != nil {
		return "", err
	}

	response := strings.TrimSpace(string(buffer[:n]))
	return response, nil
}

// CheckStatus checks the status of the relay
func (s *SR201) CheckStatus() (string, error) {
	response, err := s.Send("00")
	if err != nil {
		return "", err
	}
	return response, nil
}

func main() {
	// Replace with your SR201 IP address and port
	SR201_IP := "192.168.100.100"
	SR201_PORT := "6722"

	sr201, err := NewSR201Status(SR201_IP, SR201_PORT)
	if err != nil {
		fmt.Println("Failed to connect to SR201:", err)
		return
	}
	defer sr201.Close()

	status, err := sr201.CheckStatus()
	if err != nil {
		fmt.Println("Error checking status:", err)
	} else {
		fmt.Printf("Relay status: %s\n", status)
	}
}
