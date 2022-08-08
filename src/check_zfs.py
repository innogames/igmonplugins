#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - ZFS pool status check

Copyright (c) 2020 InnoGames GmbH
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
from subprocess import check_output, STDOUT, CalledProcessError
import sys


def main():
    parser = argparse.ArgumentParser(
        description=(
            'Check raid state, fragmentation and utilisation of ZPools'
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        '--fragmentation-warning',
        help="warning threshold for fragmentation of zpool",
        metavar='percentage',
        type=int, default=30,
    )

    parser.add_argument(
        '--fragmentation-critical',
        help="critical threshold for fragmentation of zpool",
        metavar='percentage',
        type=int, default=50,
    )

    parser.add_argument(
        '--capacity-warning',
        help="twarning hreshold for space utilization of zpool",
        metavar='percentage',
        type=int, default=70,
    )

    parser.add_argument(
        '--capacity-critical',
        help="critical threshold for space utilization of zpool",
        metavar='percentage',
        type=int, default=90,
    )

    args = parser.parse_args()

    try:
        proc = check_output([
            '/sbin/zpool',
            'list',
            '-H',
            '-o', 'name,frag,cap,health'
        ], stderr=STDOUT
        ).decode()
    except OSError as e:
        print('UNKNOWN: can\'t read zpool status: {}'.format(e))
        return ExitCodes.unknown
    except CalledProcessError as e:
        print('UNKNOWN: can\'t read zpool status: {}'.format(e.output))
        return ExitCodes.unknown

    exit_multiline = []
    lines = proc.splitlines()

    if not lines:
        print('No zpools found!')
        return ExitCodes.unknown

    exit_code = ExitCodes.ok
    exit_header = 'All zpools are fine'
    for line in lines:
        zpool_code, zpool_name, zpool_state = parse_zpool(line, args)
        exit_multiline.append('{}: {}'.format(zpool_name, zpool_state))
        if zpool_code > exit_code:
            exit_code = zpool_code
            exit_header = 'Some zpools have issues!'

    print(exit_header)
    if exit_multiline:
        print('\n'.join(exit_multiline))
    return exit_code


def parse_zpool(line, args):
    """
    The output looks like this, with -H there are real tabs separating fields:

    # sudo zpool list -H
    tank\t130T\t75.9T\t54.1T\t-\t22%\t58%\t1.00x\tONLINE\t-
    ...
    """

    data = line.split('\t')
    assert len(data) == 4, "Expected 10 columns from zpool status"

    name = data[0]
    frag = data[1]
    cap = data[2]
    health = data[3]

    ret_code = ExitCodes.ok
    cap = int(cap.split('%')[0])
    frag = int(frag.split('%')[0])

    if (
        health != 'ONLINE' or
        frag > args.fragmentation_warning or
        cap > args.capacity_warning
    ):
        ret_code = ExitCodes.warning

    if (
        frag > args.fragmentation_critical or
        cap > args.capacity_critical
    ):
        ret_code = ExitCodes.critical

    message = 'health: {}, fragmentation: {}%, capacity: {}%'.format(
        health, frag, cap,
    )
    return (ret_code, name, message)


# Nagios plugin exit codes
class ExitCodes:
    ok = 0
    warning = 1
    critical = 2
    unknown = 3


if __name__ == '__main__':
    sys.exit(main())
