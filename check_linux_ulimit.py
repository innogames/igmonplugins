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

import os
import sys

# to be enabled in a better future
'''import argparse
parser = argparse.ArgumentParser(description='check all running processes for the nofile limit, will throw a warning if the limit is nearly reached and critical if the limit is reached')
parser.add_argument('-w','--warning', metavar='warning', type=int, default=90, help="percentage of the limit which may be reached until a warning is thrown.\nIf -w is 99 and the nofile limit is at 1000 the warning will occure if 990 ore more files are opened.")
args = parser.parse_args()

warning = args.warning
'''

def main():
    if os.getuid() != 0:
        state = 3
        msg = 'I need to be run as root, really'
    else:
        if len(sys.argv) == 3 and sys.argv[1] == '-w':
            warning = int(sys.argv[2])
        else:
            warning = 60

        state, msg = get_state(warning)

        if state == 0:
            msg += 'OK'

    print(msg)
    sys.exit(state)

def get_state(warning):

    state = 3
    msg = ''

    # compare softlimits with openfiles for all pids
    pids = [pid for pid in list_proc_db() if pid.isdigit()]
    for pid in pids:
        num_fds = len(list_proc_db(pid, 'fd'))
        soft_limit = get_proc_ulimit(pid, 'Max open files')

        # soft_limit 0 means actually not set (during fork etc)
        if soft_limit > num_fds or soft_limit == 0:
            if state not in (1, 2):
                state = 0

        elif soft_limit <= num_fds:
            state = 2
            msg += 'PID {0} [{1}] reached its soft limit (open: {2}, limit {3})\n'.format(
                pid, get_proc_name(pid), num_fds, soft_limit
            )

        elif (soft_limit * warning / 100) <= num_fds:
            if state != 2:
                state = 1
            msg += 'PID {0} [{1}] nearly reached its soft limit at {2} open fds\n'.format(
                pid, get_proc_name(pid), num_fds
            )

    return state, msg

def list_proc_db(*dirs):
    """Return the contents of a directory under the proc file system

    We have to handle the exceptions in here, because the proc files
    change after we read the list.
    """

    path = '/proc/' + '/'.join(dirs)

    try:
        return os.listdir(path)
    except (OSError, IOError):
        return []

def read_proc_db(*dirs):
    """Return the contents of a file under the proc file system

    We have to handle the exceptions in here, because the proc files
    change after we read the list.
    """

    path = '/proc/' + '/'.join(dirs)

    try:
        with open(path, 'r') as proc_file:
            return proc_file.readlines()
    except (OSError, IOError):
        return None

def get_proc_name(pid):
    """Get the name of the process from the proc file system"""

    cmdline = read_proc_db(pid, 'cmdline')

    return cmdline.split('\x00')[0] if cmdline else 'unknown'

def get_proc_ulimit(pid, name):
    """Return the soft limit value of the given limit"""

    limits = read_proc_db(pid, 'limits')

    if limits:
        for line in limits:
            if line.startswith(name):
                return line.split()[3]

    return 0

if __name__ == '__main__':
    main()
