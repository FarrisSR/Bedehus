package state

import (
	"database/sql"
	"fmt"
	"time"

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
