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

--critical='10 on query at init'
    Emit critical if more than 10 queries are at initialization state

--warning='1 on query for 2s at sending data'
    Emit warning if a query is running for 2 seconds and at sending data state

--critical='50% on query'
    Emit critical if more than 50% of max_connections are executing a query

--warning='50 in transaction'
    Emit warning for more than 50 active InnoDB transactions

--critical='50 in transaction for 1min'
    Emit critical for more than 59 transactions active for longer than 1 minute

--warning='in transaction on sleep for 10 seconds'
    Emit warning for a transaction idle for 10 seconds

--critical='in transaction at starting for 10 seconds'
    Emit critical for a transaction at starting step for longer than 10 seconds

--warning='in transaction at prepared'
    Emit warning for a prepared transaction

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

from mysql.connector import connect


def parse_args():
    parser = ArgumentParser(
        formatter_class=RawTextHelpFormatter, description=__doc__
    )
    parser.add_argument(
        '--host',
        default='localhost',
        help='Target MySQL server (default: %(default)s)'
    )
    parser.add_argument(
        '--unix-socket',
        default='/var/run/mysqld/mysqld.sock',
        help='Target unix socket (default: %(default)s)'
    )
    parser.add_argument(
        '--user',
        help='MySQL user (default: %(default)s)'
    )
    parser.add_argument(
        '--passwd',
        help='MySQL password (default empty)'
    )
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
    connection_kwargs = {}
    if args.host == 'localhost':
        connection_kwargs['unix_socket'] = args.unix_socket
    else:
        connection_kwargs['host'] = args.host
    if args.user:
        connection_kwargs['user'] = args.user
        if args.passwd:
            connection_kwargs['passwd'] = args.passwd
    db = Database(connect(**connection_kwargs))

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
    def __init__(self, connection):
        self.connection = connection
        self.cursor = connection.cursor()
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
                    # New header should be the next line.
                    in_header = True
                    header = None
                    continue

                # The header line
                if in_header and not header:
                    if line.isupper():
                        header = line
                        continue
                    else:
                        # Oh well, it was not header.
                        in_header = False

                # The header end
                if in_header:
                    assert header
                    if not any(all(c == d for c in line) for d in '-='):
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
        if txn_id_str == '0':
            return None

        line_split = line.split()
        if line_split[0] in ['ACTIVE']:
            state = line_split[0]
            line_split = line_split[1:]
        else:
            return None
        if line_split[0].startswith('(') and line_split[0].endswith(')'):
            state = line_split[0][1:-1]
            line_split = line_split[1:]
        if len(line_split) < 2 or line_split[1] not in ['sec', 'sec,']:
            raise Exception('Cannot parse transaction header')
        if state == 'ACTIVE' and len(line_split) > 2:
            state = ' '.join(line_split[2:])

        return {
            'txn_id': int(txn_id_str),
            'seconds': int(line_split[0]),
            'state': state,
        }

    def get_max_connections(self):
        if self.max_connections is None:
            result = self.execute("SHOW VARIABLES LIKE 'max_connections'")
            assert len(result) == 1
            self.max_connections = int(result[0]['value'])
        return self.max_connections

    def get_problems(self, checks):
        return list(filter(bool, (c.get_problem(self) for c in checks)))


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
        # We will iterate the units to choose the most suitable one.
        # The first one is taken as the default.
        for index, (unit, multiplier) in enumerate(self.units):
            if index + 1 == len(self.units):
                # This is the biggest unit.
                continue
            next_multiplier = self.units[index + 1][1]
            if self.seconds > next_multiplier * 10:
                # We will lose some precision, but it is better to use
                # the next one.
                continue
            if self.seconds % next_multiplier == 0:
                # The next one matches nicely.
                continue
            break
        return str(self.seconds // multiplier) + unit


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
        '(?:at',                            # State after separator
        '(?P<txn_state>[a-z ]+?)',
        ')?',
        ')?',
        '(?:on',                            # Command after separator
        '(?P<command>[a-z ]+?)',
        ')?',
        '(?:for',                           # Time clause after separator
        '(?P<command_time_number>[0-9]+)',
        '(?P<command_time_unit>{time_units})?'
        ')?',
        '(?:at',                            # State after separator
        '(?P<command_state>[a-z ]+?)',
        ')?',
        '\Z',
    ]).format(
        time_units='|'.join(k for k, v in Interval.units)
    ))

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
        self.txn_state = matches.group('txn_state')
        self.command = matches.group('command')
        self.command_state = matches.group('command_state')
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
        if self.txn_state:
            spec += ' at {}'.format(self.txn_state)
        if self.command:
            spec += ' on {}'.format(self.command)
        if self.command_time:
            spec += ' for {}'.format(self.command_time)
        if self.command_state:
            spec += ' at {}'.format(self.command_state)
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
            if self.fail_command(process):
                continue
            if self.txn and self.fail_txn(process, db):
                continue
            count += 1

        if count >= self.get_count_limit(db):
            return self.format_problem(count)
        return None

    def fail_command(self, process):
        # Command time is checked by the caller.
        if self.command and process['command'].lower() != self.command:
            return True
        if self.command_state:
            if not process['state'].lower().startswith(self.command_state):
                return True
        return False

    def fail_txn(self, process, db):
        txn_info = db.get_txn(process['id'])
        if not txn_info:
            return True
        if txn_info['seconds'] < int(self.txn_time):
            return True
        if self.txn_state:
            if not txn_info['state'].lower().startswith(self.txn_state):
                return True
        return False

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
