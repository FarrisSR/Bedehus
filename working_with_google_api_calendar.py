import os
import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
import time

# Path to the service account JSON key file
key_file = 'service-account-key.json'

# Scopes for the Google Calendar API
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']


def main():

    # Create a credentials object
    credentials = service_account.Credentials.from_service_account_file(
        key_file, scopes=SCOPES)

    # Create a service object for the Google Calendar API
    service = build('calendar', 'v3', credentials=credentials)

    # Get the current time
    current_time = datetime.datetime.utcnow()

    # Calculate the start and end times for the next two hours
    time_window_start = current_time - datetime.timedelta(hours=2)
    time_window_end = current_time + datetime.timedelta(hours=2)

    # Call the Calendar API to retrieve events within the time window
    events_result = service.events().list(
        #calendarId='84ansm753q4ru2mjc9952nel7g@group.calendar.google.com', timeMin=time_window_start.isoformat() + 'Z',
        calendarId='forrisdahl.no_benv5nuse42vgk649seiient1o@group.calendar.google.com', timeMin=time_window_start.isoformat() + 'Z',
        timeMax=time_window_end.isoformat() + 'Z', singleEvents=True,
        orderBy='startTime').execute()
    events = events_result.get('items', [])

    # Check if there are any events within the time window
    if events:
        # There are events within the time window, turn on the relay
        #sr201-on
        print('Relay turned ON for upcoming events:')
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            try:
                summary = event['summary']
            except KeyError:
                summary = 'No Summary Available'

            print(start, summary)
    else:
        # No events within the time window, turn off the relay
        #sr201-off
        print('Relay turned OFF (no upcoming events)')

    #SR-201.close

if __name__ == '__main__':
    main()

