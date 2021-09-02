#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Check if logfile values defined by regex
are changing.

The script will exit with:
 - 0 (OK) if there are values changes in the last N lines
 - 2 (CRITICAL) if there are no values changes in the last N lines
 - 3 (UNKNOWN) if there are no values or wrong regex
Copyright (c) 2021 InnoGames GmbH
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

import re
import sys
from argparse import ArgumentParser, RawTextHelpFormatter
import subprocess


def parse_args():
    parser = ArgumentParser(
        description=(
            'This Nagios check validates if values (defined by regex)'
            'in log file are changing'
        ),
        formatter_class=RawTextHelpFormatter
    )

    parser.add_argument(
        '--path', help='Path to logfile', type=str
    )

    parser.add_argument(
        '--regex',
        help=(
            'Regex for value to compare. Must contain named group "value", '
            'e.g. v=(?P<value>\d+?)'
        ),
        type=str,
    )

    parser.add_argument(
        '--num', help='Number of last lines to check',
        nargs='?', const=5, type=int, default=5
    )

    return parser.parse_args()


def main():
    args = parse_args()
    logfile_path = args.path
    num = args.num
    lines = tail(logfile_path, num)
    values = set()
    p = re.compile(rf'{args.regex}')

    if 'value' not in p.groupindex:
        print(
            'UNKNOWN - Regex without named group "value" '
            'provided, e.g. v=(?P<value>\d+?)'
        )
        sys.exit(3)

    for line in lines:
        match = p.search(f'{line}')
        if not match:
            continue
        value = match.group('value')
        if value is not None:
            values.add(value)

    if not values:
        print(f'UNKNOWN - No values in {logfile_path} or wrong regex')
        sys.exit(3)

    if len(values) <= 1:
        print(f'CRITICAL - Values in {logfile_path} are not changing')
        sys.exit(2)

    print(f'OK - Values in {logfile_path} are changing')
    sys.exit(0)


def tail(file, lines_num):
    proc = subprocess.Popen(
        ['tail', '-n', f'{lines_num}', file], stdout=subprocess.PIPE
    )
    lines = proc.stdout.readlines()
    return lines


if __name__ == '__main__':
    main()
