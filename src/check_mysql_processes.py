#!/usr/bin/env python
'''InnoGames Monitoring Plugins - check_mysql_process_list.py

Copyright (c) 2017, InnoGames GmbH
'''
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the 'Software'), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED 'AS IS', WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

from argparse import ArgumentParser, ArgumentTypeError
from operator import itemgetter
from sys import exit
from re import compile as regexp_compile

from MySQLdb import connect

# TODO: Add for select columns (Sleep)


def parse_args():
    parser = ArgumentParser(
        description='Parameters for checking MySQL process list'
    )
    parser.add_argument('--host', default='localhost', help=(
        'Target MySQL server (default: %(default)s)'
    ))
    parser.add_argument('--user', default='user', help=(
        'MySQL user (default: %(default)s)'
    ))
    parser.add_argument('--passwd', default='', help=(
        'MySQL password (default empty)'
    ))
    parser.add_argument(
        '--warning',
        nargs='*',
        type=Check,
        default=[Check('1 for 30s')],
        help='Warning threshold in count and time (default: %(default)s)'
    )
    parser.add_argument(
        '--critical',
        nargs='*',
        type=Check,
        default=[Check('1 for 2min')],
        help='Critical threshold in count and time (default: %(default)s)'
    )

    return parser.parse_args()


def main():
    args = parse_args()
    processes = get_processlist(args.host, args.user, args.passwd)
    # We need to sort the entries to let the check() function stop searching
    # early.
    processes.sort(key=itemgetter('time'), reverse=True)

    if any(c(processes) for c in args.critical):
        exit(ExitCodes.critical)
    if any(c(processes) for c in args.warning):
        exit(ExitCodes.warning)
    exit(ExitCodes.ok)


def get_processlist(host, user, passwd):
    """Return the processes as a list of dicts"""
    try:
        db = connect(host=host, user=user, passwd=passwd)
        try:
            cursor = db.cursor()
            cursor.execute('SHOW PROCESSLIST')
            col_names = [desc[0].lower() for desc in cursor.description]
            return [dict(zip(col_names, r)) for r in cursor.fetchall()]
        finally:
            cursor.close()
    finally:
        db.close()


class ExitCodes:
    ok = 0
    warning = 1
    critical = 2


class Interval:
    units = [
        ('s', 1),
        ('min', 60),            # "m" would mean "metre"
        ('h', 60 * 60),
        ('d', 12 * 60 * 60),
    ]

    def __init__(self, multiplier, unit):
        for key, value in self.units:
            if key == unit:
                break
        else:
            raise Exception('Unit "{}" couldn\'t found'.format(unit))

        self.seconds = multiplier * value

    def __int__(self):
        return self.seconds

    def __str__(self):
        for key, value in reversed(self.units):
            if self.seconds > value:
                break
        return '{}{}'.format(self.seconds / value, key)


class Check:
    pattern = regexp_compile(
        '\A\s*'         # Input start
        '([0-9]+)'      # | Count part
        '(?:'           # | Time part start
        '\s*for\s*'     # | | Time separator
        '([0-9]+)'      # | | Time multiplier
        '({})?'         # | | Time unit
        ')?'            # | Time part end
        '\s*\Z'         # Input end
        .format('|'.join(k for k, v in Interval.units))
    )

    def __init__(self, arg):
        matches = self.pattern.match(arg)
        if not matches:
            raise ArgumentTypeError('"{}" cannot be parsed'.format(arg))
        self.count = int(matches.group(1) or 1)
        self.time = Interval(
            int(matches.group(2) or 0),
            matches.group(3) or Interval.units[0],
        )

    def __repr__(self):
        return '{} for {}'.format(self.count, self.time)

    def __call__(self, processes):
        count = 0
        for process in processes:
            if process['time'] >= int(self.time):
                count += 1
                if count >= self.count:
                    return True
            else:
                break
        return False


if __name__ == '__main__':
    main()
