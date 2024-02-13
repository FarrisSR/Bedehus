import os
import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
<<<<<<< HEAD
from sr201.sr201class import Sr201
from loguru import logger
=======
>>>>>>> origin/master
import time

# Path to the service account JSON key file
key_file = 'service-account-key.json'

# Scopes for the Google Calendar API
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']


def main():
<<<<<<< HEAD
    status = ""
    heaton = False
    relaystatus = False
    logger.add("BedehusTemperaturProgram.log")
    logger.add(file_{time}.log, rotation="1 day", retention="30 days", compression="gz")
    logger.info("Bedehusets temperatur Script is starting")

    #Check connectivity to SR-201
    try:
        sr201 = Sr201('192.168.100.100')
        status = sr201.do_return_status('status')
        logger.debug('Current status')
        logger.debug(str(status[0]))
        # print(type(int(status)))
        sr201.close()
        relaystatus = bool(int(status))
    except:
        logger.error("Unable to connect to SR201 relay, exiting program")
        exit()


    #Able to get Calendar or not?
    try:
        # Create a credentials object
        credentials = service_account.Credentials.from_service_account_file(
            key_file, scopes=SCOPES)

        # Create a service object for the Google Calendar API
        service = build('calendar', 'v3', credentials=credentials)

        # Get the current time
        current_time = datetime.datetime.utcnow()

        # Calculate the start and end times for the next two hours
        time_window_start = current_time
        time_window_end = current_time + datetime.timedelta(hours=2)

        # Call the Calendar API to retrieve events within the time window
        events_result = service.events().list(
            calendarId='84ansm753q4ru2mjc9952nel7g@group.calendar.google.com', timeMin=time_window_start.isoformat() + 'Z',
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

                print(start, event['summary'])
                logger.info("Found event start: " + start + "Summary: " + summary)
                logger.info("Heat is set to True")
                heaton = True
        else:
            # No events within the time window, turn off the relay
            #sr201-off
            print('Relay turned OFF (no upcoming events)')
            logger.info('Heat is set to False (no upcoming events)')
            heaton = False

    except:
        logger.error("Unable to connect to SR201 relay, exiting program")
        exit()

    if heaton:
        if relaystatus:
            logger.info("I'm HOT. The heat is on!")
        else:
            logger.info("I'm heating up. Event starting")
            sr201 = Sr201('192.168.100.100')
            sr201.do_close('close:1')
            time.sleep(5)
            sr201.do_open('open:1')
            time.sleep(5)
            sr201.do_close('close:1')
            time.sleep(5)
            sr201.do_open('open:1')
            time.sleep(5)
            sr201.do_close('close:1')
            sr201.close()
    else:
        if relaystatus:
            logger.info("I'm Cooling off. Event ended")
            sr201 = Sr201('192.168.100.100')
            sr201.do_open('open:1')
            time.sleep(5)
            sr201.do_close('close:1')
            time.sleep(5)
            sr201.do_open('open:1')
            sr201.close()
        else:
            logger.info("I'm Cold. Comfort heat is off.")


if __name__ == '__main__':
    main()
=======

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

>>>>>>> origin/master
