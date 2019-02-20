

#!/usr/bin/env python

import time, os, urllib, urllib2

PERIOD = 60 # Seconds

BASE_URL = 'https://api.thingspeak.com/update.json'
KEY = '72LT0GVTHPYRSEA7'

def send_data(temp):
    data = urllib.urlencode({'api_key' : KEY, 'field1': temp})
    response = urllib2.urlopen(url=BASE_URL, data=data)
    print(response.read())

while True:
    temp = '-1'
    print("Test tilstand: " + str(temp))
    send_data(temp)
    time.sleep(PERIOD)

