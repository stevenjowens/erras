import sys # for checking the python version

# This check has to be at the top or python versioning errors occur in the imports.
if sys.version_info < (3, 0):
    # TODO:  Should handle dependency checking more elegantly.
    print("%s requires python 3, is being run under python %s, exiting.") % (__file__, sys.version_info)
    exit()

from pprint import pprint
from pprint import pformat
import logging
from logging.handlers import TimedRotatingFileHandler
# from systemd.journal import JournaldLogHandler
import datetime
import urllib.request
import urllib.response
import urllib.error
import urllib.parse
import json
import base64
import time 
import csv
import os # for rename and for pruning backup files
import pathlib # used for loading config file
from configparser import ConfigParser
from WaApi_hacked import WaApiClient

######################################################################
class ErrasFiles(object):
    # class for:
    # parsing the values returned by wild apricot API,
    # writing data to CSV files,
    # pruning old files
    # etc.
    def __init__(self, keypad_field_names, rfid_field_names, log):
        self.log = log
        self.keypad_field_names = keypad_field_names
        self.rfid_field_names = rfid_field_names
        
    # For debugging the json returned by wildapricot, not currently used.
    def log_contact(self, contact):
        default_field_name = "default"
        k_field_values = dict()
        for name in self.keypad_field_names:
            k_field_values[name] = self.get_field_value(contact, name, default_field_name)
        r_field_values = dict()
        for name in self.rfid_field_names:
            r_field_values[name] = self.get_field_value(contact, name, default_field_name)
        self.log.debug("DisplayName: %s" % contact.DisplayName)
        self.log.debug("Status: %s" % contact.Status)
        self.log.debug("Email: %s" % contact.Email)
        self.log.debug("FirstName: %s" % contact.FirstName)
        self.log.debug("LastName: %s" % contact.LastName)
    #    self.log.debug("MembershipEnabled: %s" % contact.MembershipEnabled)
        self.log.debug("Id: %s" % contact.Id)
        # self.log.debug("IsAccountAdminitrator: %s" % contact.IsAccountAdminitrator)
        self.log.debug("Url: %s" % contact.Url)

        for name, value in k_field_values.items():
            self.log.debug("%s: %s" % name, value)
        for name, value in r_field_values.items():
            self.log.debug("%s: %s" % name, value)
        self.log.debug("------------------------------")
    
    # Remember to: import csv
    # See https://pymotw.com/2/csv/ for more info on csv module
    def contacts_to_list(self, contacts):
        contacts_list = list()
        contacts_list.append(self.get_contacts_headers())
        for contact in contacts:
            contacts_list.append(self.contact_to_list(contact))
        return contacts_list

    def get_contacts_headers(self):
        headers = ["Id", 
                   "DisplayName",
                   "FirstName",
                   "LastName",
                   "Email",
                   "Status",
                   "Url"]
        for name in sorted(self.keypad_field_names):
            headers.append(name)
        for name in sorted(self.rfid_field_names):
            headers.append(name)
        return headers
    
    def strip(self, foo):
        if foo is not None:
            foo2 = foo.strip()  # Remove any leading/trailing whitespace
            foo2 = foo2.lstrip("0") # Remove any leading zeroes to avoid python interpreting it as octal
            return foo2

    def contact_to_list(self, contact):
        field_values = dict()
        for name in self.keypad_field_names:
            field_values[name] = self.strip(self.get_field_value(contact, name, "default"))
        for name in self.rfid_field_names:
            field_values[name] = self.strip(self.get_field_value(contact, name, "default"))

        contact_list = [contact.Id,
                contact.DisplayName,
                contact.FirstName,
                contact.LastName,
                contact.Email,
                contact.Status,
                contact.Url]
        for name, value in field_values.items():
            contact_list.append(value)
        return contact_list
    
    def get_field_value(self, contact, fieldname, defaultvalue=""):
        # self.log.debug("get_field_value:  looking for fieldname \"%s\", default value is \"%s\"" % (fieldname, defaultvalue))
        if not contact.FieldValues:
            return defaultvalue
        for field in contact.FieldValues:
           # self.log.debug("%s has name: \"%s\", code: \"%s\", value: \"%s\"" % (contact.DisplayName, field.FieldName, field.SystemCode, field.Value))
            if fieldname == field.FieldName:
                # self.log.debug("Returning name \"%s\" value \"%s\"" % (fieldname, field.Value))
                return field.Value
        return defaultvalue
    
    def print_contacts_csv(self, contacts, filename):
        contacts_list = self.contacts_to_list(contacts)
        self.log.debug("Writing data to filename %s" % filename)
        filehandle = open(filename, 'wt')
        try:
            writer = csv.writer(filehandle, quoting=csv.QUOTE_NONNUMERIC, dialect='excel')
            for row in contacts_list:
                writer.writerow(row)
        finally:
            filehandle.close()
    
    # Not used in current version, but very handy for debugging, so keeping.
    def todict(self, obj, classkey=None):
        # from https://stackoverflow.com/questions/1036409/recursively-convert-python-object-graph-to-dictionary
        # https://stackoverflow.com/a/1118038/1813403
        if isinstance(obj, dict):
            data = {}
            for (k, v) in obj.items():
                data[k] = todict(v, classkey)
            return data
        elif hasattr(obj, "_ast"):
            return todict(obj._ast())
        elif hasattr(obj, "__iter__") and not isinstance(obj, str):
            return [todict(v, classkey) for v in obj]
        elif hasattr(obj, "__dict__"):
            data = dict([(key, todict(value, classkey)) 
                for key, value in obj.__dict__.items()
                if not callable(value) and not key.startswith('_')])
            if classkey is not None and hasattr(obj, "__class__"):
                data[classkey] = obj.__class__.__name__
            return data
        else:
            return obj
    
    def list_backups_sorted(self, dirpath, prefix, suffix):
        all_files = sorted(os.listdir(dirpath), key=os.path.getctime)
        files2 = list()
        for file in all_files:
            filename = os.fsdecode(file)
            if filename.endswith(suffix) and filename.startswith(prefix):
                # self.log.debug(os.path.join(directory, filename))
                files2.append(os.path.join(dirpath, filename))
        return files2
    
    def prune(self, dirpath, prefix, suffix, count):
        backups = self.list_backups_sorted(dirpath, prefix, suffix)
        backups = backups[:-count]
        count = 0
        for file in backups:
            if os.path.isfile(file):
                count += 1
                os.remove(file)
        return count

    ######################################################################
    # These two methods are superfluous and can be deleted,
    # they're here mainly as an example.
    def get_10_active_members(self, api):
        params = {'$filter': 'member eq true',
                  '$top': '10',
                  '$async': 'false'}
        request_url = contactsUrl + '?' + urllib.parse.urlencode(params)
        self.log.debug(request_url)
        return api.execute_request(request_url).Contacts
    
    def print_contact_info(self, contact):
        self.log.debug('Contact details for ' + contact.DisplayName + ', ' + contact.Email)
        self.log.debug('Main info:')
        self.log.debug('\tID:' + str(contact.Id))
        self.log.debug('\tFirst name:' + contact.FirstName)
        self.log.debug('\tLast name:' + contact.LastName)
        self.log.debug('\tEmail:' + contact.Email)
        self.log.debug('\tAll contact fields:')
        for field in contact.FieldValues:
            if field.Value is not None:
                self.log.debug('\t\t' + field.FieldName + ':' + repr(field.Value))
    # end of two superfluous example methods
    ######################################################################
    
