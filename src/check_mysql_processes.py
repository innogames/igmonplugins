#!/usr/bin/env python
"""InnoGames Monitoring Plugins - check_mysql_process_list.py

This scripts executes SHOW PROCESSLIST and optionally SHOW ENGINE INNODB
STATUS commands on the MySQL server and cross checks the results.  It
implements a domain specific micro language for complicated conditions
to be specified.  Those conditions are allowed multiple times for warning
and critical reporting.  Here are some examples:

--warning=10
    Emit warning for more than 10 processes

--critical=80%
    Emit critical when more than 80% of the max_connections is used

--warning='for 30s'
    Emit warning if a process is in the same state for longer than 30 seconds

--critical='100 on query'
    Emit critical if more than 100 processes are executing a query

--warning='10 on sleep for 1h'
    Emit warning if more than 10 processes are sleeping for more than 1 hour

--critical='50% on query'
    Emit critical if more than 50% of max_connections are executing a query

--warning='50 in transaction'
    Emit warning for more than 50 active InnoDB transactions

--critical='50 in transaction for 1min'
    Emit critical for more than 59 transactions active for longer than 1 minute

--warning='in transaction on sleep for 10 seconds'
    Emit warning for a transaction idle for 10 seconds

Copyright (c) 2017, InnoGames GmbH
"""
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

from argparse import ArgumentParser, ArgumentTypeError, RawTextHelpFormatter
from collections import defaultdict
from operator import itemgetter
from sys import exit
from re import compile as regexp_compile

from MySQLdb import connect


def parse_args():
    parser = ArgumentParser(
        formatter_class=RawTextHelpFormatter, description=__doc__
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
        self.innodb_status = None
        self.txns = None
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

    def get_innodb_status(self):
        if self.innodb_status is None:
            result = self.execute('SHOW ENGINE INNODB STATUS')
            # This is a mess not meant to be parsed.  We will parse it anyway.
            # There must be sections inside with headers separated by lines.
            assert len(result) == 1
            self.innodb_status = defaultdict(list)
            in_header = False
            header = None
            for line in result[0]['status'].splitlines():
                if not line:
                    continue

                # The header start
                if not in_header and all(c == '-' for c in line):
                    if len(line) < 3:
                        raise Exception('Cannot parse InnoDB status')
                    # New header must be the next line.
                    in_header = True
                    header = None
                    continue

                # The header line
                if in_header and not header:
                    if not line.isupper():
                        raise Exception('Cannot parse InnoDB status')
                    header = line
                    continue

                # The header end
                if in_header:
                    assert header
                    if line not in ['-' * len(header), '=' * len(header)]:
                        raise Exception('Cannot parse InnoDB status')
                    in_header = False
                    continue

                self.innodb_status[header].append(line)
        return self.innodb_status

    def get_txn(self, process_id):
        if self.txns is None:
            self.txns = {}
            lines = self.get_innodb_status()['TRANSACTIONS']
            # This is even bigger mess.  We will try to get the transactions
            # anyway.  If you need that far, please do not use a database
            # which doesn't even have a reasonable way to monitor
            # transactions.
            header = None
            for line_id, line in enumerate(lines):
                if line.startswith('---TRANSACTION '):
                    header = line
                    continue
                if header is None:
                    continue
                if not line.startswith('MySQL thread id '):
                    continue
                txn_info = self.parse_transaction_header(header)
                if not txn_info:
                    continue
                txn_id = int(line[len('MySQL thread id '):].split(',', 1)[0])
                self.txns[txn_id] = txn_info

        return self.txns.get(process_id)

    def parse_transaction_header(self, line):
        line = line[len('---TRANSACTION '):]
        txn_id_str, line = line.split(', ', 1)
        if not txn_id_str.isdigit():
            raise Exception('Cannot parse transaction header')
        if txn_id_str == '0' or not line.startswith('ACTIVE '):
            return None
        line_split = line[len('ACTIVE '):].split(None, 2)
        if len(line_split) < 2 or line_split[1] != 'sec':
            raise Exception('Cannot parse transaction header')
        return {
            'txn_id': int(txn_id_str),
            'seconds': int(line_split[0]),
            'state': line_split[2] if len(line_split) >= 3 else None,
        }

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

    def __bool__(self):
        return bool(self.seconds)

    def __nonzero__(self):
        return bool(self.seconds)

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
        '(?P<count_unit>%?)',
        ')?',
        '(?:in',                            # Transaction after separator
        '(?P<txn>transaction)',
        '(?:for',                           # Time clause after separator
        '(?P<txn_time_number>[0-9]+)',
        '(?P<txn_time_unit>{time_units})?'
        ')?',
        ')?',
        '(?:on',                            # Command after separator
        '(?P<command>[a-z ]+?)',
        ')?',
        '(?:for',                           # Time clause after separator
        '(?P<command_time_number>[0-9]+)',
        '(?P<command_time_unit>{time_units})?'
        ')?',
        '\Z',
    ]).format(time_units='|'.join(k for k, v in Interval.units)))

    def __init__(self, arg):
        matches = self.pattern.match(arg)
        if not matches:
            raise ArgumentTypeError('"{}" cannot be parsed'.format(arg))
        self.count_number = int(matches.group('count_number') or 1)
        self.count_unit = matches.group('count_unit')
        self.txn = matches.group('txn')
        self.txn_time = Interval(
            int(matches.group('txn_time_number') or 0),
            matches.group('txn_time_unit') or Interval.units[0][0],
        )
        self.command = matches.group('command')
        self.command_time = Interval(
            int(matches.group('command_time_number') or 0),
            matches.group('command_time_unit') or Interval.units[0][0],
        )

    def __repr__(self):
        return "'{}'".format(self.__str__())

    def __str__(self):
        return str(self.count_number) + self.count_unit + self.get_spec_str()

    def get_spec_str(self):
        spec = ''
        if self.txn:
            spec += ' in {}'.format(self.txn)
        if self.txn_time:
            spec += ' for {}'.format(self.txn_time)
        if self.command:
            spec += ' on {}'.format(self.command)
        if self.command_time:
            spec += ' for {}'.format(self.command_time)
        return spec

    def relative(self):
        return bool(self.count_unit)

    def get_problem(self, db):
        count = 0
        for process in db.get_processes():
            if process['time'] < int(self.command_time):
                if not self.txn_time:
                    break
                continue
            if self.command and process['command'].lower() != self.command:
                continue
            if self.txn:
                txn_info = db.get_txn(process['id'])
                if not txn_info:
                    continue
                if txn_info['seconds'] < int(self.txn_time):
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
        problem = '{} processes{}'.format(count, self.get_spec_str())
        if self.count_number > 1 or self.count_unit:
            problem += ' exceeds ' + str(self.count_number) + self.count_unit
        return problem


if __name__ == '__main__':
    main()
