#!/usr/bin/env python

import time, os
from datetime import datetime, date, time, timedelta
import pytz


now = datetime.now()

print("Time now is: " + str(now))

realnow = datetime.now()
print("RealTime now is: " + str(now))

intwo = now - timedelta(hours=2)
print("in two Time now is: " + str(intwo))

aftertwo = now + timedelta(hours=2)
print("after two Time now is: " + str(aftertwo))

now = pytz.utc.localize(now)
print("Pytz Time now is: " + str(intwo))

intwo = pytz.utc.localize(intwo)
print("Pytz in two Time now is: " + str(intwo))

aftertwo = pytz.utc.localize(aftertwo)
print("Pytz after two Time now is: " + str(aftertwo))
