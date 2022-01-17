#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Linux huge pages check

This script will verify that huge pages are active as configured

Copyright (c) 2022 InnoGames GmbH
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

import sys

from argparse import ArgumentParser


def parse_args():
    parser = ArgumentParser()
    parser.add_argument('--min_value', type=int, required=True,
                        help='The amount of huge pages to expect')
    return parser.parse_args()


def main(args):
    meminfo = read_proc_meminfo()
    if not meminfo:
        print('UNKNOWN - Could not parse /proc/meminfo')
        sys.exit(3)

    meminfo_huge_pages = meminfo['HugePages_Total']

    if int(meminfo_huge_pages) < args.min_value:
        exit_status = 1
        output = (
            f'WARNING - HugePages_Total is {meminfo_huge_pages} '
            f'(<{args.min_value})'
        )
    else:
        exit_status = 0
        output = (
            f'OK - HugePages_Total is {meminfo_huge_pages} '
            f'(>={args.min_value})'
        )

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
    except (OSError, IOError, ValueError):
        return None


if __name__ == '__main__':
    main(parse_args())
