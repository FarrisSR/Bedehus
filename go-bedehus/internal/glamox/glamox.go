package glamox

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"
)

const defaultAPI = "https://api-1.glamoxheating.com/client-api"

type Client struct {
	apiURL    string
	accountID string
	password  string
	roomName  string
	token     string
	roomID    int
	http      *http.Client
}

type Secrets struct {
	AccountID string
	Password  string
	APIURL    string
}

type Room struct {
	ID                int    `json:"id"`
	Name              string `json:"name"`
	Temperature       int    `json:"temperature"`
	TargetTemperature int    `json:"targetTemperature"`
}

func NewClient(baseDir, roomName, apiOverride string) (*Client, error) {
	secrets, err := LoadSecrets(baseDir, apiOverride)
	if err != nil {
		return nil, err
	}
	return &Client{
		apiURL:    secrets.APIURL,
		accountID: secrets.AccountID,
		password:  secrets.Password,
		roomName:  roomName,
		http:      &http.Client{Timeout: 20 * time.Second},
	}, nil
}

func LoadSecrets(baseDir, apiOverride string) (Secrets, error) {
	candidates := []string{
		filepath.Join(baseDir, "secrets.json"),
		filepath.Join(baseDir, "glamox", "secrets.json"),
	}
	for _, path := range candidates {
		data, err := os.ReadFile(path)
		if err != nil {
			continue
		}
		var raw map[string]any
		if err := json.Unmarshal(data, &raw); err != nil {
			return Secrets{}, fmt.Errorf("parse secrets.json: %w", err)
		}

		accountID := readString(raw, "ACCOUNT_ID")
		password := readString(raw, "API_PASSWORD")
		apiURL := readString(raw, "API_URL")

		if accountID == "" && password == "" {
			accountID = readString(raw, "GLAMOX_CLIENT_ID")
			password = readString(raw, "GLAMOX_CLIENT_SECRET")
			apiURL = readString(raw, "GLAMOX_API_URL")
		}

		if accountID == "" || password == "" {
			continue
		}

		if apiOverride != "" {
			apiURL = apiOverride
		}
		if apiURL == "" {
			apiURL = defaultAPI
		}

		return Secrets{
			AccountID: accountID,
			Password:  password,
			APIURL:    strings.TrimRight(apiURL, "/"),
		}, nil
	}
	return Secrets{}, errors.New("fant ingen secrets.json")
}

func readString(raw map[string]any, key string) string {
	if value, ok := raw[key]; ok {
		if str, ok := value.(string); ok {
			return str
		}
	}
	return ""
}

func (c *Client) ensureAuth() error {
	if c.token != "" {
		return nil
	}
	form := url.Values{}
	form.Set("grant_type", "password")
	form.Set("username", c.accountID)
	form.Set("password", c.password)

	req, err := http.NewRequest("POST", c.apiURL+"/auth/token", strings.NewReader(form.Encode()))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	resp, err := c.http.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("auth failed: %s", strings.TrimSpace(string(body)))
	}
	var payload struct {
		AccessToken string `json:"access_token"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return err
	}
	c.token = payload.AccessToken
	return nil
}

func (c *Client) listRooms() ([]Room, error) {
	if err := c.ensureAuth(); err != nil {
		return nil, err
	}
	req, err := http.NewRequest("GET", c.apiURL+"/rest/v1/content/", nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+c.token)

	resp, err := c.http.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("list rooms failed: %s", strings.TrimSpace(string(body)))
	}

	var payload struct {
		Rooms []Room `json:"rooms"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return nil, err
	}
	return payload.Rooms, nil
}

func (c *Client) ensureRoomID() error {
	if c.roomID != 0 {
		return nil
	}
	rooms, err := c.listRooms()
	if err != nil {
		return err
	}
	for _, room := range rooms {
		if room.Name == c.roomName {
			c.roomID = room.ID
			return nil
		}
	}
	return fmt.Errorf("fant ikke rom '%s' i Glamox-appen", c.roomName)
}

func (c *Client) GetRoomStatus() (map[string]any, error) {
	if err := c.ensureRoomID(); err != nil {
		return nil, err
	}
	rooms, err := c.listRooms()
	if err != nil {
		return nil, err
	}
	for _, room := range rooms {
		if room.ID == c.roomID {
			return map[string]any{
				"room":              room.Name,
				"id":                room.ID,
				"temperature":       float64(room.Temperature) / 100.0,
				"targetTemperature": float64(room.TargetTemperature) / 100.0,
			}, nil
		}
	}
	return nil, fmt.Errorf("room id %d ikke funnet", c.roomID)
}

func (c *Client) SetTemperature(value float64) (map[string]any, error) {
	if err := c.ensureRoomID(); err != nil {
		return nil, err
	}
	payload := map[string]any{
		"rooms": []map[string]any{{
			"id":                c.roomID,
			"targetTemperature": fmt.Sprintf("%d", int(value*100+0.5)),
		}},
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}

	req, err := http.NewRequest("POST", c.apiURL+"/rest/v1/control/", bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+c.token)
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.http.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		respBody, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("set temperature failed: %s", strings.TrimSpace(string(respBody)))
	}
	return map[string]any{"ok": true, "requested": payload}, nil
}
