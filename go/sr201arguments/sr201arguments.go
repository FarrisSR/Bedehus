package sr201arguments

import (
	"flag"
	"fmt"
	"net"
	"os"
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

// NewSR201arg initializes a new SR201 instance
func NewSR201arg(ip string, port string) (*SR201, error) {
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

// CloseRelay closes the specified relay
func (s *SR201) CloseRelay(relay int) error {
	command := fmt.Sprintf("1%d", relay)
	_, err := s.Send(command)
	return err
}

// OpenRelay opens the specified relay
func (s *SR201) OpenRelay(relay int) error {
	command := fmt.Sprintf("2%d", relay)
	_, err := s.Send(command)
	return err
}

func main() {
	// Command-line arguments
	ip := flag.String("ip", "192.168.100.100", "IP address of SR201 relay")
	port := flag.String("port", "6722", "Port of SR201 relay")
	action := flag.String("action", "status", "Action to perform: status, open, close")
	relay := flag.Int("relay", 1, "Relay number to operate on")
	flag.Parse()

	sr201, err := NewSR201arg(*ip, *port)
	if err != nil {
		fmt.Println("Failed to connect to SR201:", err)
		os.Exit(1)
	}
	defer sr201.Close()

	switch *action {
	case "status":
		status, err := sr201.CheckStatus()
		if err != nil {
			fmt.Println("Error checking status:", err)
			os.Exit(1)
		}
		fmt.Printf("Relay status: %s\n", status)

	case "open":
		if err := sr201.OpenRelay(*relay); err != nil {
			fmt.Println("Error opening relay:", err)
			os.Exit(1)
		}
		fmt.Printf("Relay %d opened.\n", *relay)

	case "close":
		if err := sr201.CloseRelay(*relay); err != nil {
			fmt.Println("Error closing relay:", err)
			os.Exit(1)
		}
		fmt.Printf("Relay %d closed.\n", *relay)

	default:
		fmt.Println("Unknown action. Use status, open, or close.")
		os.Exit(1)
	}
}
