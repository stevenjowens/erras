# ERRAS

ERRAS stands for Experimental RFID Reader Activation System

"Erras" also, coincidentally, is the second-person singular past
historic form of the french word "*errer*", meaning "to wander about"
(the same root word from which we get "errant", as in
"knight-errant").

I asked a French-speaking friend and they said they're no expert, but
they think *"tu erras"* translates as "you wandered":

'Par example, la phrase, *"tu arras dans la campagne"* veut dire en Anglais, "you wandered around the countryside".'

There is no relationship whatsoever between these two facts.

## Preparing the RaspberryPi

Disable login over serial, enable serial port hardware

Run raspi-config, select:

Interfacing Options/Serial/Disable shell and kernel messages on the serial connection

Select disable for login over serial.
Select enable for serial port hardware.
Reboot.

Log back in.

Various sources say I need to put “enable_uart=1” in config.txt on the
boot partition to get bluetooth to let go of the serial port but still
have the serial port enabled.  However, other sources say that doing
the raspi-config commands above should be sufficient, and indeed that
seems to work.

Erras depends on pyserial, and to install pyserial on raspberrypi you'll need pip3, which does not come bundled with python, so:

```
$ sudo apt-get update && sudo apt-get install python3-pip
$ sudo pip3 install pyserial
$ sudo pip3 install RPi.GPIO
```

## A Note About Door Lock GPIO Values

Note that this code was written to work with an electronic door lick that wants:

GPIO 23 = TRUE on init, to lock the door
GPIO 23 = FALSE to unlock the door
wait 6 seconds to allow entry
GPIO 23 = TRUE again to re-lock the door

However, some versious of electronic door lock hardware need the opposite values, FALSE to loc the door, TRUE to unlock the door.

Currently the only option is to edit the code to fix this. Need to move that out to the .ini file.

## Installation Instructions

Note, this assumes a raspbian environment, which has certain libraries installed by default.

This also assumes you've configured the raspberrypi to have ssh enabled, and be on the local network.

The example commands below use the default hostname of raspberrypi.local, but it is, of course, highly recommended that you change the hostname and password before doing anything else.

So far Erras consists of five files:

- members.csv contains member data
- erras_members.py downloads members.csv
- erras_rfid_reader.py reads members.csv and the RFID reader

Also two systemd unit files to set up automatically starting the python scripts on bootup:

- erras_members.service
- erras_rfid_reader.service

Also, a (slightly hacked) copy of the Wild Apricot API python implementation, WaApi.py, is included.

- WaApi.py

Note, the following assumes you've cloned or downloaded and unpacked the erras files into a subdirectory named "repo" and are executing the commands from the directory that contains the "repo" subdirectory.


To install erras, after cloning it or downloading it from github:

```
$ git clone https://github.com/stevenjowens/erras.git
```

First, copy the erras directory and its files onto the raspberry pi (note the trailing backslashes in the rsync command, be sure to include those on both arguments) and copy the erras_services directory's contents onto the raspberry pi:

```
$ rsync -avz ./repo/erras/ pi@raspberrypi.local:/home/pi/erras/
$ scp ./repo/erras_services/erras_members.service pi@raspberrypi.local:/home/pi
$ scp ./repo/erras_services/erras_rfid_reader.service pi@raspberrypi.local:/home/pi
```

Then ssh into the raspberripi and:

Move the systemd service files into ```/lib/systemd/system```:

```
$ sudo mv /home/pi/erras_rfid_reader.service /lib/systemd/system/erras_rfid_reader.service 
$ sudo mv /home/pi/erras_members.service /lib/systemd/system/erras_members.service
```

Chmod the service files to 644:

```
$ sudo chmod 644 /lib/systemd/system/erras_rfid_reader.service   
$ sudo chmod 644 /lib/systemd/system/erras_members.service
```

Reload the systemd daemon:

```
$ sudo systemctl daemon-reload
```

Enable the erras systemd services:

```
$ sudo systemctl enable erras_rfid_reader.service
Created symlink /etc/systemd/system/multi-user.target.wants/door_rfid_reader.service → /lib/systemd/system/erras_rfid_reader.service.
$ sudo systemctl enable erras_members.service
Created symlink /etc/systemd/system/multi-user.target.wants/erras_members.service → /lib/systemd/system/erras_members.service.
```

This should suffice to start the new services:

