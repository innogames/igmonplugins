#!/usr/bin/python

import io,sys,glob,os,time
import datetime,platform
from socket import gethostname

# There are three default config variables in here:
#   CSV_PATH, HDD_NAMES and ALERTS
#
# These values get overwritten by a separate config file (if it exists)
# The separate config file is found in:
#   /etc/nagios-plugins/check_smartmon.cfg
# on each server (distributed by puppet)!

### DEFAULT CONFIG VALUES ### (if /etc/nagios-plugins/check_smartmon.cfg doesn't exist!)
#
# CSV_PATH: This value should never change
CSV_PATH="/var/lib/smartmontools/"

# HDD_NAMES: These are the manufacturer names for the csv data
#            found in: $CSV_PATH/attrlog.$HDD_NAMES*.csv
#            Currently we have these to csv files:
#              /var/lib/smartmontools/attrlog.KINGSTON_SKC100S3480G-480BA0001342.ata.csv
#              /var/lib/smartmontools/attrlog.SAMSUNG_SSD_830_Series-S0WLNYAC201478.ata.csv
#            If you add a new manufacturer, make sure the filenames match to only one file!
HDD_NAMES = ['SAMSUNG', 'KINGSTON']

# ALERTS: These alerts should be pretty self-explanatory
#         Min/Max alert value, exit_status, description
ALERTS = {
  'SAMSUNG': {
    5:{ 'min': 95, 'max': 100, 'exit_status': 1, 'description':'Reallocated Sector Count'},
    9:{ 'min': 95, 'max': 100, 'exit_status': 1, 'description':'Power-on Hours'},
   12:{ 'min': 95, 'max': 100, 'exit_status': 1, 'description':'Power-on Count'},
  177:{ 'min': 93, 'max': 100, 'exit_status': 1, 'description':'Wear Leveling Count'},
  179:{ 'min': 95, 'max': 100, 'exit_status': 1, 'description':'Used Reserved Block Count(total)'},
  181:{ 'min': 95, 'max': 100, 'exit_status': 1, 'description':'Program Fail Count(total)'},
  182:{ 'min': 95, 'max': 100, 'exit_status': 1, 'description':'Erase Fail Count(total)'},
  183:{ 'min': 95, 'max': 100, 'exit_status': 1, 'description':'Runtime Bad Count (total)'},
  187:{ 'min': 95, 'max': 100, 'exit_status': 1, 'description':'Uncorrectable_Error_Cnt'},
  190:{ 'min': 55, 'max': 85 , 'exit_status': 1, 'description':'Airflow Temperature'},
  195:{ 'min': 195,'max': 205, 'exit_status': 1, 'description':'ECC_Rate'},
  199:{ 'min': 250,'max': 255, 'exit_status': 1, 'description':'CRC_Error_Count'},
  235:{ 'min': 95, 'max': 100, 'exit_status': 1, 'description':'Power Recovery Count'},
  240:{ 'min': 95, 'max': 100, 'exit_status': 1, 'description':'Total LBA Written'},
  },
  'KINGSTON': {
    1:{ 'min': 50, 'max': 120, 'exit_status': 1, 'description':'Raw Read Error Rate'},
    5:{ 'min': 95, 'max': 100, 'exit_status': 1, 'description':'Retired Block Count'},
    9:{ 'min': 0,  'max': 100, 'exit_status': 1, 'description':'Power-On Hours (POH)'},
   12:{ 'min': 95, 'max': 100, 'exit_status': 1, 'description':'Device Power Cycle Count'},
   13:{ 'min': 44, 'max': 120, 'exit_status': 1, 'description':'Soft Read Error Rate'},
  100:{ 'min': 0 , 'max':   5, 'exit_status': 1, 'description':'Gigabytes Erased'},
  170:{ 'min': 0 , 'max':   5, 'exit_status': 1, 'description':'Reserve Block Count'},
  171:{ 'min': 95, 'max': 100, 'or': 0, 'exit_status': 1, 'description':'Program Fail Count'},
  172:{ 'min': 95, 'max': 100, 'or': 0, 'exit_status': 1, 'description':'Erase Fail Count'},
  174:{ 'min': 0 , 'max':   5, 'exit_status': 1, 'description':'Unexpected Power Loss'},
  177:{ 'min': 0 , 'max':   5, 'exit_status': 1, 'description':'Wear Range Delta'},
  181:{ 'min': 95, 'max': 100, 'or': 0, 'exit_status': 1, 'description':'Program Fail Count'},
  182:{ 'min': 95, 'max': 100, 'or': 0, 'exit_status': 1, 'description':'Erase Fail Count'},
  184:{ 'min': 95, 'max': 100, 'exit_status': 1, 'description':'Reported I/O Error Detection Code Errors (IOEDC errors)'},
  187:{ 'min': 95, 'max': 100, 'exit_status': 1, 'description':'Reported Uncorrectable Errors (URAISE)'},
  194:{ 'min': 10, 'max':  35, 'exit_status': 1, 'description':'Temperature'},
  195:{ 'min': 95 ,'max': 125, 'exit_status': 1, 'description':'ECC On-the-Fly Error Count'},
  196:{ 'min': 95, 'max': 105, 'exit_status': 1, 'description':'Reallocation Event Count'},
  198:{ 'min': 90, 'max': 120, 'exit_status': 1, 'description':'Uncorrectable Sector Count'},
  199:{ 'min': 195,'max': 205, 'exit_status': 1, 'description':'SATA R-Errors Error Count'},
  201:{ 'min': 95 ,'max': 125, 'exit_status': 1, 'description':'Uncorrectable Soft Read Error Rate (UECC)'},
  204:{ 'min': 95 ,'max': 125, 'exit_status': 1, 'description':'Soft ECC Correction Rate (UECC)'},
  230:{ 'min': 95, 'max': 105, 'exit_status': 1, 'description':'Drive Life Protection Status'},
  231:{ 'min': 85, 'max': 101, 'exit_status': 1, 'description':'SSD Life Left'},
  232:{ 'min': 0 , 'max':   5, 'exit_status': 1, 'description':'Available Reserved Space'},
  233:{ 'min': 0 , 'max':   5, 'exit_status': 1, 'description':'Unknown value?!'},
  234:{ 'min': 0 , 'max':   5, 'exit_status': 1, 'description':'Unknown value?! Maybe: Power Fail Backup Health'},
  241:{ 'min': 0 , 'max':   5, 'exit_status': 1, 'description':'Lifetime Writes from Host System', 'raw':'yes'},
  242:{ 'min': 0 , 'max':   5, 'exit_status': 1, 'description':'Lifetime Reads to Host System'}
  }
}

