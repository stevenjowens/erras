ERRAS stands for Experimental RFID Reader Activation System

"Erras" also, coincidentally, is the second-person singular past
historic form of the french word "errer", meaning "to wander about"
(the same root word from which we get "errant", as in
"knight-errant").

There is no relationship whatsoever between these two facts.

# Installation Instructions

Note, this assumes a raspbian environment, which has certain libraries installed by default.

So far this consists of five files:

members.csv contains member data

erras_members.py downloads members.csv
erras_rfid_reader.py reads members.csv and the RFID reader

Also two systemd unit files to set up automatically starting the python scripts on bootup:

erras_members.service
erras_rfid_reader.service

To install the system:

$ scp erras_members.py pi@raspberrypi:/home/pi
$ scp erras_rfid_reader.py pi@raspberrypi:/home/pi
$ scp erras.ini pi@raspberrypi:/home/pi

To set up the systemd stuff requires copying the files into root-owned directories, so you'll
have to two-step it:

$ scp erras_rfid_reader.service pi@raspberrypi:/home/pi
$ scp erras_members.service pi@raspberrypi:/home/pi

Then ssh into the raspberripi and:

$ sudo mv erras_rfid_reader.service /lib/systemd/system/erras_rfid_reader.service 
$ sudo mv erras_members.service /lib/systemd/system/erras_members.service

$ sudo chmod 644 /lib/systemd/system/erras_rfid_reader.service   
$ sudo chmod 644 /lib/systemd/system/erras_members.service

$ sudo systemctl daemon-reload

$ sudo systemctl enable erras_rfid_reader.service
Created symlink /etc/systemd/system/multi-user.target.wants/door_rfid_reader.service → /lib/systemd/system/erras_rfid_reader.service.
$ sudo systemctl enable erras_members.service
Created symlink /etc/systemd/system/multi-user.target.wants/erras_members.service → /lib/systemd/system/erras_members.service.

This should suffice to start the new services:

$ sudo systemctl start erras_rfid_reader.service
$ sudo systemctl start erras_members.service

But if it doesn't, just reboot the pi:

$ sudo reboot

# Debugging

For debugging purposes, you can stop the scripts with:

$ sudo systemctl stop erras_members.service
$ sudo systemctl stop erras_rfid_reader.service

And then manually run the scripts.  Make sure you use python3.

$ python3 erras_members.py
$ python3 erras_readers.py

# Background/Troubleshooting/How It Works

For specific details on the hardware, see the hardware.md, but broadly speaking, the ERRAS system is comprised of:

- a wildapricot database (see below)
- an RFID reader, optionally with a keypad for manual entry
- an arduino that reads from the RFID reader
- a raspberry pi that reads serial from the arduino
- erras.ini, a config file
- two programs on the raspberry pi:
-- erras_members.py, downloads member data from wildapricot
-- erras_rfid_reader.py, loads data and responds to RFID reader
-- an electriconic device to activate (relay, electric lock, etc)

Note: This high-level description will not include configuration variable names.

The arduino implements the weigand protocol and sends any values received over the serial port to erras_rfid_reader.py, as ASCII.  The arduino prefixs the value with an R to indicate it's from the RFID reader, or K to indicate it's from the Keypad.  The arduino begins the value with ASCII_STX and ends with ASCII_ETX.  

The wildapricot database must contain one or more custom fields that contain RFID values or keypad codes.  Erras supports multiple field names, comma-separated.

Note that these values are treated throughout the system as strings, they are not parsed as ints for comparison purposes, etc.

erras_members.py downloads the member data, including the custom fields, and saves it as a csv file.  It also saves each CSV download in a backup timestamped file, pruning older files.  Then it sleeps for a period (default is 500 seconds), then downloads a fresh copy.

erras_rfid_reader.py starts up, reads and parses the CSV file, then goes into an infinite loop reading from the arduino serial port.  

Each time erras_rfid_reader.py loops, it checks the file modification date of the CSV file and reloads it if it is changed.  This means that if new member data is added to wildapricot, you must a) wait long enough for erras_members.py to download it, then b) swipe the RFID reader or enter a keypad code to get erras_rfid_reader.py to loop so it checks the file modification date.

If erras_rfid_reader.py receives a value from the serial port, it checks for an R (for RFID) or K (for keypad) prefix. It ignores any value that doesn't have a prefix.

If erras_rfid_reader.py receives a value with an R or K prefix, it checks against its in memory copy of the member data, in the appropriate field for RFID values or keypad codes.  If it finds a match, it activates the appropriate hardware.

Note: Work is in progress to add support for boolean flag fields for activating specific systems.

# Systemd Cheat Sheet

To list all systemctl services:

$ systemctl list-unit-files

$ systemctl status errsa_rfid_reader

When troubleshooting, also check journalctl for more complete logging information.

Try this combo:

$ systemctl start myservice && journalctl -fu

To see the current status of the services:

$ sudo systemctl status door_rfid_reader.service
$ sudo systemctl status door_database.service

$ sudo systemctl status erras_rfid_reader.service
$ sudo systemctl status erras_members.service

To switch from the erras version back to the old version,
first disable the erras version:

$ sudo systemctl disable erras_rfid_reader.service
$ sudo systemctl disable erras_members.service

Then enable the old version:

$ sudo systemctl enable door_rfid_reader.service
$ sudo systemctl enable door_database.service

Then either reboot the rpi, or start the old version:

$ sudo systemctl start door_rfid_reader.service
$ sudo systemctl start door_database.service

Check the status on the old version with:

$ sudo systemctl status erras_rfid_reader.service
$ sudo systemctl status erras_members.service

In the event a service failed to start, for more complete log info, use journalctl:

$ sudo journalctl -fu
