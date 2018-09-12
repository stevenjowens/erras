# This check has to be at the top or python versioning errors occur in the imports.
# TODO: There is probably a more pythonic way to do this.
import sys # for checking the python version
if sys.version_info < (3, 0):
    print("%s requires python 3, is being run under python %s, exiting.") % (__file__, sys.version_info)
    exit()

import csv
import time
import serial
import RPi.GPIO as GPIO
import os # for checking members.csv modification time
import sys  # for checking python version
import logging
from logging.handlers import TimedRotatingFileHandler
from configparser import ConfigParser
# TODO: trying to use systemd for logging causes errors on the raspberrypi.
# TODO: still working on figuring it out.
# from systemd.journal import JournaldLogHandler  

class Member(object):
    def __init__(self, id, displayName, firstName, lastName, email, status, url, keypad_fields, rfid_fields):
        self.id = id
        self.displayName = displayName
        self.firstName = firstName
        self.lastName = lastName
        self.email = email
        self.status = status
        self.url = url
        self.keypad_fields = keypad_fields
        self.rfid_fields = rfid_fields

class MemberDb(object):
    def __init__(self, log, csv_filename, keypad_field_names, rfid_field_names):
        self.log = log
        self.csv_filename = csv_filename
        self.mtime = os.path.getmtime(self.csv_filename) 
        self.door_keypad_codes = dict()
        self.door_rfid_codes = dict()
        self.keypad_field_names = keypad_field_names
        self.rfid_field_names = rfid_field_names
        self.load_csv()

    def check_mtime(self):
        currentmtime = os.path.getmtime(self.csv_filename)
        # self.log.info("old time = %d, current time = %d, diff = %d" % (self.mtime, currentmtime, (currentmtime - self.mtime)))
        if currentmtime > self.mtime:
            self.log.info("%s modification time changed, reloading." % csv_filename) 
            self.load_csv()
            self.mtime = currentmtime

    def populate_field_values(self, member):
        for key, value in member.keypad_fields.items():
            try:
                # self.door_keypad_codes[int(value)] = member
                self.door_keypad_codes[value] = member
                log.debug("Setting keypad code for %s=%s" % (member.displayName, value))
            except:
                log.info("Exception on parsing key value for member \"%s\", %s=%s: Exception: %s" % (member.displayName, key, value, sys.exc_info()[0]))
        for key, value in member.rfid_fields.items():
            try:
                # self.door_rfid_codes[int(value)] = member
                self.door_rfid_codes[value] = member
                log.debug("Setting RFID code for %s=%s" % (member.displayName, value))
            except:
                log.info("Exception on parsing key value for member \"%s\", %s=%s, Exception: %s" % (member.displayName, key, value, sys.exc_info()[0]))

    # TODO:  Think about extracting all the CSV stuff to a separate class
    def extract_fields(self, row, field_names):
        fields = dict()
        for name in field_names:
            fields[name] = row[name]
        return fields

    def load_csv(self):
        with open(self.csv_filename, 'r') as filehandle:
            reader = csv.DictReader(filehandle, quoting=csv.QUOTE_NONNUMERIC, dialect='excel')
            for row in reader:
                keypad_fields = self.extract_fields(row, self.keypad_field_names)
                rfid_fields = self.extract_fields(row, self.rfid_field_names)
                member = Member(row['Id'],
                                row['DisplayName'],
                                row['FirstName'],
                                row['LastName'],
                                row['Email'],
                                row['Status'],
                                row['Url'],
                                keypad_fields,
                                rfid_fields)
                self.populate_field_values(member)

    def check_for_member_rfid(self, rfid):
        self.log.debug("check_for_member_rfid firing with rfid value \"%s\"" % rfid)
        return self.door_rfid_codes.get(rfid)

    def check_for_member_keypad(self, keypad):
        self.log.debug("check_for_member_rfid firing with keypad value \"%s\"" % keypad)
        return self.door_keypad_codes.get(keypad)

