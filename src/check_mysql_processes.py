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
    db = Database(host=args.host, user=args.user, passwd=args.passwd)

    critical_problems = db.get_problems(args.critical)
    if critical_problems:
        print('CRITICAL {}'.format(', '.join(critical_problems)))
        exit(ExitCodes.critical)
    warning_problems = db.get_problems(args.warning)
    if warning_problems:
        print('WARNING {}'.format(', '.join(warning_problems)))
        exit(ExitCodes.warning)
    print('OK')
    exit(ExitCodes.ok)


class Database:
    def __init__(self, **kwargs):
        self.connection = connect(**kwargs)
        self.cursor = self.connection.cursor()
        self.processes = None
        self.max_connections = None

    def execute(self, statement):
        """Return the results as a list of dicts"""
        self.cursor.execute(statement)
        col_names = [desc[0].lower() for desc in self.cursor.description]
        return [dict(zip(col_names, r)) for r in self.cursor.fetchall()]

    def get_processes(self):
        if self.processes is None:
            self.processes = self.execute('SHOW PROCESSLIST')
            # We need to sort the entries to let the check() function stop
            # searching early.
            self.processes.sort(key=itemgetter('time'), reverse=True)
        return self.processes

    def get_max_connections(self):
        if self.max_connections is None:
            result = self.execute("SHOW VARIABLES LIKE 'max_connections'")
            assert len(result) == 1
            self.max_connections = int(result[0]['value'])
        return self.max_connections

    def get_problems(self, checks):
        return filter(bool, (c.get_problem(self) for c in checks))


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
    pattern = regexp_compile('\s*'.join([   # Allow spaces between everything
        '\A',
        '(?:',                              # Count clause
        '(?P<count_number>[0-9]+)',
        '(?P<count_unit>%)?',
        ')?',
        '(?:on',                            # Command after separator
        '(?P<command>[a-z ]+?)',
        ')?',
        '(?:for',                           # Time clause after separator
        '(?P<time_number>[0-9]+)',
        '(?P<time_unit>{})?'
        .format('|'.join(k for k, v in Interval.units)),
        ')?',
        '\Z',
    ]))

    def __init__(self, arg):
        matches = self.pattern.match(arg)
        if not matches:
            raise ArgumentTypeError('"{}" cannot be parsed'.format(arg))
        self.count_number = int(matches.group('count_number') or 1)
        self.count_unit = matches.group('count_unit')
        self.command = matches.group('command')
        self.time = Interval(
            int(matches.group('time_number') or 0),
            matches.group('time_unit') or Interval.units[0][0],
        )

    def __repr__(self):
        return '{}{} for {}'.format(
            self.count_number, self.count_unit, self.time
        )

    def relative(self):
        return bool(self.count_unit)

    def get_problem(self, db):
        count = 0
        for process in db.get_processes():
            if process['time'] < int(self.time):
                break
            if self.command and process['command'].lower() != self.command:
                continue
            count += 1

        if count >= self.get_count_limit(db):
            return self.format_problem(count)
        return None

    def get_count_limit(self, db):
        if not self.relative():
            return self.count_number
        return self.count_number * db.get_max_connections() / 100.0

    def format_problem(self, count):
        problem = '{} processes'.format(count)
        if self.command:
            problem += ' on {}'.format(self.command)
        if int(self.time):
            problem += ' longer than {}'.format(self.time)
        if self.count_number > 1 or self.count_unit:
            problem += ' exceeds {}{}'.format(
                self.count_number, self.count_unit
            )
        return problem


if __name__ == '__main__':
    main()