# END of utility functions    
######################################################################
# Set up configuration variables.

# TODO:  delete this default dict after testing fallback.
# default_confs = {
#    "filter_query" : "status eq Active or status eq 'Pending - Renewal'",
#    "csv_backup_filename_root" : "erras_backup_members_",
#    "csv_filename_temp" : "erras_members_new.csv",
#    "csv_filename" : "erras_members.csv",
#    "apricot_response_root" : "wild_apricot_response_",
#    "members_log_filename" : "erras_members.log",
#    "keypad_field_names" : "Keypad",
#    "rfid_field_names" : "RFID",
#    "loop_delay" : 500,
#    "csv_prune_max" : 5,
#    "json_prune_max" : 10
# }
# parser = ConfigParser(default_confs)
# TODO:  delete the above default dict after testing fallback.

parser = ConfigParser()
config_file_name = 'erras.ini'
section_name = "erras"
# This constructs a file path to the config_file_name in the same directory as the script file.
config_path = str(pathlib.Path(__file__).with_name(config_file_name))
with open(config_path) as config_file:
    parser.read_file(config_file)

wa_api_client_id = parser.get(section_name, "wa_api_client_id")
wa_api_client_secret = parser.get(section_name, "wa_api_client_secret")
credential_name = parser.get(section_name, "credential_name")
credential_key = parser.get(section_name, "credential_key")
api_key = parser.get(section_name, "api_key")
filter_query = parser.get(section_name, "filter_query", fallback="status eq Active or status eq 'Pending - Renewal'")
request_url_root = parser.get(section_name, "request_url_root")
csv_backup_filename_root = parser.get(section_name, "csv_backup_filename_root", fallback="erras_backup_members_")
csv_filename_temp = parser.get(section_name, "csv_filename_temp", fallback="erras_members_new.csv")
csv_filename = parser.get(section_name, "csv_filename", fallback="erras_members.csv")
apricot_response_root = parser.get(section_name, "apricot_response_root", fallback="wild_apricot_response_")
loop_delay = parser.getint(section_name, "loop_delay", fallback=500)
csv_prune_max = parser.getint(section_name, "csv_prune_max", fallback=5)
json_prune_max = parser.getint(section_name, "json_prune_max", fallback=5)
log_filename = parser.get(section_name, "members_log_filename", fallback="erras_members.log")
keypad_field_names_string = parser.get(section_name, "keypad_field_names", fallback="Keypad")
rfid_field_names_string = parser.get(section_name, "rfid_field_names", fallback="RFID")
# Split up the key_fields_string into a list.
# TODO: look into this later for split with escape
# https://stackoverflow.com/questions/18092354/python-split-string-without-splitting-escaped-character
keypad_field_names = keypad_field_names_string.split(",")
rfid_field_names = rfid_field_names_string.split(",")

