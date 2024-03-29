#!/usr/bin/env python
# -*- coding: UTF-8 -*-
import logging
import logging.config
import socket

__author__ = 'Cato'

from Calendalyzer.CalendarAnalyzer import CalendarAnalyzer
from Calendalyzer.CalendarClient import CalendarClient

storsalurl = 'https://calendar.google.com/calendar/ical/84ansm753q4ru2mjc9952nel7g%40group.calendar.google.com/public/basic.ics'  # type: str

class HostnameFilter(logging.Filter):
    hostname = socket.gethostname()

    def filter(self, record):
        record.hostname = self.hostname
        return True


class BedehusTemperaturProgram:
    """ A class for being a dataprogram for Bedehuset """

    def __init__(self):
        self.configure_logging()
        self.logger = logging.getLogger(__name__)
        self.logger.addFilter(HostnameFilter())

    @staticmethod
    def configure_logging():
        logging.config.fileConfig(fname='logging.config', disable_existing_loggers=True)

    def start(self):
        #self.logger.info("Program starting")
        self.logger.debug("Program started")
        calendar_client = CalendarClient(storsalurl)  # type: object
        calendar = calendar_client.fetch_calendar()

        calendar_analyzer = CalendarAnalyzer()
        power_on = calendar_analyzer.should_power_be_on(calendar)

        if power_on:
            self.logger.info("Program ended. Powerstate on! " + str(power_on))
        else:
            self.logger.info("Program ended. Powerstate off! " + str(power_on))
        return power_on



def main():
    program = BedehusTemperaturProgram()
    program.start()




if __name__ == "__main__":
    main()
