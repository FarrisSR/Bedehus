package sr201

import (
	"fmt"
	"net"
	"strings"
	"time"
)

// SR201 struct to handle the relay device
type SR201 struct {
	IP       string
	Port     string
	Protocol string
	Relay    int
	Conn     net.Conn
	Timeout  time.Duration
}

// Config struct for setting up SR201
type Config struct {
	IP       string
	Port     string
	Protocol string
	Relay    int
}

// NewSR201 initializes a new SR201 instance
func NewSR201(config Config) (*SR201, error) {
	conn, err := net.DialTimeout(config.Protocol, fmt.Sprintf("%s:%s", config.IP, config.Port), 5*time.Second)
	if err != nil {
		return nil, err
	}
	return &SR201{
		IP:       config.IP,
		Port:     config.Port,
		Protocol: config.Protocol,
		Relay:    config.Relay,
		Conn:     conn,
		Timeout:  5 * time.Second,
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
func (s *SR201) CloseRelay() error {
	command := fmt.Sprintf("1%d", s.Relay)
	_, err := s.Send(command)
	return err
}

// OpenRelay opens the specified relay
func (s *SR201) OpenRelay() error {
	command := fmt.Sprintf("2%d", s.Relay)
	_, err := s.Send(command)
	return err
}

// ExecuteAction performs the specified action on the relay
func (s *SR201) ExecuteAction(action string) error {
	switch action {
	case "status":
		status, err := s.CheckStatus()
		if err != nil {
			return fmt.Errorf("error checking status: %v", err)
		}
		fmt.Printf("Relay status: %s\n", status)

	case "open":
		if err := s.OpenRelay(); err != nil {
			return fmt.Errorf("error opening relay %d: %v", s.Relay, err)
		}
		fmt.Printf("Relay %d opened.\n", s.Relay)

	case "close":
		if err := s.CloseRelay(); err != nil {
			return fmt.Errorf("error closing relay %d: %v", s.Relay, err)
		}
		fmt.Printf("Relay %d closed.\n", s.Relay)

	default:
		return fmt.Errorf("unknown action: %s", action)
	}
	return nil
}
