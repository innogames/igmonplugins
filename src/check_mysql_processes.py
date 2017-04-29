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
    parser.add_argument('--command', help=(
        'Filter the processes by the command'
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
    database = Database(host=args.host, user=args.user, passwd=args.passwd)
    runner = Runner(database, args.command)
    runner.fetch_processes()

    critical_problems = runner.get_problems(args.critical)
    if critical_problems:
        print('CRITICAL {}'.format(', '.join(critical_problems)))
        exit(ExitCodes.critical)
    warning_problems = runner.get_problems(args.warning)
    if warning_problems:
        print('WARNING {}'.format(', '.join(warning_problems)))
        exit(ExitCodes.warning)
    print('OK')
    exit(ExitCodes.ok)


class Runner:
    def __init__(self, database, command):
        self.database = database
        self.command = command
        self.max_connections = None
        self.processes = None

    def fetch_processes(self, command=None):
        self.processes = self.database.execute('SHOW PROCESSLIST')
        if self.command:
            self.processes = filter(self.filter_process, self.processes)
        # We need to sort the entries to let the check() function stop
        # searching early.
        self.processes.sort(key=itemgetter('time'), reverse=True)

    def filter_process(self, process):
        return self.command == process['command']

    def fetch_max_connections(self):
        result = self.database.execute("SHOW VARIABLES LIKE 'max_connections'")
        assert len(result) == 1
        self.max_connections = int(result[0]['value'])

    def get_problems(self, checks):
        if any(c.relative() for c in checks) and self.max_connections is None:
            self.fetch_max_connections()
        return filter(bool, (
            c(self.processes, self.max_connections) for c in checks)
        )


class Database:
    def __init__(self, **kwargs):
        self.connection = connect(**kwargs)
        self.cursor = self.connection.cursor()

    def __del__(self):
        if self.cursor:
            self.cursor.close()
            self.connection.close()

    def execute(self, statement):
        """Return the results as a list of dicts"""
        self.cursor.execute(statement)
        col_names = [desc[0].lower() for desc in self.cursor.description]
        return [dict(zip(col_names, r)) for r in self.cursor.fetchall()]


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

    def __init__(self, number, unit):
        for key, multiplier in self.units:
            if key == unit:
                break
        else:
            raise Exception('Unit "{}" couldn\'t found'.format(unit))

        self.seconds = number * multiplier

    def __int__(self):
        return self.seconds

    def __str__(self):
        for unit, multiplier in reversed(self.units):
            if self.seconds > multiplier:
                break
        return '{}{}'.format(self.seconds / multiplier, unit)


class Check:
    pattern = regexp_compile(
        '\A\s*'         # Input
        '(?:'           # | Optional count clause
        '([0-9]+)'      # | | Number
        '(%)?'          # | | Optional unit
        ')?'            # | '
        '(?:'           # | Optional time clause
        '\s*for\s*'     # | | Separator
        '([0-9]+)'      # | | Number
        '({})?'         # | | Optional unit
        ')?'            # | '
        '\s*\Z'         # '
        .format('|'.join(k for k, v in Interval.units))
    )

    def __init__(self, arg):
        matches = self.pattern.match(arg)
        if not matches:
            raise ArgumentTypeError('"{}" cannot be parsed'.format(arg))
        self.count_number = int(matches.group(1) or 1)
        self.count_unit = matches.group(2)
        self.time = Interval(
            int(matches.group(3) or 0),
            matches.group(4) or Interval.units[0][0],
        )

    def __repr__(self):
        return '{}{} for {}'.format(
            self.count_number, self.count_unit, self.time
        )

    def relative(self):
        return bool(self.count_unit)

    def __call__(self, processes, max_connections=None):
        count = 0
        for process in processes:
            if process['time'] >= int(self.time):
                count += 1
            else:
                break

        if count >= self.get_count_limit(max_connections):
            return self.format_problem(count)
        return None

    def get_count_limit(self, max_connections=None):
        if not self.relative():
            return self.count_number
        assert max_connections is not None
        return self.count_number * max_connections / 100.0

    def format_problem(self, count):
        problem = '{} processes'.format(count)
        if int(self.time):
            problem += ' longer than {}'.format(self.time)
        if self.count_number > 1 or self.count_unit:
            problem += ' exceeds {}{}'.format(
                self.count_number, self.count_unit
            )
        return problem


if __name__ == '__main__':
    main()
