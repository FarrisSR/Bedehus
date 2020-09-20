# -*- coding: UTF-8 -*-
from Calendalyzer.BedehusTemperaturProgram import BedehusTemperaturProgram
from sr201.sr201class import Sr201


program = BedehusTemperaturProgram()
if program.start():
    sr201 = Sr201('192.168.1.100')
    sr201.do_close('close:1')
    sr201.close()
else:
    sr201 = Sr201('192.168.1.100')
    sr201.do_open('open:1')
    sr201.close()

