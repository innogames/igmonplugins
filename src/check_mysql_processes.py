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

from argparse import ArgumentParser
from operator import itemgetter
from sys import exit
import re

from MySQLdb import connect

# TODO: Add verbose input for timestamps (1H, 30S, ...)
# TODO: Add for select columns (Sleep)


class ExitCodes:
    ok = 0
    warning = 1
    critical = 2


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
    parser.add_argument('--warning', nargs='*', default=['1 for 30'], help=(
        'Number of occasions with number seconds before a warning is given '
        '(default: %(default)s)'
    ))
    parser.add_argument(
        '--critical', nargs='*', default=['1 for 120'], help=(
            'Number of occasions with number seconds before situation is '
            'critical (default: %(default)s)'
        )
    )

    return parser.parse_args()


def main():
    args = parse_args()
    processes = get_processlist()
    # We need to sort the entries to let the check() function stop searching
    # early.
    processes.sort(key=itemgetter('time'), reverse=True)

    if args.critical and check(args.critical, processes):
        exit(ExitCodes.critical)
    if check(args.warning, processes):
        exit(ExitCodes.warning)
    exit(ExitCodes.ok)


def get_processlist():
    """Return the processes as a list of dicts"""
    args = parse_args()
    try:
        db = connect(host=args.host, user=args.user, passwd=args.passwd)
        try:
            cursor = db.cursor()
            cursor.execute('SHOW PROCESSLIST')
            col_names = [desc[0].lower() for desc in cursor.description]
            return [dict(zip(col_names, r)) for r in cursor.fetchall()]
        finally:
            cursor.close()
    finally:
        db.close()


def check(args, processes):
    reg_pattern = '^([0-9]*).*?([0-9]*)$'
    for condition in args:
        match_array = re.match(reg_pattern, condition)
        counts_needed = int(match_array.group(1))
        count = 0
        for process in processes:
            time = int(process['time'])
            if time >= int(match_array.group(2)):
                count += 1
                if count >= counts_needed:
                    return True
            else:
                break
    return False


if __name__ == '__main__':
    main()
