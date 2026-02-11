package logging

import (
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"
)

type Level int

const (
	LevelDebug Level = iota
	LevelInfo
	LevelError
)

func ParseLevel(raw string) (Level, error) {
	switch strings.ToUpper(strings.TrimSpace(raw)) {
	case "DEBUG":
		return LevelDebug, nil
	case "INFO":
		return LevelInfo, nil
	case "ERROR":
		return LevelError, nil
	case "":
		return LevelInfo, nil
	default:
		return LevelInfo, fmt.Errorf("unknown level %q", raw)
	}
}

type Sink struct {
	MinLevel Level
	Writer   io.Writer
	Format   Formatter
}

type Entry struct {
	Time     time.Time
	Level    Level
	Message  string
	Name     string
	Hostname string
	FuncName string
	Line     int
}

type Formatter func(entry Entry) string

type Logger struct {
	name     string
	hostname string
	sinks    []Sink
	mu       sync.Mutex
}

func New(name string, hostname string, sinks []Sink) *Logger {
	return &Logger{name: name, hostname: hostname, sinks: sinks}
}

func (l *Logger) Debugf(format string, args ...any) {
	l.log(LevelDebug, fmt.Sprintf(format, args...))
}

func (l *Logger) Infof(format string, args ...any) {
	l.log(LevelInfo, fmt.Sprintf(format, args...))
}

func (l *Logger) Errorf(format string, args ...any) {
	l.log(LevelError, fmt.Sprintf(format, args...))
}

func (l *Logger) log(level Level, msg string) {
	entry := Entry{
		Time:     time.Now(),
		Level:    level,
		Message:  msg,
		Name:     l.name,
		Hostname: l.hostname,
	}

	if pc, _, line, ok := runtime.Caller(2); ok {
		fn := runtime.FuncForPC(pc)
		if fn != nil {
			entry.FuncName = shortFuncName(fn.Name())
		}
		entry.Line = line
	}

	l.mu.Lock()
	defer l.mu.Unlock()
	for _, sink := range l.sinks {
		if level < sink.MinLevel {
			continue
		}
		line := sink.Format(entry)
		_, _ = sink.Writer.Write([]byte(line))
	}
}

func LevelString(level Level) string {
	switch level {
	case LevelDebug:
		return "DEBUG"
	case LevelInfo:
		return "INFO"
	case LevelError:
		return "ERROR"
	default:
		return "INFO"
	}
}

func SimpleFormatter() Formatter {
	return func(entry Entry) string {
		ts := entry.Time.Format("2006-01-02 15:04:05,000")
		name := padRight(entry.Name, 12)
		level := padRight(LevelString(entry.Level), 8)
		return fmt.Sprintf("%s %s %s %s\n", ts, name, level, entry.Message)
	}
}

func SyslogFormatter() Formatter {
	return func(entry Entry) string {
		ts := entry.Time.Format("2006-01-02 15:04:05,000")
		level := LevelString(entry.Level)
		funcName := entry.FuncName
		if funcName == "" {
			funcName = "unknown"
		}
		return fmt.Sprintf("%s | %s | %s | %s:%s:%d - %s\n", ts, level, entry.Hostname, entry.Name, funcName, entry.Line, entry.Message)
	}
}

func padRight(value string, width int) string {
	if len(value) >= width {
		return value
	}
	return value + strings.Repeat(" ", width-len(value))
}

func shortFuncName(full string) string {
	if idx := strings.LastIndex(full, "."); idx != -1 {
		return full[idx+1:]
	}
	return full
}

type RotatingFileWriter struct {
	path        string
	maxBytes    int
	backupCount int
	mu          sync.Mutex
	file        *os.File
}

func NewRotatingFileWriter(path string, maxBytes int, backupCount int) (*RotatingFileWriter, error) {
	if path == "" {
		return nil, errors.New("file path required")
	}
	w := &RotatingFileWriter{path: path, maxBytes: maxBytes, backupCount: backupCount}
	if err := w.open(); err != nil {
		return nil, err
	}
	return w, nil
}

func (w *RotatingFileWriter) Write(p []byte) (int, error) {
	w.mu.Lock()
	defer w.mu.Unlock()

	if err := w.rotateIfNeeded(len(p)); err != nil {
		return 0, err
	}
	return w.file.Write(p)
}

func (w *RotatingFileWriter) Close() error {
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.file != nil {
		return w.file.Close()
	}
	return nil
}

func (w *RotatingFileWriter) open() error {
	if err := os.MkdirAll(filepath.Dir(w.path), 0o755); err != nil && filepath.Dir(w.path) != "." {
		return err
	}
	file, err := os.OpenFile(w.path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if err != nil {
		return err
	}
	w.file = file
	return nil
}

func (w *RotatingFileWriter) rotateIfNeeded(incoming int) error {
	if w.maxBytes <= 0 {
		return nil
	}
	info, err := os.Stat(w.path)
	if err != nil && !os.IsNotExist(err) {
		return err
	}
	currentSize := 0
	if info != nil {
		currentSize = int(info.Size())
	}
	if currentSize+incoming <= w.maxBytes {
		return nil
	}
	if w.file != nil {
		_ = w.file.Close()
		w.file = nil
	}

	if w.backupCount > 0 {
		for i := w.backupCount - 1; i >= 1; i-- {
			oldPath := fmt.Sprintf("%s.%d", w.path, i)
			newPath := fmt.Sprintf("%s.%d", w.path, i+1)
			_ = os.Rename(oldPath, newPath)
		}
		_ = os.Rename(w.path, fmt.Sprintf("%s.1", w.path))
	} else {
		_ = os.Remove(w.path)
	}

	return w.open()
}

type SyslogWriter struct {
	mu   sync.Mutex
	conn net.Conn
}

func NewSyslogWriter(address string) (*SyslogWriter, error) {
	if address == "" {
		return nil, errors.New("syslog address required")
	}
	conn, err := net.Dial("udp", address)
	if err != nil {
		return nil, err
	}
	return &SyslogWriter{conn: conn}, nil
}

func (w *SyslogWriter) Write(p []byte) (int, error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	return w.conn.Write(p)
}

func (w *SyslogWriter) Close() error {
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.conn != nil {
		return w.conn.Close()
	}
	return nil
}
