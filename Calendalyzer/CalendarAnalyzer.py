#!/usr/bin/env python
# -*- coding: UTF-8 -*-
import logging
import datetime, timedelta

import pytz as pytz
from icalendar import Calendar


class CalendarAnalyzer:
    """ A Class for analyzing Calendar Events And deciding if power should be on """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        naive_now = datetime.now()
        timezone = pytz.timezone("Europe/Oslo")
        self.now = timezone.localize(naive_now)

    def does_event_require_power(self, event):
        logger = self.logger
        logger.debug(str(event))
        meeting_end = event['DTEND'].dt
        meeting_start = event['DTSTART'].dt

        print ("Meeting_start: " + str(type(meeting_start)))
        print ("Self NOW: " + str(type(self.now)))
        if isinstance(meeting_start, datetime.date):
            now = self.now.date()
            self.now = now

        if meeting_start - timedelta(hours=2) <= self.now <= meeting_end + timedelta(hours=2):
            return True
        else:
            # Møtet starter om litt lenge
            return False

        #if self.has_meeting_ended(event):
        #    return False

        #if self.is_meeting_on(event):
        #    return True

        #if self.will_meeting_start_soon(event):
        #    return True

        # Møtet starter om litt lenge
        #return False

    def should_power_be_on(self, calendar: Calendar):
        """ It should be on if.. meeting is on - or if meeting starts in two hours or less """
        self.logger.info("Ser i kalender: " + calendar['X-WR-CALDESC'])
        for event in calendar.walk('vevent'):
            should_power_be_on = self.does_event_require_power(event)
            if should_power_be_on:
                return True
        return False

    def has_meeting_ended(self, event):
        meeting_end = event['DTEND'].dt
        if meeting_end < self.now:
            return True

    def is_meeting_on(self, event):
        meeting_start = event['DTSTART'].dt
        meeting_end = event['DTEND'].dt
        if meeting_end > self.now:
            if meeting_start <= self.now:
                return True

    def will_meeting_start_soon(self, event):
        meeting_start = event['DTSTART'].dt
        meeting_end = event['DTEND'].dt
        if meeting_end < self.now:
            if meeting_start - timedelta(hours=2) <= self.now:
                return True
