package state

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"time"

	"google.golang.org/api/calendar/v3"
	_ "modernc.org/sqlite"
)

type Store struct {
	db *sql.DB
}

func Open(path string) (*Store, error) {
	if path == "" {
		return nil, fmt.Errorf("db path is required")
	}
	db, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, err
	}
	store := &Store{db: db}
	if err := store.init(); err != nil {
		_ = db.Close()
		return nil, err
	}
	return store, nil
}

func (s *Store) Close() error {
	if s.db != nil {
		return s.db.Close()
	}
	return nil
}

func (s *Store) init() error {
	_, err := s.db.Exec(`
		CREATE TABLE IF NOT EXISTS relay_state (
			id INTEGER PRIMARY KEY CHECK(id = 1),
			state INTEGER NOT NULL,
			updated_at TEXT NOT NULL
		)
	`)
	if err != nil {
		return err
	}

	_, err = s.db.Exec(`
		CREATE TABLE IF NOT EXISTS calendar_cache (
			calendar_id TEXT NOT NULL,
			window_start TEXT NOT NULL,
			window_end TEXT NOT NULL,
			fetched_at TEXT NOT NULL,
			events_json TEXT NOT NULL
		)
	`)
	if err != nil {
		return err
	}

	_, err = s.db.Exec(`
		CREATE INDEX IF NOT EXISTS idx_calendar_cache_lookup
		ON calendar_cache(calendar_id, fetched_at)
	`)
	return err
}

func (s *Store) GetRelayState() (bool, error) {
	row := s.db.QueryRow("SELECT state FROM relay_state WHERE id = 1")
	var state int
	if err := row.Scan(&state); err != nil {
		if err == sql.ErrNoRows {
			return false, nil
		}
		return false, err
	}
	return state != 0, nil
}

func (s *Store) SetRelayState(state bool) error {
	value := 0
	if state {
		value = 1
	}
	_, err := s.db.Exec(`
		INSERT INTO relay_state (id, state, updated_at)
		VALUES (1, ?, ?)
		ON CONFLICT(id) DO UPDATE SET state = excluded.state, updated_at = excluded.updated_at
	`, value, time.Now().UTC().Format(time.RFC3339))
	return err
}

func (s *Store) SaveCalendarCache(calendarID string, windowStart, windowEnd time.Time, events []*calendar.Event) error {
	payload, err := json.Marshal(events)
	if err != nil {
		return err
	}
	_, err = s.db.Exec(`
		INSERT INTO calendar_cache (calendar_id, window_start, window_end, fetched_at, events_json)
		VALUES (?, ?, ?, ?, ?)
	`,
		calendarID,
		windowStart.UTC().Format(time.RFC3339),
		windowEnd.UTC().Format(time.RFC3339),
		time.Now().UTC().Format(time.RFC3339),
		string(payload),
	)
	return err
}

func (s *Store) GetCachedEvents(calendarID string, windowStart time.Time, maxAge time.Duration) ([]*calendar.Event, bool, error) {
	cutoff := time.Now().UTC().Add(-maxAge).Format(time.RFC3339)
	row := s.db.QueryRow(`
		SELECT events_json
		FROM calendar_cache
		WHERE calendar_id = ?
		  AND fetched_at >= ?
		  AND window_end >= ?
		ORDER BY fetched_at DESC
		LIMIT 1
	`,
		calendarID,
		cutoff,
		windowStart.UTC().Format(time.RFC3339),
	)

	var payload string
	if err := row.Scan(&payload); err != nil {
		if err == sql.ErrNoRows {
			return nil, false, nil
		}
		return nil, false, err
	}

	var events []*calendar.Event
	if err := json.Unmarshal([]byte(payload), &events); err != nil {
		return nil, false, err
	}
	return events, true, nil
}
