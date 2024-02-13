#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Python dotenv"""
"""Argparse"""
"""Use Result module to help with expection handling"""
import logging
import datetime
from datetime import timedelta
"""Convert from pytz to pendulum?"""
"""Icecream for debugging"""
import pytz as pytz
from icalendar import Calendar


class CalendarAnalyzer:
    """ A Class for analyzing Calendar Events And deciding if power should be on """

    def __init__(self):
        nowtime = datetime.datetime
        self.logger = logging.getLogger(__name__)
        naive_now = nowtime.now()
        timezone = pytz.timezone("Europe/Oslo")
        self.initnow = timezone.localize(naive_now)
        #self.initnow = naive_now

        self.ztimenow = datetime.datetime.now()
        self.debug = False

    def does_event_require_power(self, event):
        logger = self.logger
        logger.debug(str(event))
        print("INITNOW" +str(self.initnow))
        print("ZNOW" + str(type(self.ztimenow)) + str(self.ztimenow))

        meeting_end = event['DTEND'].dt
        meeting_start = event['DTSTART'].dt
        self.now = self.initnow
        onlydate = False
        if self.debug:
            print ("Meeting_start: " + str(type(meeting_start)) + str(meeting_start))
            print ("Meeting_start-minus2: " + str(type(meeting_start - timedelta(hours=2))))
            print ("Meeting_end: " + str(type(meeting_end)) + str(meeting_end))
            print ("Self NOW: " + str(type(self.now)) + str(self.now))
        if isinstance(meeting_start, datetime.datetime):
            #Is meeting_start a datetime.datetime object
            Checkthis = True
        elif isinstance(meeting_start, datetime.date):
            #Is meeting_start a datetime.date object
            if self.debug:
                print ("Meeting_start: " + str(type(meeting_start)) + str(meeting_start))

            self.now = datetime.datetime.now().date()

            if self.debug:
                print ("Self NOW: " + str(type(self.now)) + str(self.now))
            onlydate = True
        else:
            logger.debug(str(event))
            logger.debug("Meeting_start: " + str(type(meeting_start)) + str(meeting_start))
            return False

        if onlydate:
            if meeting_start <= self.now <= meeting_end :
                return True
            else:
                # Møtet starter om litt lenge
                return False
        else:
            if meeting_start - timedelta(hours=2) <= self.now <= meeting_end + timedelta(hours=2):
                return True
            else:
                # Møtet starter om litt lenge
                return False


    def should_power_be_on(self, calendar: Calendar):
        """ It should be on if.. meeting is on - or if meeting starts in two hours or less """
        self.logger.info("Ser i kalender: " + calendar['X-WR-CALDESC'])
        for event in calendar.walk('vevent'):
            should_power_be_on = self.does_event_require_power(event)
            if should_power_be_on:
                return True
        return False
