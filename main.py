# -*- coding: UTF-8 -*-
from Calendalyzer.BedehusTemperaturProgram import BedehusTemperaturProgram
from sr201.sr201class import Sr201
import time

status = ""
heaton = False
relaystatus = False

try: 
     sr201 = Sr201('192.168.100.100')

     status = sr201.do_return_status('status')
     #print(type(int(status)))
     print('Current status')
     print(str(status[0]))
     sr201.close()
     relaystatus = bool(int(status))
except:
     print("Unable to connect to SR201 relay")
     exit()

try:
    program = BedehusTemperaturProgram()
    heaton = program.start()
except:
     print("Unable to connect to get Calendar")
     exit()

if heaton:
    if relaystatus:
        print("I'm HOT")
    else:
        print("I'm heating up")
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
        print("I'm Cooling off")
        sr201 = Sr201('192.168.100.100')
        sr201.do_open('open:1')
        time.sleep(5)
        sr201.do_close('close:1')
        time.sleep(5)
        sr201.do_open('open:1')
        sr201.close()
    else:
        print("I'm Cold")
