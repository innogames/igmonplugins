#!/usr/bin/env python
#
# InnoGames Monitoring Plugins - check_puppetlog.py
#
# Copyright (c) 2016, InnoGames GmbH
#
# XXX This script uses old string formatting without .format() to be
# compatible with Python 2.5.
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

import time
import sys
import hashlib

errors = 0
msg_count = {}
msg_count['catalog'] = 0
msg_text = {}
msg_time = {}
msg_time['catalog'] = 0
new = 0
check_time = time.time() - 10800 # check the last 3 hours
important_time = time.time() - 3600 # only if message is within the last 1 hour

lines = open('/var/log/daemon.log').readlines()
for line in lines[-200:]:
	if "puppet-agent" in line:
		# remove duplicate spaces - makes problems with strptime and split
		line = " ".join(line.split())
		content = line.split(" ", 5)
		#next line if message is empty
		if len(content) < 6:
			continue
		message_time = time.strptime("%s %s %s %s" %(
			time.localtime().tm_year,content[0],content[1],content[2]), "%Y %b %d %H:%M:%S")
		timestamp = time.mktime(message_time)
		if timestamp > check_time:
			#print time.strftime("%y-%m-%d %H:%M:%S",message_time)
			#print time.mktime(message_time)
			#print content[5]
			if "ig.nagios" in content[5]:
				#file not found but the following is nevertheless may interesting
				if "cannot be authenticated" in content[5]:
					errors += 1
					hash = hashlib.md5(content[5]).hexdigest()
					msg_count.setdefault(hash,0)
					msg_count[hash] += 1
					msg_text[hash] = content[5]
					msg_time[hash] = timestamp
			elif "Error 400" in content[5]:
				errors += 1
				hash = hashlib.md5(content[5]).hexdigest()
				msg_count.setdefault(hash,0)
				msg_count[hash] += 1
				msg_text[hash] = content[5]
				msg_time[hash] = timestamp
			elif "Connection refused" in content[5]:
				errors += 1
				hash = hashlib.md5(content[5]).hexdigest()
				msg_count.setdefault(hash,0)
				msg_count[hash] += 1
				msg_text[hash] = content[5]
				msg_time[hash] = timestamp
			elif " E: " in content[5]:
				errors += 1
				hash = hashlib.md5(content[5]).hexdigest()
				msg_count.setdefault(hash,0)
				msg_count[hash] += 1
				msg_text[hash] = content[5]
				msg_time[hash] = timestamp
			elif " failed: " in content[5]:
				errors += 1
				hash = hashlib.md5(content[5]).hexdigest()
				msg_count.setdefault(hash,0)
				msg_count[hash] += 1
				msg_text[hash] = content[5]
				msg_time[hash] = timestamp
			elif "Could not evaluate" in content[5]:
				errors += 1
				hash = hashlib.md5(content[5]).hexdigest()
				msg_count.setdefault(hash,0)
				msg_count[hash] += 1
				msg_text[hash] = content[5]
				msg_time[hash] = timestamp
			elif " Skipping because of failed dependencies" in content[5]:
				errors += 1
				hash = hashlib.md5(content[5]).hexdigest()
				msg_count.setdefault(hash,0)
				msg_count[hash] += 1
				msg_text[hash] = content[5]
				msg_time[hash] = timestamp
			elif "Failed to apply" in content[5]:
				errors += 1
				hash = hashlib.md5(content[5]).hexdigest()
				msg_count.setdefault(hash,0)
				msg_count[hash] += 1
				msg_text[hash] = content[5]
				msg_time[hash] = timestamp
			elif "Finished catalog run in" in content[5]:
				msg_time['catalog'] = timestamp
				#send_error(content[5],timestamp)
key = max(msg_count.iterkeys(), key=(lambda key: msg_count[key]))
if int(msg_time[key]) > important_time:
	if int(msg_time[key]) > (int(msg_time['catalog']) - 60):
		new = 1

if errors and msg_count[key] >= 4 and new:
	print "WARNING: %d puppet error(s) for the last 3 hours! - %d times %s " %(errors, msg_count[key], msg_text[key])
	sys.exit(1)
else:
	print "OK - less than 4 repeated erros, more than 1 hour ago or last run fixed the most often counted error"
