#!/usr/bin/env python
"""InnoGames Monitoring Plugins - Linux mem free check

This script will read /proc/meminfo and calculate the sum of:
* MemFree
* SwapFree
* Cached

Will raise a warning/critical if a certain percentage or absolute value
is reached.

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
import os
import sys


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description=(
            'Calculate the sum of MemFree, SwapFree and Cached. '
            'Raise a warning or critical if the threshold is undercut.'
        ),
    )
    # Our systems usually run with 1 GiB of swap.
    # Raise a warning if the amount of free memory drops below 768 MiB
    parser.add_argument(
        '-w',
        '--warning',
        metavar='warning',
        type=str,
        default=str(768*1024*1024),  # 768 MiB
        help=(
            'Expects an absolute value in bytes or a percentage of '
            'total memory (suffixed with %%)! '
            'Raise a warning if this limit is exceeded. '
        ),
    )
    # Raise a critical error if amount of free memory drops below 512 MiB
    parser.add_argument(
        '-c',
        '--critical',
        metavar='critical',
        type=str,
        default=str(512*1024*1024),  # 512 MiB
        help=(
            'Expects an absolute value in bytes or a percentage of '
            'total memory (suffixed with %%)! '
            'Raise a warning if this limit is exceeded.'
        ),
    )
    args = parser.parse_args()

    args.warning_percent = args.warning.endswith('%')
    args.critical_percent = args.critical.endswith('%')
    args.warning = int(args.warning.rstrip('%'))
    args.critical = int(args.critical.rstrip('%'))
    return args


def main():
    args = parse_args()

    meminfo = read_proc_meminfo()
    if not meminfo:
        print('Could not parse /proc/meminfo')
        sys.exit(3)

    mem_free_kib = meminfo['MemFree'] + meminfo['SwapFree'] + meminfo['Cached']
    mem_total_kib = meminfo['MemTotal'] + meminfo['SwapTotal']

    output = (
        'Memory low! Please increase memory! (MemFree + SwapFree + Cached) '
        '< {:,} MiB'.format(mem_free_kib >> 10)
    )
    exit_status = 3

    crit_value = (mem_free_kib << 10) / args.critical
    crit_factor = (mem_total_kib << 10) / 100 if args.critical_percent else 1
    warn_value = (mem_free_kib << 10) / args.warning
    warn_factor = (mem_total_kib << 10) / 100 if args.warning_percent else 1
    if crit_value < crit_factor:
        exit_status = 2
    elif warn_value < warn_factor:
        exit_status = 1
    else:
        output = 'There is enough free memory :aw_yeah:'
        exit_status = 0

    print(output)
    sys.exit(exit_status)


def read_proc_meminfo():
    """Return /proc/meminfo as a dict"""
    meminfo_dict = {}
    try:
        with open('/proc/meminfo', 'r') as proc_file:
            for line in proc_file.readlines():
                name, value = line.strip().replace(' kB', '').split(':', 1)
                meminfo_dict[name] = int(value)
            return meminfo_dict
    except (OSError, IOError):
        return None


if __name__ == '__main__':
    main()
