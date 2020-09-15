#!/usr/bin/env python

import time, os, urllib, urllib3

# PERIOD = 60 # Seconds

BASE_URL = 'https://api.thingspeak.com/update.json'
KEY = 'PR377EQ9CB1QO3YY'


def send_data(temp):
    data = urllib.urlencode({'api_key': KEY, 'field1': temp})
    response = urllib3.urlopen(url=BASE_URL, data=data)
    print(response.read())


def cpu_temp():
    dev = os.popen('/opt/vc/bin/vcgencmd measure_temp')
    cpu_temp = dev.read()[5:-3]  # type: str
    return cpu_temp


temp = cpu_temp()
print("CPU Temp (C): " + str(temp))
send_data(temp)
