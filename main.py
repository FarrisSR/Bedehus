# -*- coding: UTF-8 -*-
import logging
import requests
from datetime import datetime, timedelta
import pytz
from Calendalyzer.CalendarClient import CalendarClient
from grove_relay import GroveRelayClient
import urllib3

urllib3.disable_warnings()

__author__ = 'Cato'

relay = 4

mintemp = 17
leiemintemp = 20
maxtemp = 22

utleie = 0

poweron = GroveRelayClient

## Logging:
console = logging.StreamHandler()
console.setLevel(logging.DEBUG)
logging.getLogger('').addHandler(console)
logger = logging.getLogger("Calendar")
logger.setLevel(logging.DEBUG)

logger.debug("Starting")

calendarUrls = [
    # 1.etg-detaljer:
    'https://www.google.com/calendar/ical/84ansm753q4ru2mjc9952nel7g%40group.calendar.google.com/public/basic.ics',
    # Bønnerom-detaljer
    # 'https://www.google.com/calendar/ical/sivrsgorvkkohp6ofe7p65j4o0%40group.calendar.google.com/public/basic.ics',
    # Kjeller-detaljer
    # 'https://www.google.com/calendar/ical/chgvav5nl87ue74dk270vnl1s8%40group.calendar.google.com/public/basic.ics',

]

storsaltempurl = 'http://192.168.1.49/cgi-bin/temp.py'
storsalurl = 'https://www.google.com/calendar/ical/84ansm753q4ru2mjc9952nel7g%40group.calendar.google.com/public/basic.ics'

shouldPowerBeOff = True  # Will try to prove this to be false by looking at the configured calendars
shouldPowerBeOffinFuture = True  # Will try to prove this to be false by looking at the configured calendars

now = datetime.now()
intwo = now + timedelta(hours=2)
now = pytz.utc.localize(now)
intwo = pytz.utc.localize(intwo)
### START
# d = date(2015,5,10)
# t = time(16,30, 0, 0)
# now = datetime.combine(d, t)
# now = pytz.utc.localize(now)
### ^^ END
# for calendarUrl in calendarUrls:
calendarClient = CalendarClient(storsalurl)
if calendarClient.shouldPowerBeOn(now, intwo):
    shouldPowerBeOff = False
# if calendarClient.shouldPowerBeOn(intwo):
#    shouldPowerBeOffinFuture = False

if shouldPowerBeOff:
    logger.debug("Conclusion: Power should be off")
else:
    logger.debug("Conclusion: Power should be on")
    utleie = 1

temprequest = requests.get(storsaltempurl, verify=False)
rawtemp = int(str.strip(str(temprequest.text).split('=')[1]))

logger.debug("Temperaturen er:" + str(rawtemp) + " mintemp:" + str(mintemp) + " utleietemp:" + str(
    leiemintemp) + "maxtemp:" + str(maxtemp))

if utleie:
    mintemp = leiemintemp
    logger.debug("Conclusion: Utleie min temp set")
else:
    maxtemp = leiemintemp

if rawtemp <= mintemp:
    logger.debug("Conclusion: Power should be on - Lav Temperatur")
    poweron.shouldpowerbeon(relay)
elif rawtemp >= maxtemp:
    poweron.shouldpowerbeoff(relay)
    logger.debug("Conclusion: Power should be off - Høytemperatur")
