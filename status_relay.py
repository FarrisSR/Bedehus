#!/usr/bin/env python
#-*- coding: UTF-8 -*-
import logging
from grove_relay import GroveRelayClient
import urllib3
urllib3.disable_warnings()

__author__ = 'Cato'

relay = 4

mintemp = 17
leiemintemp = 20
maxtemp = 22

utleie = 0

poweron=GroveRelayClient

## Logging:
# set up logging to file - see previous section for more details
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                    datefmt='%m-%d %H:%M',
                    filename='/var/log/heatcalaneder.log',
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

logger.debug("DEBUG - Starting")

logger.debug("DEBUG - Conclusion: Power should be on - Utleie ")
print(poweron.powerstatus(relay))

logger.debug("DEBUG - Ending")

