#!/usr/bin/env python
#
# InnoGames Monitoring Plugins - check_linux_ulimit.py
#
# Currently this script only checks the open file limit.
#
# Copyright (c) 2016, InnoGames GmbH
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

from __future__ import print_function
import os.path
import sys
# to be enabled in a better future
'''import argparse
parser = argparse.ArgumentParser(description='check all running processes for the nofile limit, will throw a warning if the limit is nearly reached and critical if the limit is reached')
parser.add_argument('-w','--warning', metavar='warning', type=int, default=90, help="percentage of the limit which may be reached until a warning is thrown.\nIf -w is 99 and the nofile limit is at 1000 the warning will occure if 990 ore more files are opened.")
args = parser.parse_args()

warning = args.warning
'''

if len(sys.argv) == 3 and sys.argv[1] == '-w':
    warning = int(sys.argv[2])
else:
    warning = 60

state = 3
msg = ''
procdir = '/proc'


def _get_procname(piddir):
    # get procname and set to unknown if cmdline is empty or not availabe
    try:
        with open(piddir + '/cmdline', 'r') as f:
            procname = f.readline().split('\x00')[0]
    except OSError:
        pass
    if not procname:
        procname = 'unknown'
    return procname


def _get_fdlimits(limits):
    # parse output of /proc/PID/limits to get max open files
    a,a,a,soft,hard,a = [ line.split() for line in limits if line.startswith('Max open files') ][0]

    return int(soft), int(hard)


def get_state(state, msg):
    # comapre softlimits with openfiles for all pids
    pids = [ pid for pid in os.listdir(procdir) if pid.isdigit() ]
    for pid in pids:
        piddir = os.path.join(procdir, pid)
        try:
            num_fds = len(os.listdir( piddir+ '/fd'))
            with open(os.path.join(piddir + '/limits'), 'r') as f:
                limits = f.readlines()
        except (OSError, IOError):
            continue

        soft_limit, hard_limit = _get_fdlimits(limits)

        # solt_limit 0 means actually not set (during fork etc)
        if soft_limit > num_fds or soft_limit == 0:
            if state not in (1,2):
                state = 0

        elif soft_limit <= num_fds:
            state = 2
            procname = _get_procname(piddir)
            msg += 'PID {0} [{1}] reached its soft limit (open: {2}, limit {3})\n'.format(
                pid,procname, num_fds, soft_limit)

        elif (soft_limit * warning / 100) <= num_fds:
            if state != 2:
                state = 1
            procname = _get_procname(piddir)
            msg += 'PID {0} [{1}] nearly reached its soft limit at {2} open fds\n'.format(
                pid,procname,num_fds)

    return state, msg


if os.getuid() != 0:
    state = 3
    msg += 'I need to be run as root, really'
else:
    state, msg = get_state(state, msg)

if state == 0:
    msg += 'OK'

print(msg)
sys.exit(state)
