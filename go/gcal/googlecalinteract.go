package main

import (
	"context"
	"log"
	"log/syslog"
	"os"
	"time"

	"golang.org/x/oauth2/google"
	"google.golang.org/api/calendar/v3"
	"google.golang.org/api/option"
)

func setupSyslogClient(syslogprotocol string, raddr string, priority syslog.Priority, tag string) (*syslog.Writer, error) {
	sysLog, err := syslog.Dial(syslogprotocol, raddr, priority, tag)
	if err != nil {
		log.Fatal(err)
	}
	return sysLog, nil
}
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

	sysLog, err := setupSyslogClient("udp", "10.253.4.1:5515", syslog.LOG_DAEMON, "GoHeater")
	if err != nil {
		log.Fatalf("Error setting up SysLog client: %v", err)
	}

	sysLog.Warning("Start of script")
	// Example usage
	calendarID := "84ansm753q4ru2mjc9952nel7g@group.calendar.google.com"
	// Set a specific date and time
	specificTime := time.Date(2024, time.December, 17, 17, 30, 0, 0, time.UTC)
	Now := specificTime
	//Now := time.Now()
	timeMin := Now
	timeMax := Now.Add(48 * time.Hour) // Next 48 hours
	events, err := getCalendarEvents(service, calendarID, timeMin, timeMax)
	if err != nil {
		sysLog.Err("Error retrieving calendar events: %v" + err.Error())
	}

	for _, event := range events {
		sysLog.Warning("Event: " + event.Summary + " Start Time: " + event.Start.DateTime + "\n")
	}
	sysLog.Warning("End of script")
}
