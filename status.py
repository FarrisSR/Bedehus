# -*- coding: UTF-8 -*-
from sr201.sr201class import Sr201


sr201 = Sr201('192.168.100.100')
sr201.do_status('status')
sr201.close()
