#!/usr/bin/env python

import time, os, urllib, urllib2

__author__ = 'Runo'


class ThingSpeakClient:
    """ A class for sending to ThingSpeak calendar"""

    def __init__(self, url, apikey):
        self.url = url
        self.apikey = apikey
        self.debug = 1

    def send_data(self, temp):
        data = urllib.urlencode({'api_key': self.apikey, 'field1': temp})
        response = urllib2.urlopen(url=self.url, data=data)
        # print(response.read())
