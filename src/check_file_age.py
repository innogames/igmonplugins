#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - File Age Check

This script checks the age of a file and raises a warning or critical state
depending on the thresholds specified as arguments

Copyright 2019 InnoGames GmbH
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

from argparse import ArgumentParser
import os
import time

def main():
    """Main entrypoint, performs check of file age"""

    args = get_parser().parse_args()

    if not args.path:
        print('UNKNOWN - no path supplied')
        exit(3)

    age = 0
    try:
        age = time.time() - os.path.getmtime(args.path)
    except OSError:
        print('UNKNOWN - {} is not present or no permissions'.format(
            args.path))
        exit(3)

    status = 'OK'
    code = 0

    if age > args.critical*60:
        code = 2
        status = 'CRITICAL'
    elif age > args.warning*60:
        code = 1
        status = 'WARNING'

    print('{} - {} last changed {} minutes ago'.format(
        status, args.path, round(age/60)))
    exit(code)


def get_parser():
    """Get argument parser -> ArgumentParser"""

    parser = ArgumentParser()

    parser.add_argument('--path', '-p', help='path of file to check')
    parser.add_argument(
        '--warning', '-w',
        help='warning threshold in minutes for file age',
        default=30, type=int)
    parser.add_argument(
        '--critical', '-c',
        help='critical threshold in minutes for file age',
        default=60, type=int)

    return parser


if __name__ == '__main__':
    main()
