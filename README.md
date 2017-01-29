# Bedehus

Hi ALL!

This is my rPI project to control heat at our Bedehus.

I pull the calander from Google and turn on the heat if someone is renting it.

For this project I have a rPI with the GrovePI HAT and a Grove-relay:

# Update and upgrade Rasbian
  sudo apt update
  sudo apt upgrade

# Install req packages
  sudo apt install autossh
  sudo apt install aptitude
  sudo apt install links2
  sudo apt install git
  sudo apt install python-openssl
  sudo apt install tcpdump
  sudo apt install flock
  sudo apt install autossh
  sudo apt install python-requests
  sudo apt install python-pip
  sudo apt install python-icalendar
  sudo apt install -y python-pip python-dev build-essential libffi-dev libssl-dev

# Download GrovePi Library
  git clone https://github.com/DexterInd/GrovePi
  cd GrovePi/
  chmod +x install.sh
  sudo ./install.sh

# Pip Install packages for Python
  sudo pip install -U pip
  sudo pip install requests_cache
  sudo apt install python-urllib3
  sudo pip install logging
  sudo pip install certifi
  sudo pip install requests
  sudo pip install requests
  sudo pip install cryptography
  sudo pip install pytz
  sudo apt-get install python3-pip
  sudo pip install --upgrade urllib3
  sudo pip install --upgrade requests
  sudo pip install --upgrade requests_cache
  sudo pip install --upgrade requests


--
FarrisSR
