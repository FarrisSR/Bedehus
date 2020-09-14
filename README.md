# Bedehus

Hi ALL!

This is my rPI project to control heat at our Bedehus.

I pull the calander from Google and turn on the heat if someone is renting it.

For this project I have a Raspberry Pi (Running Rasbian) with the GrovePI HAT and a Grove-relay:

https://www.raspberrypi.org/

https://www.dexterindustries.com/GrovePi/get-started-with-the-grovepi/


* Have a look into requirements.txt. 

During development (whenever new requirements are added):

    pip freeze > requirements.txt 

When arriving to a new runtime location, install dependencies like this:

    pip install -r requirements.txt 

--
FarrisSR & Vaskeball