# set up logger
logger_name = "erras_members"
logger_format = '%(asctime)s %(levelname)s %(message)s'
log = logging.getLogger(logger_name)
log.setLevel(logging.DEBUG)
formatter = logging.Formatter(logger_format)

# https://docs.python.org/2/library/logging.handlers.html
# how often the log file is rotated is interval * when
# when = S/M/H/D/W0-W6/midnight
# so when='S', interval=500 means every 500 seconds.
handler = TimedRotatingFileHandler(log_filename, when='D', interval=1, backupCount=20)
handler.setFormatter(formatter)
# handler.setLevel(logging.INFO)
handler.setLevel(logging.DEBUG)

log.addHandler(handler)
# log.addHandler(JournalHandler())

# Log the field names
for field in keypad_field_names:
    log.debug("keypad field names: %s" % field)
for field in rfid_field_names:
    log.debug("RFID field names: %s" % field)

errasfile = ErrasFiles(keypad_field_names, rfid_field_names, log)

api = WaApiClient(wa_api_client_id, wa_api_client_secret, log, debug=True)
api.authenticate_with_contact_credentials(credential_name, credential_key)

log.info("Starting request loop.")
while(True):
    log.info("########################### requesting member data ############################")
    params = { '$filter': filter_query,
               '$async': 'false' }

    request_url = request_url_root + '?' + urllib.parse.urlencode(params)
    log.debug("Request url is: %s" % request_url)

    contacts = api.execute_request(request_url)
    # each contact is an ApiObject instance
    contact_list = contacts.Contacts
    log.info("There are %d contacts in results." % len(contact_list))
    
    # Save the newly downloaded member data in a backup file
    csv_backup_filename = csv_backup_filename_root + api.get_timestamp() + ".csv"
    errasfile.print_contacts_csv(contact_list, csv_backup_filename)
    # And in a temp file.
    errasfile.print_contacts_csv(contact_list, csv_filename_temp)

    # Note, do not use across filesystem boundaries.  File rename is
    # only atomic on unix if both new and old are on the same
    # filesystem.
    os.rename(csv_filename_temp, csv_filename)
    log.info("Member data saved in filename %s" % csv_filename)
    directory = os.getcwd()
    errasfile.prune(directory, csv_backup_filename_root, ".csv", csv_prune_max)
    errasfile.prune(directory, apricot_response_root, ".json", json_prune_max)

    log.info("Sleeping for %d seconds." % loop_delay)
    time.sleep(loop_delay)
