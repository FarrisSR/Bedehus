package mill

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

type Controller struct {
	IP       string
	TempType string
	http     *http.Client
}

func New(ip, tempType string) *Controller {
	return &Controller{
		IP:       ip,
		TempType: tempType,
		http:     &http.Client{Timeout: 10 * time.Second},
	}
}

func (c *Controller) SetTemperature(value float64) (map[string]any, error) {
	url := fmt.Sprintf("http://%s/set-temperature", c.IP)
	payload := map[string]any{"type": c.TempType, "value": value}
	body, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}

	req, err := http.NewRequest("POST", url, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.http.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		b, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("mill set temperature failed: %s", string(b))
	}

	var out map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, err
	}
	return out, nil
}

func (c *Controller) GetControlStatus() (map[string]any, error) {
	url := fmt.Sprintf("http://%s/control-status", c.IP)
	resp, err := c.http.Get(url)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		b, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("mill status failed: %s", string(b))
	}

	var out map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, err
	}
	return out, nil
}
