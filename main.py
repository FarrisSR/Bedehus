# -*- coding: UTF-8 -*-
import logging
import logging.config
from Calendalyzer.BedehusTemperaturProgram import BedehusTemperaturProgram
from sr201.sr201class import Sr201
import time
import socket

class HostnameFilter(logging.Filter):
    hostname = socket.gethostname()

    def filter(self, record):
        record.hostname = self.hostname
        return True

status = ""
heaton = False
relaystatus = False

logging.config.fileConfig(fname='logging.config', disable_existing_loggers=True)
logger = logging.getLogger(__name__)
logger.addFilter(HostnameFilter())

try:
     sr201 = Sr201('192.168.100.100')

     status = sr201.do_return_status('status')
     #print(type(int(status)))
     logger.debug('Current status')
     logger.debug(str(status[0]))
     sr201.close()
     relaystatus = bool(int(status))
except:
     logger.error("Unable to connect to SR201 relay, exiting program")
     exit()

try:
    program = BedehusTemperaturProgram()
    heaton = program.start()
except:
     logger.error("Unable to connect to get Calendar, exiting program")
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
