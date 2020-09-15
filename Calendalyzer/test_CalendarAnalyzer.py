import logging
import logging.config

import unittest
from datetime import datetime, timedelta

from icalendar import Calendar, Event

from Calendalyzer.CalendarAnalyzer import CalendarAnalyzer


class MyTestCase(unittest.TestCase):
    def test_meeting_too_long_in_future_aka_no_power(self):
        logging.config.fileConfig(fname='logging.config', disable_existing_loggers=True)

        event = Event()
        event.add('summary', "Et kort sammendrag")
        event.add('dtstart', datetime.now() + timedelta(hours=3))
        event.add('dtend', datetime.now() + timedelta(hours=4))
        event.add('description', 'Awsome Description')
        event.add('location', "Los Bedehusas")

        cal = Calendar()
        cal.add_component(component=event)
        cal.add('X-WR-CALDESC', "Testkalender")

        analyzer = CalendarAnalyzer()
        should_be_on = analyzer.should_power_be_on(cal)

        self.assertFalse(should_be_on)

    def test_meeting_ongoing_have_power(self):
        event = Event()
        event.add('summary', "Et kort sammendrag")
        event.add('dtstart', datetime.now() - timedelta(hours=5))
        event.add('dtend', datetime.now() + timedelta(hours=4))
        event.add('description', 'Awsome Description')
        event.add('location', "Los Bedehusas")

        cal = Calendar()
        cal.add_component(component=event)
        cal.add('X-WR-CALDESC', "Testkalender")

        analyzer = CalendarAnalyzer()
        should_be_on = analyzer.should_power_be_on(cal)

        self.assertTrue(should_be_on)

    def test_meeting_starts_soon_have_power(self):
        event = Event()
        event.add('summary', "Et kort sammendrag")
        event.add('dtstart', datetime.now() - timedelta(hours=1))
        event.add('dtend', datetime.now() + timedelta(hours=4))
        event.add('description', 'Awsome Description')
        event.add('location', "Los Bedehusas")

        cal = Calendar()
        cal.add_component(component=event)
        cal.add('X-WR-CALDESC', "Testkalender")

        analyzer = CalendarAnalyzer()
        should_be_on = analyzer.should_power_be_on(cal)

        self.assertTrue(should_be_on)

    def test_meeting_has_been_no_power(self):
        event = Event()
        event.add('summary', "Et kort sammendrag")
        event.add('dtstart', datetime.now() - timedelta(hours=4))
        event.add('dtend', datetime.now() - timedelta(hours=3))
        event.add('description', 'Awsome Description')
        event.add('location', "Los Bedehusas")

        cal = Calendar()
        cal.add_component(component=event)
        cal.add('X-WR-CALDESC', "Testkalender")

        analyzer = CalendarAnalyzer()
        should_be_on = analyzer.should_power_be_on(cal)

        self.assertFalse(should_be_on)


if __name__ == '__main__':
    unittest.main()