```
$ sudo systemctl start erras_rfid_reader.service
$ sudo systemctl start erras_members.service
```

But if it doesn't, just reboot the pi:

```
$ sudo reboot
```

# Debugging

For debugging purposes, you can stop the scripts with:

```
$ sudo systemctl stop erras_members.service
$ sudo systemctl stop erras_rfid_reader.service
```

And then manually run the scripts.  Make sure you use python3.

```
$ python3 erras_members.py
$ python3 erras_readers.py
```

Note that because the scripts use python logging, you should see almost no output to stdout.

## Background and Troubleshooting

For specific details on the hardware, see the [Hardware List](hardware.md), and [wiring diagrams](wiring), but broadly speaking, the ERRAS system is comprised of:

- a wild apricot database (see below)
- an RFID reader, optionally with a keypad for manual entry
- an arduino that reads from the RFID reader
- a raspberry pi that reads serial from the arduino
- erras.ini, a config file
- erras_members.py, downloads member data from wild apricot
- erras_rfid_reader.py, loads data and responds to RFID reader
- an electronic device to activate (relay, electric lock, etc)

Note: This high-level description does not include configuration variable names.

### Arduino

The arduino implements the weigand protocol to read from the RFID reader (and optional keypad) and sends any values received over the serial port to erras_rfid_reader.py, as ASCII.

The arduino prefixs the value with an R to indicate it's from the RFID reader, or K to indicate it's from the Keypad.

The arduino begins the value with ASCII_STX and ends with ASCII_ETX.  

### Wild Apricot Database

The wild apricot database must contain one or more custom fields that contain RFID values or keypad codes.  Erras supports multiple field names, comma-separated.

Note that these values are treated throughout the system as strings, they are not parsed as ints for comparison purposes, etc.

### erras_members.py

erras_members.py downloads the member data, including the custom fields, and saves it as a csv file.  It also saves each CSV download in a backup timestamped file, pruning older files.  Then it sleeps for a period (default is 500 seconds), then downloads a fresh copy.

### erras_rfid_reader.py

erras_rfid_reader.py starts up, reads and parses the CSV file, then goes into an infinite loop reading from the arduino serial port.  

Each time erras_rfid_reader.py loops, it checks the file modification date of the CSV file and reloads it if it is changed.  This means that if new member data is added to wild apricot, you must a) wait long enough for erras_members.py to download it, then b) swipe the RFID reader or enter a keypad code to get erras_rfid_reader.py to loop so it checks the file modification date.

If erras_rfid_reader.py receives a value from the serial port, it checks for an R (for RFID) or K (for keypad) prefix. It ignores any value that doesn't have a prefix.

If erras_rfid_reader.py receives a value with an R or K prefix, it checks against its in memory copy of the member data, in the appropriate field for RFID values or keypad codes.  If it finds a match, it activates the appropriate hardware.

Note: Work is in progress to add support for boolean flag fields for activating specific systems.

# Systemd Cheat Sheet

To list all systemctl services:

```
$ systemctl list-unit-files
```

To see the status of a given systemd unit:

```
$ systemctl status erras_rfid_reader
```

### journalctl

When troubleshooting, also check journalctl for more complete logging information.

Try this combo:

```
$ systemctl start erras_rfid_reader && journalctl -fu
```

### Status

To see the current status of the services:

```
$ sudo systemctl status door_rfid_reader.service
$ sudo systemctl status door_database.service
```

```
$ sudo systemctl status erras_rfid_reader.service
$ sudo systemctl status erras_members.service
```

When you enable a systemd unit file it creates various
links in various spots that cause systemd to, on start up,
read the service file  and take various actions. If you
decide you don't want that to happen, use the disable
command:

```
$ sudo systemctl disable erras_rfid_reader.service
$ sudo systemctl disable erras_members.service
```

In the event a service failed to start, for more complete log info, use journalctl:

```
$ sudo journalctl -fu
```

# License

ERRAS is licensed under the MIT license.  See the [License file](./LICENSE.md)

Portions of this repo which include code from other sources, e.g. the Wild Apricot Python API, are provided here for your convenience and governed by their respective licenses.

See [Wild Apricot API Github repo](https://github.com/WildApricot/ApiSamples/tree/master/python)

## WaApi License

In accordance with the license for the Wild Apricot Python API, the license text is included here, and [here](WaApi_LICENSE.md).

License

Copyright 2018, Wild Apricot Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