# Override default config with local config
load_config = "/etc/nagios-plugins/check_smartmon.cfg"
conf_data = {}

try:
    execfile(load_config, conf_data)
    CSV_PATH  = conf_data['CSV_PATH']
    HDD_NAMES = conf_data['HDD_NAMES']
    ALERTS    = conf_data['ALERTS']
except IOError as e:
    pass

os_major = platform.dist()[1].split('.')[0]
if os_major == "8":
    import subprocess as sp
    DEVNULL = open(os.devnull, 'wb')
    proc = sp.Popen(['/bin/systemctl', '-n', '0', 'status', 'smartmontools'], stdout=DEVNULL, stderr=DEVNULL)
    proc.wait()
    if proc.returncode != 0:
        print "CRITICAL: smartmontools is not running! Start it with systemctl start smartmontools"
        sys.exit(2)
else:
    if not os.path.exists('/var/run/smartd.pid'):
        print "CRITICAL: smartmontools is not running! Start it with /etc/init.d/smartmontools start"
        sys.exit(2)
    fh = open('/var/run/smartd.pid', 'r')
    pid = fh.readline().strip('\n')
    fh.close()
    if not os.path.exists('/proc/' + pid + '/'):
        print "CRITICAL: pidfile exists but smartmontools is not running! Start it with /etc/init.d/smartmontools start"
        sys.exit(2)


