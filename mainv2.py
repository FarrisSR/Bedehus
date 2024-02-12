import os
import datetime
import time
from google.oauth2 import service_account
from googleapiclient.discovery import build
from sr201.sr201class import Sr201
from mock_sr201class import MockSr201  # Import the mock class
import logging
from logging.handlers import SysLogHandler

# Configuration variables
USE_MOCK_SR201 = True  # Set to False when using real SR201
KEY_FILE = 'service-account-key.json'
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
SR201_IP = '192.168.100.100'
CALENDAR_ID = '84ansm753q4ru2mjc9952nel7g@group.calendar.google.com'
LOG_FILE = "BedehusTemperaturProgram.log"


def setup_logging():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    # File handler
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setLevel(logging.INFO)
    file_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(file_format)
    logger.addHandler(console_handler)

    # Syslog handler
    syslog_handler = SysLogHandler(address=('10.253.4.1', 5514))
    syslog_handler.setLevel(logging.INFO)
    syslog_format = logging.Formatter('%(asctime)s | %(levelname)s | %(name)s:%(funcName)s:%(lineno)d - %(message)s')
    syslog_handler.setFormatter(syslog_format)
    logger.addHandler(syslog_handler)

    return logger

def initialize():
    global logger
    logger = setup_logging()
    # Any other initialization code can go here
    # Change directory to the script's directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)


def setup_google_calendar_client():
    try:
        credentials = service_account.Credentials.from_service_account_file(
            KEY_FILE, scopes=SCOPES)
        service = build('calendar', 'v3', credentials=credentials)
        return service
    except Exception as e:
        logger.error(f"Error setting up Google Calendar client: {e}")
        raise


def get_calendar_events(service, start_time, end_time):
    try:
        events_result = service.events().list(
            calendarId=CALENDAR_ID, timeMin=start_time.isoformat() + 'Z',
            timeMax=end_time.isoformat() + 'Z', singleEvents=True,
            orderBy='startTime').execute()
        return events_result.get('items', [])
    except Exception as e:
        logger.error(f"Error retrieving calendar events: {e}")
        raise


def interact_with_sr201(action):
    # Choose between real or mock SR201 based on the USE_MOCK_SR201 variable
    sr201_class = MockSr201 if USE_MOCK_SR201 else Sr201
    try:
        sr201 = sr201_class(SR201_IP)
        if action == 'check_status':
            status = sr201.do_return_status('status')
            sr201.close()
            return bool(int(status))
        elif action in ['heat_on', 'heat_off']:
            sr201.do_close('close:1')
            time.sleep(5)
            sr201.do_open('open:1')
            time.sleep(5)
            sr201.do_close('close:1')
            sr201.close()
    except Exception as e:
        logger.error(f"Error interacting with SR201: {e}")
        raise


def process_events(events):
    heat_on = False
    if events:
        logger.info(f"Relay turned ON for upcoming events: {len(events)}")
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            summary = event.get('summary', 'No Summary Available')
            logger.info(f"Found event start: {start} Summary: {summary}")
        heat_on = True
    else:
        logger.info("Relay turned OFF (no upcoming events)")
    return heat_on


def main():
    try:
        initialize()
        # Setup Google Calendar client
        service = setup_google_calendar_client()

        # Define the time window for events
        current_time = datetime.datetime.utcnow()
        time_window_end = current_time + datetime.timedelta(hours=2)

        # Get calendar events
        events = get_calendar_events(service, current_time, time_window_end)

        # Process events and determine if heating is needed
        heat_on = process_events(events)

        # Check and update SR-201 relay status
        relay_status = interact_with_sr201('check_status')
        if heat_on:
            if not relay_status:
                logger.info("Turning heat on.")
                interact_with_sr201('heat_on')
        else:
            if relay_status:
                logger.info("Turning heat off.")
                interact_with_sr201('heat_off')

    except Exception as e:
        logger.error(f"Error in main: {e}")
        exit(1)


if __name__ == '__main__':
    main()
