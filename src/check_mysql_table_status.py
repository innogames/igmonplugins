#!/usr/bin/env python
"""InnoGames Monitoring Plugins - check_mysql_table_status.py

Modes are used to check different values of the tables.  Multiple
vales can be given comma separated to modes and limits.  K for 10**3,
M for 10**6, G for 10**9, T for 10**12 units can be used for limits.

Copyright (c) 2013, Tart Internet Teknolojileri Ticaret AS
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

from argparse import ArgumentParser, RawTextHelpFormatter
from sys import exit

from MySQLdb import connect

DEFAULT_MODES = ['rows', 'data_length', 'index_length']
MESSAGE_TYPES = ['ok', 'warning', 'critical', 'perf']
MESSAGE_SEPARATOR = '; '


def parse_arguments():
    def options(value):
        return value.split(',')

    parser = ArgumentParser(
        formatter_class=RawTextHelpFormatter, description=__doc__
    )
    parser.add_argument('--host', help='hostname', default='localhost')
    parser.add_argument('--port', type=int, default=3306)
    parser.add_argument('--user', help='username')
    parser.add_argument('--passwd', help='password')
    parser.add_argument('--modes', type=options, default=DEFAULT_MODES)
    parser.add_argument('--warnings', type=options, help='warning limits')
    parser.add_argument('--criticals', type=options, help='critical limits')
    parser.add_argument('--tables', type=options, help='show selected tables')
    parser.add_argument('--perf', action='store_true', help='performance data')
    parser.add_argument('--avg', action='store_true', help='show averages')
    parser.add_argument('--max', action='store_true', help='show maximums')
    parser.add_argument('--min', action='store_true', help='show minimums')

    return parser.parse_args()


def main():
    arguments = parse_arguments()
    database = Database(**{
        k: v for k, v in vars(arguments).items()
        if k in ('host', 'port', 'user', 'passwd') and v is not None
    })
    output_classes = [OutputTables]
    if arguments.avg:
        output_classes.append(OutputAvg)
    if arguments.max:
        output_classes.append(OutputMax)
    if arguments.min:
        output_classes.append(OutputMin)
    outputs = get_outputs(
        output_classes,
        arguments.modes,
        arguments.warnings,
        arguments.criticals,
        arguments.perf,
    )
    messages = get_messages(database, arguments.modes, list(outputs))
    joined_message = join_messages(**messages)

    if messages['critical']:
        print('CRITICAL ' + joined_message)
        exit(2)
    if messages['warning']:
        print('WARNING ' + joined_message)
        exit(1)
    print('OK ' + joined_message)
    exit(0)


def get_outputs(output_classes, modes, warnings, criticals, perf):
    for seq, mode in enumerate(modes):
        warning_limit = (
            Value(warnings[seq])
            if warnings and seq < len(warnings) and warnings[seq]
            else None
        )
        critical_limit = (
            Value(criticals[seq])
            if criticals and seq < len(criticals) and criticals[seq]
            else None
        )
        for output_class in output_classes:
            yield output_class(mode, warning_limit, critical_limit, perf)


def get_messages(database, attributes, outputs):
    """Check all tables for all output instances"""
    for table, values in database.get_table_values(attributes):
        for output in outputs:
            if output.attribute in values:
                output.check(table, values[output.attribute])

    messages = {}
    for message_type in MESSAGE_TYPES:
        messages[message_type] = MESSAGE_SEPARATOR.join(filter(bool, (
            o.get_message(message_type) for o in outputs if o
        )))

    return messages


def join_messages(critical, warning, ok, perf):
    result = critical + warning
    if not result:
        result += ok
    if perf:
        result += ' | ' + perf
    return result


class Value(object):
    def __init__(self, value):
        """Parse the value"""
        if str(value)[-1:] in ['K', 'M', 'G', 'T']:
            self.value = int(value[:-1])
            self.unit = value[-1:]
        else:
            self.value = int(value)
            self.unit = None

    def __str__(self):
        """If necessary change the value to number + unit format by rounding"""
        if self.unit:
            return str(self.value) + self.unit
        if self.value > 10 ** 12:
            return str(int(round(self.value / 10 ** 12))) + 'T'
        if self.value > 10 ** 9:
            return str(int(round(self.value / 10 ** 9))) + 'G'
        if self.value > 10 ** 6:
            return str(int(round(self.value / 10 ** 6))) + 'M'
        if self.value > 10 ** 3:
            return str(int(round(self.value / 10 ** 3))) + 'K'
        return str(self.value)

    def __int__(self):
        """If necessary change the value to number format"""
        if self.unit == 'K':
            return self.value * 10 ** 3
        if self.unit == 'M':
            return self.value * 10 ** 6
        if self.unit == 'G':
            return self.value * 10 ** 9
        if self.unit == 'T':
            return self.value * 10 ** 12
        return self.value

    def __lt__(self, other):
        return other is not None and int(self) < int(other)

    def __gt__(self, other):
        return other is not None and int(self) > int(other)


class Database(object):
    def __init__(self, **kwargs):
        self.connection = connect(**kwargs)
        self.cursor = self.connection.cursor()

    def __del__(self):
        if self.cursor:
            self.cursor.close()
            self.connection.close()

    def select(self, query):
        self.cursor.execute(query)
        return self.cursor.fetchall()

    def get_column_position(self, name):
        column = [desc[0] for desc in self.cursor.description]
        for position, column in enumerate(column):
            if column.lower() == name.lower():
                return position

    def get_table_values(self, attributes):
        """Iterate tables with selected attributes"""
        for schema_row in self.select('SHOW SCHEMAS'):
            query = (
                'SHOW TABLE STATUS IN `{}` WHERE Engine IS NOT NULL'
                .format(schema_row[0])
            )
            for table_row in self.select(query):
                values = {}
                for attribute in attributes:
                    position = self.get_column_position(attribute)
                    if table_row[position]:
                        values[attribute] = Value(table_row[position])
                yield '{}.{}'.format(schema_row[0], table_row[0]), values


class Output(object):
    def __init__(self, attribute, warning_limit, critical_limit, perf):
        self.attribute = attribute
        self.warning_limit = warning_limit
        self.critical_limit = critical_limit
        self.perf = perf

    def format_perf_message(self, name, value):
        return '{}.{}={};{};{};'.format(
            name,
            self.attribute,
            int(value),
            int(self.warning_limit) if self.warning_limit else '',
            int(self.critical_limit) if self.critical_limit else '',
        )


class OutputTables(Output):
    def __init__(self, *args):
        Output.__init__(self, *args)
        self.messages = {
            'ok': [],
            'warning': [],
            'critical': [],
            'perf': [],
        }

    def check(self, table, value):
        """Check for warning and critical limits"""
        if self.critical_limit and value > self.critical_limit:
            self.messages['critical'].append(
                self.format_message(table, value, self.critical_limit)
            )
        elif self.warning_limit and value > self.warning_limit:
            self.messages['warning'].append(
                self.format_message(table, value, self.warning_limit)
            )
        if self.perf:
            self.messages['perf'].append(
                self.format_perf_message(table, value)
            )

    def format_message(self, table, value, limit):
        return '{}.{} is {} reached {}'.format(
            table, self.attribute, value, limit
        )

    def get_message(self, name):
        return MESSAGE_SEPARATOR.join(self.messages[name])


class OutputAvg(Output):
    def __init__(self, *args):
        Output.__init__(self, *args)
        self.count = 0
        self.total = 0

    def check(self, table, value):
        """Count tables and sum values for average calculation"""
        self.count += 1
        self.total += int(value)

    def get_value(self):
        return Value(round(self.total / self.count))

    def get_message(self, name):
        if name == 'ok':
            return 'average {} = {};'.format(
                self.attribute, self.get_value()
            )
        if name == 'perf':
            return self.format_perf_message('average', int(self.get_value()))


class OutputMax(Output):
    def __init__(self, *args):
        Output.__init__(self, *args)
        self.table = None
        self.value = None

    def check(self, table, value):
        """Get table which has maximum value"""
        if not self.value or value > self.value:
            self.table = table
            self.value = value

    def get_message(self, name):
        if self.table:
            if name == 'ok':
                return 'maximum {} = {} for table {}'.format(
                    self.attribute, self.value, self.table
                )
            if name == 'perf':
                return self.format_perf_message('maximum', self.value)


class OutputMin(Output):
    def __init__(self, *args):
        Output.__init__(self, *args)
        self.table = None
        self.value = None

    def check(self, table, value):
        """Get table which has minimum value"""
        if not self.value or self.value > value:
            self.table = table
            self.value = value

    def get_message(self, name):
        if self.table:
            if name == 'ok':
                return 'minimum {} = {} for table {}'.format(
                    self.attribute, self.value, self.table
                )
            if name == 'perf':
                return self.format_perf_message('minimum', self.value)


if __name__ == '__main__':
    main()
