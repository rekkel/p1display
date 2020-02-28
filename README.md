# P1 Display

The P1 Display is a python based application which turns your Raspberry Pi Touchscreen into a DSMR4/SMR5 smart meter P1 reader. The unique EAN of the smart meter is displayed, the current per phase and the message field.
When the message field contains congestion data in the following format 'EAN;I1+;I2+;I3+;I1-;I2-;I3-', it will be parsed and displayed in the congestion fields. This additional fields will display the desired maximum import or export current per phase.  

The charge indicator will turn blue when the congestion signal values are empty, for example:  
EAN0000000000000;;;;;;

The charge indicator will turn purple when the congestion signal is present and one or more values are not empty, for example:  
EAN0000000000000;;20;;;;5

Optional, the smart meter measurements and the congestion signal is sent to a firebase database for monitoring and visualisation. If you prefer to work without this feature, the `P1plus_display_offline.py` version can be used instead.

## Installation

Most Linux OS's have python3 installed by default. If not, install it. 
Make sure the following files are in the same directory: P1plus_display.py and smartmetericon.png
They all should be readable and the python files should be executable for all user levels.

Make sure the desktop icon is at the desired desktop to start the application: ~/Desktop/P1Display.desktop

On your Linux system, open: File manager --> Edit --> Preferences --> General  
- Check: Open files with single click
- Check: Do not ask option on executable launch

Install Neopixel library:
`sudo pip3 install rpi_ws281x adafruit-circuitpython-neopixel`  

Install firebase:
`sudo pip3 install --upgrade firebase-admin`  

Add firebase certificate: `/home/pi/P1plus_display/peakshaving-2ab48-firebase-adminsdk-zrzq6-4fe5809bbe.json`  

Now the program can be successfully started by ticking the desktop icon.

## Mandatory hardware

The application reads serial data from a P1 to USB cable, connected to the Raspberry Pi and the smart meter.
# p1display
