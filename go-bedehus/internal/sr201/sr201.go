package sr201

import (
	"fmt"
	"net"
	"strings"
	"time"
)

type Client struct {
	IP      string
	Port    int
	Relay   int
	Timeout time.Duration
}

func (c *Client) addr() string {
	return fmt.Sprintf("%s:%d", c.IP, c.Port)
}

func (c *Client) send(command string) (string, error) {
	conn, err := net.DialTimeout("tcp", c.addr(), c.Timeout)
	if err != nil {
		return "", err
	}
	defer conn.Close()

	if err := conn.SetDeadline(time.Now().Add(c.Timeout)); err != nil {
		return "", err
	}
	if _, err := conn.Write([]byte(command)); err != nil {
		return "", err
	}

	buf := make([]byte, 4096)
	n, err := conn.Read(buf)
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(string(buf[:n])), nil
}

func (c *Client) CheckStatus() (bool, error) {
	resp, err := c.send("00")
	if err != nil {
		return false, err
	}
	if len(resp) == 0 {
		return false, fmt.Errorf("empty status response")
	}
	return resp[0] == '1', nil
}

func (c *Client) CloseRelay() error {
	command := fmt.Sprintf("1%d", c.Relay)
	_, err := c.send(command)
	return err
}

func (c *Client) OpenRelay() error {
	command := fmt.Sprintf("2%d", c.Relay)
	_, err := c.send(command)
	return err
}
