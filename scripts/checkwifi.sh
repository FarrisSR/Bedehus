ping -c4 192.168.0.1 > /dev/null
 
if [ $? != 0 ] 
then
  logger "No network connection, restarting wlan0"
  /sbin/ifdown 'wlan0'
  sleep 5
  /sbin/ifup --force 'wlan0'
else
  logger "YES - local network connection!"
  ping -c4 81.93.163.115 > /dev/null
  if [ $? != 0 ] 
  then
    logger "NO INTERNET connection!"
  else
    logger "Jippi we've got INTERNET connection!"
  fi
fi
  #sudo /sbin/shutdown -r now
#fi

#autossh -M 5249 -N -i /home/pi/.ssh/id_rsa -f -R 2248:localhost:22 runo@brothers.forrisdahl.no &
#killall autossh
