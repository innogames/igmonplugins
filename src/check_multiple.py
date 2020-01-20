#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Wrapper Script to Run Multiple Checks

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

import argparse
import subprocess
import sys

parser = argparse.ArgumentParser(description='Executes origin_command as many times with an element of iterate_over as iterate_over passed')
parser.add_argument('origin_command', help='Original command with base params. e.g. "check_rabbitmq_queue --vhost=events -H localhost --port=15672 -u user -p pass --warning=50 --critical=100 --queue"')
parser.add_argument('iterate_over', nargs='+', help='Queue list separated by space. e.g. "queue1 queue2"')
args=parser.parse_args()

exit_code = 0
unknown = False
message = ''
subs = {}

for iterate_param in args.iterate_over:
    subs[iterate_param] = subprocess.Popen(args.origin_command + ' ' + iterate_param , stdout=subprocess.PIPE, shell=True)

for iterate_param, process in subs.items():
    out, err = process.communicate()
    # Return the worst error code, because nagios interprets '3' as unknown we have to do some magic
    if process.returncode != 0:
        if process.returncode == 3:
            unknown = True
        elif process.returncode > exit_code:
            exit_code = process.returncode
        message += '(' + iterate_param + '): ' + out + '\n'
if exit_code == 0 and unknown:
    exit_code = 3

if not message:
    print('Everything is fine')
else:
    print('Found some problems: ' + message.replace('\n', ' <> '))

sys.exit(exit_code)
