# -*- coding: UTF-8 -*-
import logging
import requests
import requests_cache
from icalendar import Calendar

__author__ = 'Cato'


class CalendarClient:
    """ A class for fetching ICAL calendar"""

    def __init__(self, url):
        self.url = url
        self.logger = logging.getLogger('calendarClient')

    def fetch_calendar(self):
        self.logger.info("Will fetch calendar")
        #requests_cache.install_cache('bedehus_cache', backend='sqlite', expire_after=7200)
        ical_text = requests.get(self.url, verify=True).text
        return Calendar.from_ical(ical_text)
