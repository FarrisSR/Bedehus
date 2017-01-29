#!/usr/bin/env python
#
# GrovePi Example for using the Grove Relay (http://www.seeedstudio.com/wiki/Grove_-_Relay)
#
# The GrovePi connects the Raspberry Pi and Grove sensors.  You can learn more about GrovePi here:  http://www.dexterindustries.com/GrovePi
#
# Have a question about this example?  Ask on the forums here:  http://www.dexterindustries.com/forum/?forum=grovepi
#
# LICENSE:
# These files have been made available online through a [Creative Commons Attribution-ShareAlike 3.0](http://creativecommons.org/licenses/by-sa/3.0/) license.
#
# NOTE: Relay is normally open. LED will illuminate when closed and you will hear a definitive click sound
import time
import grovepi
import logging


class GroveRelayClient:
    """ A class for controling the GrovePiBoard"""
    # Connect the Grove Relay to digital port D4
    # SIG,NC,VCC,GND

    def __init__(self):
        self.logger = logging.getLogger('GroveRelayClient')
        self.logger.setLevel(logging.DEBUG)
        self.debug = 0

    @staticmethod
    def shouldpowerbeon(relay):
        grovepi.pinMode(relay,"OUTPUT")
        grovepi.digitalWrite(relay,1)
    @staticmethod
    def shouldpowerbeoff(relay):
        grovepi.pinMode(relay,"OUTPUT")
        grovepi.digitalWrite(relay,0)
    @staticmethod
    def powerstatus(relay):
        grovepi.digitalRead(relay)
