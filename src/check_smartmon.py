#!/usr/bin/env python
"""InnoGames Monitoring Plugins - SMART Check

Copyright (c) 2017 InnoGames GmbH
"""
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import datetime
import glob
import sys
import os

# There are three default config variables in here:
#   CSV_PATH, HDD_NAMES and ALERTS
#
# These values get overwritten by a separate config file (if it exists)
# The separate config file is found in:
#   /etc/nagios-plugins/check_smartmon.cfg
# on each server (distributed by puppet)!

CSV_PATH = '/var/lib/smartmontools'

# We don't provide default values anymore.
load_config = '/etc/nagios-plugins/check_smartmon.cfg'
conf_data = {}

try:
    with open(load_config) as f:
        code = compile(f.read(), load_config, 'exec')
        exec(code, conf_data)
    CSV_PATH = conf_data['CSV_PATH']
    HDD_NAMES = conf_data['HDD_NAMES']
    ALERTS = conf_data['ALERTS']
except IOError as e:
    pass

senddata = []
exit_status = 0
kingston_gb_written = 0

try:
    os.chdir(CSV_PATH)
except OSError as e:
    print('Could not find {}'.format(CSV_PATH))
    if exit_status < 1:
        exit_status = 1
    sys.exit(exit_status)

# find all csvfiles and match a HDD_NAME and use the first one
files = {}
for csv in glob.glob("*.csv"):
    for model in HDD_NAMES:
        if csv.find(model) != -1:
            files[csv] = model
            break

for csvfile in files:
    with open(csvfile) as myfile:
        manufacturer = files[csvfile]
        # Get a snapshot in case file changes in the meantime
        myfile_list = list(myfile)
        if len(myfile_list) == 0:
            # Empty, pass
            continue
        csv_last_line = myfile_list[-1]
    csv_array = csv_last_line.split("\t")

    smart_date = csv_array.pop(0).strip(";\n")
    smart_year = int(smart_date.split("-")[0])
    smart_mon = int(smart_date.split("-")[1])
    smart_day = int(smart_date.split("-")[2].split(" ")[0])
    smart_h = int(smart_date.split(":")[0].split(" ")[1])
    smart_m = int(smart_date.split(":")[1])
    smart_s = int(smart_date.split(":")[2])

    smart_date_diff = datetime.datetime.now() - datetime.datetime(
        smart_year, smart_mon, smart_day, smart_h, smart_m, smart_s
    )

    # Throw error if csv data is more than 6 hours old!
    if smart_date_diff > datetime.timedelta(hours=6):
        senddata.append(
            'SMART-CSV-Data is {} old! ({}/{})\n' .format(
                smart_date_diff, CSV_PATH, csvfile
            )
        )
        if exit_status < 1:
            exit_status = 1

    for elements in csv_array:
        element = elements.split(";")
        smart_id = int(element[0])

        # Skip attributes that do not exists in our config
        if smart_id not in ALERTS[manufacturer]:
            continue

        if ALERTS[manufacturer][smart_id].get('raw'):
            if ALERTS[manufacturer][smart_id].get('mask'):
                smart_value = (
                    int(element[2]) &
                    ALERTS[manufacturer][smart_id].get('mask')
                )
            else:
                smart_value = int(element[2])
        else:
            smart_value = int(element[1])

        if not int(smart_id) in ALERTS[manufacturer]:
            senddata.append(
                'Error: No id {} in {}-config found. '
                'Please configure this value.\n'
                .format(
                    smart_id, manufacturer
                )
            )
            if exit_status < 1:
                exit_status = 1
            continue

        # In Kingston drives some values are just 0 in old version of disk.
        if ALERTS[manufacturer][smart_id].get('or') != smart_value:
            if smart_value < ALERTS[manufacturer][smart_id]['min']:
                senddata.append(
                    '{}: [id={}] "{}" is "{}" '
                    'which is lower than "{}"\n'.format(
                        manufacturer, smart_id,
                        ALERTS[manufacturer][smart_id]['description'],
                        smart_value,
                        ALERTS[manufacturer][smart_id]['min']
                    )
                )
                if (
                    exit_status <
                    ALERTS[manufacturer][smart_id]['exit_status']
                ):
                    exit_status = \
                        ALERTS[manufacturer][smart_id]['exit_status']

            if smart_value > ALERTS[manufacturer][smart_id]['max']:
                senddata.append(
                    '{}: [id={}] "{}" is "{}" '
                    'which is higher than "{}"\n'.format(
                        manufacturer, smart_id,
                        ALERTS[manufacturer][smart_id]['description'],
                        smart_value,
                        ALERTS[manufacturer][smart_id]['max']
                    )
                )
                if (
                    exit_status <
                    ALERTS[manufacturer][smart_id]['exit_status']
                ):
                    exit_status = \
                        ALERTS[manufacturer][smart_id]['exit_status']

if kingston_gb_written > 0 and kingston_gb_written < 99:
    for i in range(len(senddata)):
        if 'KINGSTON: [id=13]' in senddata[i]:
            del senddata[i]
    if len(senddata) == 0:
        exit_status = 0

if exit_status == 1:
    print('WARNING: ' + ' '.join(senddata))
elif exit_status == 2:
    print('CRITICAL: ' + ' '.join(senddata))
else:
    print('OK')

sys.exit(exit_status)
