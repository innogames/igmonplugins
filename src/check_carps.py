#!/usr/bin/env python
#
# InnoGames Monitoring Plugins - check_carps.py
#
# Copyright (c) 2017, InnoGames GmbH
#
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
#

import re
import subprocess
import sys
import imp

# Nagios return codes
NAGIOS = {
    'UNDEFINED': -1,
    'OK': 0,
    'WARNING': 1,
    'CRITICAL': 2,
    'UNKNOWN': 3,
}

multiline_msg = ''
final_exit = 'UNDEFINED'

carp_settings = imp.load_source('carp_settings', '/etc/iglb/carp_settings.py')

for ifname, iface_carp in carp_settings.ifaces_carp.items():
    # Read interface configuration:
    p = subprocess.Popen(
        ['/sbin/ifconfig', ifname],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    ifconfig, err = p.communicate()

    iface_checked = False
    for line in ifconfig.split('\n'):
        # Find carp lines, the look like this:
        # carp: MASTER vhid 133 advbase 1 advskew 50
        ifconfig_match = re.match(
            '.*carp: ([A-Z]+) vhid ([0-9]+) advbase.*',
            line,
        )
        if ifconfig_match:
            status = ifconfig_match.group(1)
            vhid = int(ifconfig_match.group(2))

            if vhid != iface_carp['vhid']:
                continue

            iface_checked = True

            multiline_msg += '{} vhid {}: '.format(ifname, iface_carp['vhid'])
            local_exit = 'UNKNOWN'

            if status == 'INIT':
                multiline_msg += 'WARNING: init state\n'
                local_exit = 'WARNING'

            if iface_carp['advskew'] == 150:
                if status == 'MASTER':
                    multiline_msg += (
                        'CRITICAL: configured as backup '
                        'but running as master!\n'
                    )
                    local_exit = 'CRITICAL'
                if status == 'BACKUP':
                    multiline_msg += 'OK: configured and running as backup\n'
                    local_exit = 'OK'

            if iface_carp['advskew'] == 50:
                if status == 'MASTER':
                    multiline_msg += 'OK: configured and running as master\n'
                    local_exit = 'OK'
                if status == 'BACKUP':
                    multiline_msg += (
                        'CRITICAL: configured as master '
                        'but running as backup!\n'
                    )
                    local_exit = 'CRITICAL'

            if NAGIOS[local_exit] > NAGIOS[final_exit]:
                final_exit = local_exit

    if not iface_checked:
        multiline_msg += (
            '{} vhid {}: CRITICAL: no such interface in system!\n'.format(
                ifname, iface_carp['vhid']
            )
        )
        final_exit = 'CRITICAL'


if final_exit == 'UNDEFINED':
    print('UNKNOWN: no carp were found in config!')
    sys.exit(NAGIOS['UNKNOWN'])
else:
    if final_exit == 'OK':
        final_msg = 'All carps are fine'
    else:
        final_msg = 'Some carps are bad!'
    print('{}: {}'.format(final_exit, final_msg))
    print(multiline_msg)
    sys.exit(NAGIOS[final_exit])
