#!/usr/bin/env python
#
# InnoGames Monitoring Plugins - check_linux_ulimit.py
#
# This script intended to check user limits on Linux.  It is currently
# only checking the open file limit.
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

import os
import sys
import argparse


class ExitCodes:
    """Enum for Nagios compatible exit codes

    We are not including a code for unknown in here.  Anything other
    than those two are considered as unknown.  It is easier to threat
    unknown as None on Python rather than giving it a number greater
    than 2, because None is less than all of those.
    """
    ok = 0
    warning = 1
    critical = 2


def main():
    """The main program"""
    parser = argparse.ArgumentParser(
        description=(
            'Check all running processes for the nofile limit, will throw '
            'a warning if the limit is nearly reached and critical, if '
            'the limit is reached'
        ),
    )
    parser.add_argument(
        '-w',
        '--warning',
        metavar='warning',
        type=int,
        default=60,
        help=(
            'Percentage of the limit which may be reached until a warning is '
            'thrown.  If -w is 99 and the nofile limit is at 1000 the warning '
            'will occur, if 990 ore more files are opened.'
        ),
    )
    args = parser.parse_args()

    if os.getuid() != 0:
        raise Exception('I need to be run as root, really')

    exit(*get_state(int(args.warning) / 100))


def get_state(warning_ratio):
    """The main logic of the check"""

    assert 0 <= warning_ratio <= 1

    state = None    # None is less than everything
    msg = ''

    for pid in list_proc_db():

        # The are some other files under the proc file system.  If
        # the directory name is not a digit, it cannot be a process.
        if not pid.isdigit():
            continue

        soft_limit = get_proc_ulimit(pid, 'Max open files')

        # soft_limit 0 means actually not set (during fork etc)
        if soft_limit == 0:
            continue

        num_fds = len(list_proc_db(pid, 'fd'))

        if num_fds >= soft_limit:
            state = ExitCodes.critical
            msg += (
                'PID {0} [{1}] reached its soft limit (open: {2}, limit {3})\n'
                .format(pid, get_proc_name(pid), num_fds, soft_limit)
            )
        elif num_fds >= soft_limit * warning_ratio:
            state = max(state, ExitCodes.warning)
            msg += (
                'PID {0} [{1}] nearly reached its soft limit at {2} open fds\n'
                .format(pid, get_proc_name(pid), num_fds)
            )
        else:
            state = max(state, ExitCodes.ok)

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


def exit(exit_code=None, message=''):
    """Exit procedure for the check commands"""
    if exit_code == ExitCodes.ok:
        status = 'OK'
    elif exit_code == ExitCodes.warning:
        status = 'WARNING'
    elif exit_code == ExitCodes.critical:
        status = 'CRITICAL'
    else:
        status = 'UNKNOWN'
        exit_code = 3

        # People tend to interpret UNKNOWN status in different ways.
        # We are including a default message to avoid confusion.  When
        # there are specific problems, errors, the message should be
        # set.
        if not message:
            message = 'Nothing could be checked'

    print(status, message)
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
