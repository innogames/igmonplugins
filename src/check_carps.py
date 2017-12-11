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
import socket
import struct
import subprocess
import sys
import os
import imp

# Nagios return codes
exit_ok      = 0
exit_warn    = 1
exit_crit    = 2
exit_unknown = 3

carp_settings = imp.load_source('carp_settings', '/etc/iglb/carp_settings.py')

try:
	fhostname = open('/etc/rc.conf.d/hostname', 'r')
	line =  fhostname.readline()
	hostname_match = re.match('^hostname="([a-z0-9\-]+)', line)
	hostname = hostname_match.group(1)
	fhostname.close()
except:
	print("UNKNOWN: Unable to read hostname and determine system's role.")
	sys.exit(exit_unknown)

known_hwlbs = { key for iface_dict in carp_settings.ifaces.values() for key in iface_dict.keys() }
if hostname in known_hwlbs or hostname + '.ig.local' in known_hwlbs:
	my_role = "MASTER"
else:
	my_role = "BACKUP"

result_txt = "my role is %s; " % (my_role)
result_code = 0

p = subprocess.Popen(['/sbin/ifconfig', '-l'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
ifaces, err = p.communicate()
ifaces = ifaces.split()

carps9 = []
for carp_k, carp_v in  carp_settings.ifaces.iteritems():
	for hwlb_k, hwlb_v in carp_v.iteritems():
		carps9.append("carp" + hwlb_k.split('lb')[1] + carp_k)

for ifname in carp_settings.ifaces.keys() + carps9:
	# Read interface configuration:
	p = subprocess.Popen(['/sbin/ifconfig', ifname], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	ifconfig, err = p.communicate()

	for line in ifconfig.split("\n"):
		try:
			# Find carp lines, the look like this:
			#carp: MASTER vhid 133 advbase 1 advskew 50
			ifconfig_match = re.match(".*carp: ([A-Z]+) vhid ([0-9]+) advbase.*", line)
			status =     ifconfig_match.group(1)
			vhid   = int(ifconfig_match.group(2))
		except: 
			continue

		# Ignore INIT state CARPs.
		if status=="INIT":
			continue

		if (my_role=="BACKUP" and status!='BACKUP') or (my_role=="MASTER" and status!='MASTER'):
			result_code = exit_crit
			result_txt += "carp %d is %s; " % (vhid, status)

if result_code == exit_ok:
	result_dscr = "OK"
elif result_code == exit_warn:
	result_dscr = "WARNING"
elif result_code == exit_crit:
	result_dscr = "CRITICAL"
elif result_code == exit_unknown:
	result_dscr = "UNKNOWN"

print("%s: %s" % (result_dscr, result_txt))
sys.exit(result_code)

