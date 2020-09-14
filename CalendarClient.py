# -*- coding: UTF-8 -*-
import logging
import requests
from datetime import datetime, date, time, timedelta
import requests_cache
import urllib3
urllib3.disable_warnings()
from icalendar import Calendar

__author__ = 'Cato'


# set up logging to file - see previous section for more details
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                    datefmt='%m-%d %H:%M',
                    filename='calendar.log',
                    filemode='a')
# define a Handler which writes INFO messages or higher to the sys.stderr
logger = logging.StreamHandler()
logger.setLevel(logging.INFO)
# set a format which is simpler for console use
formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
# tell the handler to use this format
logger.setFormatter(formatter)
# add the handler to the root logger
logging.getLogger('').addHandler(logger)

class CalendarClient:
    """ A class for fetching ICAL calendar"""

    def __init__(self, url):
        self.url = url
        self.logger = logging.getLogger('calendarClient')
        self.logger.setLevel(logging.DEBUG)
        self.debug = 0
        self.check = 0


    def fetchCalendar(self):
        self.logger.info("Will fetch calendar")
        requests_cache.install_cache('bedehus_cache', backend='sqlite', expire_after=7200)
        icalText = requests.get(self.url,verify=False).text
        return Calendar.from_ical(icalText)

    def checkEvent(self, event, time, in_two, after_two):
        #self.logger.debug(str(event))
        start = event['DTSTART'].dt
        end = event['DTEND'].dt
        summary = event['SUMMARY'].encode('utf-8')

        if start - timedelta(days=7) <= in_two <= start + timedelta(days=7):
            self.debug = 1
            self.check = 1
        else:
            self.debug = 0
            self.check = 0

        """
            Start: 2015-06-14 14:30:00+00:00 End: 2015-06-14 17:00:00+00:00
            time: 2015-05-10 16:30:00+00:00
        """
        if self.debug:
            self.logger.debug("###################################################") 
            self.logger.debug("Event:        " + str(summary) + " Start:" + str(start) + "Til --> " + str(end)) 
            self.logger.debug("Sjekker tiden NOW " + str(time) + " mot møtet med starttid:" + str(start))
            self.logger.debug("Sjekker tiden INTWO " + str(in_two) + " mot møtet med starttid:" + str(start))
            self.logger.debug("              " + str(start) + " --> " + str(end))
            self.logger.debug("###################################################") 

        # Is it in the future?
        # Is it in the near future?
        # Is it in the past?
        # But still not finished?
        if self.check:
            if end < time:
                if end > after_two:
                    if self.debug:
                        self.logger.info("Vi er under to timer etter møteslutt: ")
                    return True
                else:
                    if self.debug:
                        self.logger.debug("Vi er etter møteslutt: ")
                    return False

            if start > time:
                diff = start - time
                if self.debug:
                    self.logger.debug("Vi er før møtestart: " + str(diff))
                if start <= in_two:
                    if self.debug:
                        self.logger.debug("Vi er under to timer til møtestart: " + str(diff))
                    return True

            if start <= time:
                if self.debug:
                    self.logger.debug('Vi er etter møtestart')
                diff = time - start
                if end > time:
                    if self.debug:
                        self.logger.debug('Men er før møteslutt, noe som betyr: --> Møtet pågår!! : ' + str(summary))
                    # Keep the power on
                    return True
                else:
                    if self.debug:
                        self.logger.debug('Vi er også etter møteslutt med ' + str(diff))
                    return False  # Todo - not hardocde
            else:
                return False

    def shouldPowerBeOn(self, time, in_two,after_two):
        icalCalendar = self.fetchCalendar()
        self.logger.info("Ser i kalender: " + icalCalendar['X-WR-CALDESC'])
        for event in icalCalendar.walk('vevent'):
            shouldPowerBeOn = self.checkEvent(event, time, in_two, after_two)
            if shouldPowerBeOn == True:
                return True
        return False