class RfidReader(object):
    def __init__(self, log):
        self.log = log
        self.ASCII_STX = b"\x02"
        self.ASCII_ETX = b"\x03"
        GPIO.setmode(GPIO.BCM)
        self.init_GPIOs()
        self.portRF = serial.Serial('/dev/serial0',9600)

    def read(self):
        self.log.debug("serial read starting.")
        rfid_value = ""
        read_byte = b""

        # If it's not ASCII_STX, read and skip until we get to ASCII_STX
        # only begin accumulating bytes after we see an ASCII_STX
        read_start_flag = True
        while read_start_flag:
            if self.ASCII_STX == read_byte:
                self.log.debug("Saw ASCII_STX, exiting pre-accumulation while loop")
                read_byte = b""
                read_start_flag = False
                break
            else:
                self.log.debug("Skipping value: %s" % read_byte.decode("ascii"))
                read_byte = self.portRF.read()
        self.log.debug("after STX while loop, beginning accumulation.")

        # Start accumulating bytes, exit loop when we see an ASCII_ETX
        read_flag = True
        while read_flag:
            if self.ASCII_ETX == read_byte:
                self.log.debug("Saw ASCII_ETX, exiting while loop, accumulator contains %s" % rfid_value)
                read_byte = b""
                read_flag = False
                break
            else:
                rfid_value += read_byte.decode("ascii")
                # self.log.debug("appending value: \"%s\", result is \"%s\"" % (read_byte.decode("ascii"), rfid_value) )
                read_byte = self.portRF.read()
        self.log.debug("after ETX while loop.")

        if sys.version_info[0] < 3:
            # flushInput() is deprecated after 3.0, use reset_input_buffer() instead
            rfidreader.portRF.reset_input_buffer()
        else:
            rfidreader.portRF.flushInput()
        self.log.debug("rfid_value is \"%s\"" % rfid_value)
        return rfid_value

    def init_GPIOs(self): #startup light/door sequence
        GPIO.setup(23,GPIO.OUT)
        GPIO.setup(24,GPIO.OUT)
        GPIO.setup(25,GPIO.OUT)
        GPIO.output(23,True) # 23 is the door magnet
        GPIO.output(24,True) # 24 is the red light
        GPIO.output(25,False) # 25 is the green light

class Activator(object):
    def __init__(self, memberdb, rfidreader, log):
        self.rfidreader = rfidreader
        self.memberdb = memberdb
        self.log = log
        self.loop_boolean = True
        self.activator_delay = 6
        self.light_delay = 2
        self.mtime = 0
        
    def tag_matched(self, ID):
        self.log.info("ID string matched a member, Activating" % ID)
        self.log.debug("ID string \"%s\" matched, Activating" % ID)
        GPIO.output(23,False) # Turn on door magnet
        GPIO.output(24,False) # Turn off red light
        GPIO.output(25,True) # Turn on green light
        time.sleep(self.activator_delay)
        GPIO.output(23,True) # turn off door magnet
        GPIO.output(24,True) # turn on red light
        GPIO.output(25,False) # turn off green light

    def tag_not_matched(self, ID):
        GPIO.output(23,True) # Make sure door is still unactivated
        self.log.info("ID string not match any member, Not Activating" % ID)
        self.log.debug("ID string \"%s\" did not match, Not Activating" % ID)
        GPIO.output(24,False) # turn off red light
        GPIO.output(25,False) # Make sure green light is off
        time.sleep(self.light_delay)
        GPIO.output(24,True) # turn back on red light

    def loop(self):
        while self.loop_boolean:
            self.log.debug("loop")
            ID = self.rfidreader.read()
            self.log.debug("Received ID value \"%s\"" % ID)
            # TODO: This nested if is kind of ugly, can we clean it up?
            if None != ID and '' != ID and "" != ID and ID is not None:
                k_or_r = ID[0]
                ID = ID[1:]  # Clip the ID type character off
                member = None
                if None != ID and '' != ID and "" != ID and ID is not None:
                    if k_or_r == "K":
                        self.log.debug("ID starts with K, it is a keypad entry.")
                        member = memberdb.check_for_member_keypad(ID)
                    if k_or_r == "R":
                        self.log.debug("ID starts with R, it is a RFID card entry.")
                        member = memberdb.check_for_member_rfid(ID)
                else:
                    self.log.info("Keypad string empty after trimming leading K/R character, ignoring.")

                if member:
                    self.log.warning("Member name \"%s\" found matching code type %s" % (member.displayName, k_or_r))
                    self.log.debug("Member name \"%s\" found matching code type %s with value %s" % (member.displayName, k_or_r, ID))
                    self.tag_matched(ID)
                else:
                    self.log.warning("No member found matching code type %s" % (k_or_r))
                    self.log.debug("No member found matching code type %s with value %s" % (k_or_r, ID))
                    self.tag_not_matched(ID)
            ID = ""
            rfid = ""
            checksum = ""
            decimalid = 0
            rfidreader.portRF.flushInput()
            memberdb.check_mtime()

