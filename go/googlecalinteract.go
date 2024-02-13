package main

import (
	"context"
	"log"
	"os"
    "time"

	"golang.org/x/oauth2/google"
	"google.golang.org/api/calendar/v3"
	"google.golang.org/api/option"
)

func setupGoogleCalendarClient() (*calendar.Service, error) {
	ctx := context.Background()

	// Load the service account key file
	serviceAccountKeyFile := os.Getenv("KEY_FILE")
	credentials, err := os.ReadFile(serviceAccountKeyFile)
	if err != nil {
		return nil, err
	}

	// Authenticate using the service account
	config, err := google.JWTConfigFromJSON(credentials, calendar.CalendarReadonlyScope)
	if err != nil {
		return nil, err
	}

	ts := config.TokenSource(ctx)

	// Create the Google Calendar service client
	service, err := calendar.NewService(ctx, option.WithTokenSource(ts))
	if err != nil {
		return nil, err
	}

	return service, nil
}

func getCalendarEvents(service *calendar.Service, calendarID string, timeMin, timeMax time.Time) ([]*calendar.Event, error) {
	eventsCall := service.Events.List(calendarID).
		TimeMin(timeMin.Format(time.RFC3339)).
		TimeMax(timeMax.Format(time.RFC3339)).
		SingleEvents(true).
		OrderBy("startTime")

	events, err := eventsCall.Do()
	if err != nil {
		return nil, err
	}

	return events.Items, nil
}

func main() {
	service, err := setupGoogleCalendarClient()
	if err != nil {
		log.Fatalf("Error setting up Google Calendar client: %v", err)
	}

	// Example usage
	calendarID := "84ansm753q4ru2mjc9952nel7g@group.calendar.google.com"
	timeMin := time.Now()
	timeMax := time.Now().Add(48 * time.Hour) // Next 48 hours
	events, err := getCalendarEvents(service, calendarID, timeMin, timeMax)
	if err != nil {
		log.Fatalf("Error retrieving calendar events: %v", err)
	}

	for _, event := range events {
		log.Printf("Event: %s, Start Time: %s\n", event.Summary, event.Start.DateTime)
	}
}

