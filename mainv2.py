import os
import socket
import datetime
import time
from google.oauth2 import service_account
from googleapiclient.discovery import build
from mill_controller.mill_controller import mill_controller
from sr201.sr201class import Sr201
from mock_sr201class import MockSr201  # Import the mock class
import logging
import logging.config
from logging.handlers import SysLogHandler

# Configuration variables
USE_MOCK_SR201 = False  # Set to False when using real SR201
KEY_FILE = 'service-account-key.json'
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
SR201_IP = '192.168.100.100'
CALENDAR_ID = '84ansm753q4ru2mjc9952nel7g@group.calendar.google.com'
PRAY_ID = 'sivrsgorvkkohp6ofe7p65j4o0@group.calendar.google.com'
LOG_FILE = "BedehusTemperaturProgram.log"
RELAY_STATE_FILE = 'relay_state.txt'
MILL_IP_ADDRESS = "192.168.0.173"
MILL_TEMP_TYPE = "Normal"


class HostnameFilter(logging.Filter):
    hostname = socket.gethostname()

    def filter(self, record):
        record.hostname = self.hostname
        return True


def setup_logging():
    logging.config.fileConfig(fname='logging.config',
                              disable_existing_loggers=False)
    logger = logging.getLogger(__name__)

    return logger


def initialize():
    global logger
    logger = setup_logging()
    logger.setLevel(logging.INFO)
    logger.addFilter(HostnameFilter())
    # Any other initialization code can go here
    # Change directory to the script's directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)


def setup_google_calendar_client():
    try:
        credentials = service_account.Credentials.from_service_account_file(
            KEY_FILE, scopes=SCOPES)
        service = build('calendar', 'v3',
                        credentials=credentials, cache_discovery=False)
        return service
    except Exception as e:
        logger.error(f"Error setting up Google Calendar client: {e}")
        raise


def get_calendar_events(calendar, service, start_time, end_time):
    try:
        events_result = service.events().list(
            calendarId=calendar, timeMin=start_time.isoformat() + 'Z',
            timeMax=end_time.isoformat() + 'Z', singleEvents=True,
            orderBy='startTime').execute()
        return events_result.get('items', [])
    except Exception as e:
        logger.error(f"Error retrieving calendar events: {e}")
        raise


def string_to_bool(relay_state_read_from_file: str):
    """
    This function takes a string representing a boolean value read from a file
    and converts it to a corresponding boolean value.

    Args:
        relay_state_read_from_file (str): The string read from the file representing a boolean value.

    Returns:
        bool: The boolean value corresponding to the input string. Returns False if the input string is not 'True'.

    Example:
        string_to_bool("True") -> True
        string_to_bool("False") -> False
        string_to_bool("Invalid") -> False
    """
    return {"True": True, "False": False}.get(relay_state_read_from_file, False)


def save_relay_state(state: bool):
    # assert state in ["True", "False"], "Input must be 'True' or 'False'"
    # Input validation replaced assert with an explicit check
    # if state not in ["True", "False"]:
    #    # Raising an exception for invalid input
    #    # raise ValueError("Input must be 'True' or 'False'")

    try:
        with open(RELAY_STATE_FILE, 'w') as file:
            file.write(str(state))
    except Exception as e:
        logger.error(f"Error saving relay state: {e}")


def read_relay_state():
    try:
        with open(RELAY_STATE_FILE, 'r') as file:
            return string_to_bool(file.read().strip())
    except FileNotFoundError:
        # Log that the state file does not exist; this is expected on the first run
        logger.info("Relay state file not found. Assuming state is unknown.")
        return False
    except Exception as e:
        # Log any other exceptions that occur while reading the file
        logger.error(f"Error reading relay state: {e}")
        return False


def interact_with_sr201(action: str):
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
            if action == 'heat_off':
                time.sleep(5)
                sr201.do_open('open:1')
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


# Define a function to check and interact with the SR201 device based on the heat_on parameter
def check_relay_state(heat_on: bool):
    # Get the last state of the relay
    last_state = read_relay_state()
    # Log the last state
    logger.info("Last state: " + str(last_state))
    # Get the current relay status by interacting with the SR201 device
    relay_status = interact_with_sr201('check_status')
    # Save the current relay status
    save_relay_state(heat_on)

    heat_logic(heat_on, last_state, relay_status)


def heat_logic(heat_on: bool, last_state: bool, relay_status: bool):
    # Check if there is a change in the heat_on parameter compared to the last state
    if heat_on != last_state:
        logger.info("Change of state detected")
    # Check if heat is supposed to be on
    if heat_on:
        # If the relay status is off, turn the heat on
        if not relay_status:
            logger.info("Turning heat on.")
            interact_with_sr201('heat_on')
        else:
            logger.info("Relay is already on, not turning heat on.")
    else:
        # If the relay status is on, turn the heat off
        if relay_status:
            logger.info("Turning heat off.")
            interact_with_sr201('heat_off')
        else:
            logger.info("Relay is already off, not turning heat off.")


def check_update_pray(pray_heat_on):
    try:
        controller = mill_controller(
            ip_address=MILL_IP_ADDRESS, temp_type=MILL_TEMP_TYPE)
        if pray_heat_on:
            logger.info("Set PRAY heat to 21C.")
            result = controller.set_temperature(21)
            logger.debug(str(controller.get_control_status()))
        else:
            logger.info("Set PRAY heat to 17C.")
            result = controller.set_temperature(17)
            logger.debug(str(controller.get_control_status()))

        logger.info("PRAY" + str(result))
    except Exception as e:
        # Log an error message indicating an exception occurred in the main function
        logger.error(f"Error interacting with PRAY: {e}")
        raise


def main():
    try:
        initialize()
        # Setup Google Calendar client
        service = setup_google_calendar_client()

        # Define the time window for events
        current_time = datetime.datetime.utcnow()
        time_window_end = current_time + datetime.timedelta(hours=2)

        # Storsalen
        # Get calendar events
        events = get_calendar_events(
            CALENDAR_ID, service, current_time, time_window_end)

        # Process events and determine if heating is needed
        heat_on = process_events(events)

        # Check and update SR-201 relay status
        check_relay_state(heat_on)

        # Bønnerom
        # Get calendar events
        events = get_calendar_events(
            PRAY_ID, service, current_time, time_window_end)

        # Process events and determine if heating is needed
        pray_heat_on = process_events(events)

        # Check and update SR-201 relay status
        check_update_pray(pray_heat_on)

    except Exception as e:
        # Log an error message indicating an exception occurred in the main function
        logger.error(f"Error in main: {e}")
        # Exit the program with an exit code of 1
        exit(1)


if __name__ == '__main__':
    main()
