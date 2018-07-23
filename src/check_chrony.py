#!/usr/bin/env python
#
# InnoGames Monitoring Plugins - check_chrony.py
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

from subprocess import check_output, STDOUT
from argparse import ArgumentParser
from sys import exit
import re
import platform


# Nagios plugin exit codes
class ExitCodes:
    ok = 0
    warning = 1
    critical = 2
    unknown = 3


MULTIPLIERS = {
    's': 1,
    'ms': 0.001,
    'us': 0.000001,
    'ns': 0.000000001,
}


def main():
    parser = ArgumentParser(
        description=(
            'Check time difference between local Chrony deamon '
            'and its NTP peers'
        )
    )
    parser.add_argument(
        '-w', dest='warning',  type=float, required=True,
        help="Time difference in seconds for Warning state"
    )
    parser.add_argument(
        '-c', dest='critical', type=float, required=True,
        help="Time difference in seconds for Critical state"
    )
    args = parser.parse_args()

    if platform.system() == 'FreeBSD':
        chrony = '/usr/local/bin/chronyc'
    else:
        chrony = '/usr/bin/chronyc'

    try:
        proc = check_output(
            [chrony, '-n', 'sources'],
            stderr=STDOUT,
        ).decode()
    except OSError as e:
        print('UNKNOWN: can\'t read Chrony status: {}'.format(e))
        return ExitCodes.unknown
    exit_code = ExitCodes.ok
    peers_found = False
    stats_found = False
    for line in proc.split('\n'):
        if line:
            # Chrony on Debian Jessie does not support `-c` parameter.
            # No CSV output for us, we must parse text.
            if line.startswith('======='):
                stats_found = True
                continue
            if not stats_found:
                continue
            line = line.split()
            local_exit_code = ExitCodes.ok
            local_exit_string = 'OK'
            time_diff = re.match('[\+\-]([0-9]+)([a-z]s)', line[6])
            if time_diff:
                time_diff = time_diff.groups()
                time_nice = time_diff[0] + time_diff[1]
                time_diff = float(time_diff[0]) * MULTIPLIERS[time_diff[1]]
                if time_diff > args.warning:
                    local_exit_code = ExitCodes.warning
                    local_exit_string = 'WARNING'
                if time_diff > args.critical:
                    local_exit_code = ExitCodes.critical
                    local_exit_string = 'CRITICAL'
                print('{}: peer {} time offset {}'.format(
                    local_exit_string, line[1], time_nice,
                    ))
                exit_code = max(exit_code, local_exit_code)
                peers_found = True

    if not peers_found:
        print('UNKNOWN: no peers found!')
        return ExitCodes.unknown

    return exit_code


if __name__ == '__main__':
    exit(main())
