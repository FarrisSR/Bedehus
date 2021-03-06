#!/usr/bin/env python
# -*- coding: UTF-8 -*-
import logging
#import time, os, urllib, urllib2
#import requests
from datetime import datetime, timedelta
import pytz
from Calendara import CalendarClient
from ThingSpeakClient.ThingSpeakClient import ThingSpeakClient
from sr201.sr201class import Sr201
import urllib3
urllib3.disable_warnings()

__author__ = 'Cato'

relay = 4

mintemp = 17
leiemintemp = 20
maxtemp = 22

utleie = 0

BASE_URL = 'https://api.thingspeak.com/update.json'
TSCKEY = '72LT0GVTHPYRSEA7'


tsc = ThingSpeakClient(BASE_URL,TSCKEY)


## Logging:
# set up logging to file - see previous section for more details
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                    datefmt='%m-%d %H:%M',
                    filename='heatcalaneder.log',
                    filemode='a')
# define a Handler which writes INFO messages or higher to the sys.stderr
console = logging.StreamHandler()
console.setLevel(logging.INFO)
# set a format which is simpler for console use
formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
# tell the handler to use this format
console.setFormatter(formatter)
# add the handler to the root logger
logging.getLogger('').addHandler(console)

logger = logging.getLogger("Calendar")
logger.setLevel(logging.DEBUG)

logger.debug("Starting")

calendarUrls = [
    # 1.etg-detaljer:
    'https://www.google.com/calendar/ical/84ansm753q4ru2mjc9952nel7g%40group.calendar.google.com/public/basic.ics',
    # Bønnerom-detaljer
    #'https://www.google.com/calendar/ical/sivrsgorvkkohp6ofe7p65j4o0%40group.calendar.google.com/public/basic.ics',
    # Kjeller-detaljer
    #'https://www.google.com/calendar/ical/chgvav5nl87ue74dk270vnl1s8%40group.calendar.google.com/public/basic.ics',

]

#storsaltempurl = 'http://192.168.1.49/cgi-bin/temp.py'
#storsalurl = 'https://www.google.com/calendar/ical/84ansm753q4ru2mjc9952nel7g%40group.calendar.google.com/public/basic.ics'
storsalurl = 'https://calendar.google.com/calendar/ical/84ansm753q4ru2mjc9952nel7g%40group.calendar.google.com/public/basic.ics'

shouldPowerBeOff = True  # Will try to prove this to be false by looking at the configured calendars
shouldPowerBeOffinFuture = True  # Will try to prove this to be false by looking at the configured calendars


now = datetime.now()
realnow = datetime.now() 
intwo = now - timedelta(hours=2)
aftertwo = now + timedelta(hours=2)
now = pytz.utc.localize(now)
intwo = pytz.utc.localize(intwo)
aftertwo = pytz.utc.localize(aftertwo)
logger.debug("Time NOW: " +str(now) + "Time in TWO: " + str(intwo))
logger.debug("Time REAL-NOW: " +str(realnow))


#for calendarUrl in calendarUrls:
calendarClient = CalendarClient(storsalurl)
if calendarClient.shouldPowerBeOn(now,intwo,aftertwo):
    shouldPowerBeOff = False

if shouldPowerBeOff:
    logger.debug("Conclusion: Power should be off" + str(shouldPowerBeOff))
else:
    logger.debug("Conclusion: Power should be on" + str(shouldPowerBeOff))
    utleie = 1

sr201 = Sr201('192.168.1.100')

if utleie:

    logger.debug("Conclusion: Power should be on - Utleie ")
    sr201.do_close('close:1')
    sr201.close()
    #tsc.send_data(utleie)
else:
    #logger.debug("Conclusion: Power should be on - Forced utleie")
    sr201.do_open('open:1')
    sr201.close()
    logger.debug("Conclusion: Power should be off - Ingenleie")
    #tsc.send_data(utleie)