######################################################################
# Set up configuration variables.

# TODO: delete defaults dict after testing fallback
# default_confs = {
#     "csv_filename" : "erras_members.csv",
#     "rfid_reader_log_filename" : "erras_rfid_reader.log",
#     "activate_log_filename" : "erras_activate.log"
# }
# parser = ConfigParser(default_confs)
# TODO: delete the above defaults dict after testing fallback

parser = ConfigParser()
config_file_name = 'erras.ini'
# This constructs a file path to the config_file_name in the same directory as the script file.
config_path = str(pathlib.Path(__file__).with_name(config_file_name))
with open(config_path) as config_file:
    parser.read_file(config_file)

csv_filename = parser.get("erras", "csv_filename", fallback="erras_members.csv")
log_filename = parser.get("erras", "rfid_reader_log_filename", fallback="erras_rfid_reader.log")
log_filename = parser.get("erras", "activate_log_filename", fallback="erras_activate.log")
keypad_field_names_string = parser.get("erras", "keypad_field_names", fallback="Keypad")
rfid_field_names_string = parser.get("erras", "rfid_field_names", fallback="RFID")

# Split up the keypad_field_names_string into a list.
# TODO: look into this later for split with escape
# https://stackoverflow.com/questions/18092354/python-split-string-without-splitting-escaped-character
keypad_field_names = keypad_field_names_string.split(",")
rfid_field_names = rfid_field_names_string.split(",")

# set up logger
log = logging.getLogger('erras_activator')
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
log.setLevel(logging.DEBUG)

# https://docs.python.org/2/library/logging.handlers.html
# how often the log file is rotated is interval * when
# when = S/M/H/D/W0-W6/midnight
# so when='S', interval=500 means every 500 seconds.
handler = TimedRotatingFileHandler(log_filename, when='D', interval=7, backupCount=20)

# handler.setLevel(logging.INFO)
handler.setLevel(logging.DEBUG)
handler.setFormatter(formatter)
log.addHandler(handler)

activate_handler = TimedRotatingFileHandler(activate_log_filename, when='D', interval=1, backupCount=90)
activate_handler.setFormatter(formatter)
activate_handler.setLevel(logging.WARNING)
log.addHandler(activate_handler)

# TODO: trying to use systemd for logging causes errors on the raspberrypi.
# TODO: still working on figuring it out.
# log.addHandler(JournalHandler())

# Log the field names
for field in keypad_field_names:
    log.info("keypad field names: %s" % field)
for field in rfid_field_names:
    log.info("RFID field names: %s" % field)

memberdb = MemberDb(log, csv_filename, keypad_field_names, rfid_field_names)
rfidreader = RfidReader(log)
activator = Activator(memberdb, rfidreader, log)
activator.loop()