senddata = []
exit_status = 0

kingston_gb_written = 0
for manufacturer in HDD_NAMES:

    try:
        os.chdir(CSV_PATH)
    except OSError as e:
        senddata.append( str(e) + " ")
        if exit_status < 1:
            exit_status = 1
        continue

    for csvfile in glob.glob("*" + manufacturer + "*.csv"):
        with open(csvfile) as myfile:
            csv_last_line = (list(myfile)[-1])
        csv_array = csv_last_line.split("\t")

        smart_date = csv_array.pop(0).strip(";\n")
        smart_year = int(smart_date.split("-")[0])
        smart_mon = int(smart_date.split("-")[1])
        smart_day = int(smart_date.split("-")[2].split(" ")[0])
        smart_h = int(smart_date.split(":")[0].split(" ")[1])
        smart_m = int(smart_date.split(":")[1])
        smart_s = int(smart_date.split(":")[2])

        future = datetime.datetime.now() - datetime.datetime(smart_year, smart_mon, smart_day, smart_h, smart_m, smart_s)
        smart_date_in_seconds = int(future.days * 24 * 60 * 60 + future.seconds)

        # Throw error if csv data is more than 6 hours old!
        if smart_date_in_seconds > 6 * 60 * 60:
            senddata.append("SMART-CSV-Data is > %s hours old! (%s%s)\n" % (str(smart_date_in_seconds/3600), CSV_PATH, csvfile))
            if exit_status < 1:
                exit_status = 1

        for elements in csv_array:
            element = elements.split(";")
            smart_id = int(element[0])

            if ALERTS[manufacturer][smart_id].get('raw'):
                if ALERTS[manufacturer][smart_id].get('mask'):
                    smart_value = int(element[2]) & ALERTS[manufacturer][smart_id].get('mask')
                else:
                    smart_value = int(element[2])
            else:
                smart_value = int(element[1])

            if not int(smart_id) in ALERTS[manufacturer]:
                senddata.append("Error: No id %s in %s-config found. Please configure this value.\n" % (smart_id, manufacturer))
                if exit_status < 1:
                    exit_status = 1
                continue

            # In Kingston drives some values are just 0 in old version of disk.
            if not ('or' in ALERTS[manufacturer][smart_id] and smart_value == ALERTS[manufacturer][smart_id]['or']):
                if smart_value < ALERTS[manufacturer][smart_id]['min']:
                    senddata.append( "%s: [id=%s] '%s' is '%s' which is lower than '%s'\n" % ( 
                        manufacturer, smart_id, ALERTS[manufacturer][smart_id]['description'], smart_value, ALERTS[manufacturer][smart_id]['min']))
                    if exit_status < ALERTS[manufacturer][smart_id]['exit_status']:
                        exit_status = ALERTS[manufacturer][smart_id]['exit_status']

                if smart_value > ALERTS[manufacturer][smart_id]['max']:
                    senddata.append( "%s: [id=%s] '%s' is '%s' which is higher than '%s\n" % (
                        manufacturer, smart_id, ALERTS[manufacturer][smart_id]['description'], smart_value, ALERTS[manufacturer][smart_id]['max']))
                    if exit_status < ALERTS[manufacturer][smart_id]['exit_status']:
                        exit_status = ALERTS[manufacturer][smart_id]['exit_status']

if kingston_gb_written > 0 and kingston_gb_written < 99:
    for i in range(len(senddata)):
        if 'KINGSTON: [id=13]' in senddata[i]:
            del senddata[i]
    if len(senddata) == 0:
        exit_status = 0

if exit_status == 1:
    print "WARNING: " + " ".join(senddata)
elif exit_status == 2:
    print "CRITICAL: " + " ".join(senddata)
else:
    print "OK"

sys.exit(exit_status)

