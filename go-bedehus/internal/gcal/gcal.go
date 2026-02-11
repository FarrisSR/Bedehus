package gcal

import (
	"context"
	"time"

	"google.golang.org/api/calendar/v3"
	"google.golang.org/api/option"
)

func NewService(ctx context.Context, keyFile string, scopes []string) (*calendar.Service, error) {
	opts := []option.ClientOption{option.WithCredentialsFile(keyFile)}
	if len(scopes) > 0 {
		opts = append(opts, option.WithScopes(scopes...))
	}
	return calendar.NewService(ctx, opts...)
}

func EventsInWindow(service *calendar.Service, calendarID string, start, end time.Time) ([]*calendar.Event, error) {
	call := service.Events.List(calendarID).
		TimeMin(start.Format(time.RFC3339)).
		TimeMax(end.Format(time.RFC3339)).
		SingleEvents(true).
		OrderBy("startTime")
	resp, err := call.Do()
	if err != nil {
		return nil, err
	}
	return resp.Items, nil
}
