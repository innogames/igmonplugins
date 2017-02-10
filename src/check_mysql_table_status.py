#!/usr/bin/env python
"""InnoGames Monitoring Plugins - check_mysql_table_status.py

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

from argparse import (
    ArgumentParser, RawTextHelpFormatter, ArgumentDefaultsHelpFormatter
)
from sys import exit

from MySQLdb import connect


def main():
    messages = Checker().get_messages()
    joined_message = join_messages(**messages)

    if messages['critical']:
        print('CRITICAL ' + joined_message)
        exit(2)
    if messages['warning']:
        print('WARNING ' + joined_message)
        exit(1)
    print('OK ' + joined_message)
    exit(0)


def join_messages(critical, warning, ok, performance):
    result = critical + warning
    if not result:
        result += ok
    if performance:
        result += '|' + performance
    return result


class Checker(object):
    """Modes are used to check different values of the tables.  Multiple
    vales can be given comma separated to modes and limits.  K for 10**3,
    M for 10**6, G for 10**9, T for 10**12 units can be used for limits.
    """
    default_modes = 'rows,data_length,index_length'

    def parse_arguments(self):
        def options(value):
            return value.split(',')

        class Formatter (RawTextHelpFormatter, ArgumentDefaultsHelpFormatter):
            pass

        argumentParser = ArgumentParser(
            formatter_class=Formatter, description=self.__doc__
        )
        argumentParser.add_argument(
            '-H', '--host', help='hostname', default='localhost'
        )
        argumentParser.add_argument(
            '-P', '--port', type=int, default=3306
        )
        argumentParser.add_argument(
            '-u', '--user', help='username', default='monitor'
        )
        argumentParser.add_argument(
            '-p', '--passwd', help='password', default=''
        )
        argumentParser.add_argument(
            '-m', '--mode', type=options, default=self.default_modes
        )
        argumentParser.add_argument(
            '-w', '--warning', type=options, help='warning limits')
        argumentParser.add_argument(
            '-c', '--critical', type=options, help='critical limits'
        )
        argumentParser.add_argument(
            '-t', '--tables', type=options, help='show selected tables'
        )
        argumentParser.add_argument(
            '-a', '--all', action='store_true', help='show all tables'
        )
        argumentParser.add_argument(
            '-A', '--average', action='store_true', help='show averages'
        )
        argumentParser.add_argument(
            '-M', '--maximum', action='store_true', help='show maximums'
        )
        argumentParser.add_argument(
            '-N', '--minimum', action='store_true', help='show minimums'
        )
        return argumentParser.parse_args()

    def __init__(self):     # NOQA: C901
        arguments = self.parse_arguments()
        self.attributes = []
        self.outputs = []
        self.database = Database(
            host=arguments.host,
            port=arguments.port,
            user=arguments.user,
            passwd=arguments.passwd,
        )
        for counter, mode in enumerate(arguments.mode):
            self.attributes.append(mode)
            warning_limit = None
            if arguments.warning:
                if counter < len(arguments.warning):
                    warning_limit = Value(arguments.warning[counter])
            critical_limit = None
            if arguments.critical:
                if counter < len(arguments.critical):
                    critical_limit = Value(arguments.critical[counter])
            self.outputs.append(OutputUpperLimit(
                mode, warning_limit, critical_limit))
            if arguments.all:
                self.outputs.append(
                    OutputAll(mode, warning_limit, critical_limit))
            elif arguments.tables:
                self.outputs.append(OutputTables(
                    arguments.tables, mode, warning_limit, critical_limit))
            if arguments.average:
                self.outputs.append(OutputAverage(
                    mode, warning_limit, critical_limit))
            if arguments.maximum:
                self.outputs.append(OutputMaximum(
                    mode, warning_limit, critical_limit))
            if arguments.minimum:
                self.outputs.append(OutputMinimum(
                    mode, warning_limit, critical_limit))

    def join_messages(self, messages):
        result = ''
        for message in messages:
            if message:
                if result:
                    result += ' '
                result += message
        return result

    message_names = ('ok', 'warning', 'critical', 'performance')

    def get_messages(self):
        """Check all tables for all output instances. Return the messages."""
        for table in self.database.yieldTables(self.attributes):
            for output in self.outputs:
                output.check(table)
        messages = {}
        for name in Checker.message_names:
            messages[name] = self.join_messages(
                output.get_message(name) for output in self.outputs
            )
        return messages


class Value(object):
    def __init__(self, value):
        """Parses the value."""
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
            return str(round(self.value / 10 ** 12))[:-2] + 'T'
        if self.value > 10 ** 9:
            return str(round(self.value / 10 ** 9))[:-2] + 'G'
        if self.value > 10 ** 6:
            return str(round(self.value / 10 ** 6))[:-2] + 'M'
        if self.value > 10 ** 3:
            return str(round(self.value / 10 ** 3))[:-2] + 'K'
        return str(self.value)

    def __int__(self):
        """If necessary changes the value to number format."""
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
        return int(self) < int(other)


class Table:
    def __init__(self, schema, name, values):
        self.schema = schema
        self.name = name
        self.values = values

    def __str__(self):
        return self.schema + '.' + self.name

    def get_value(self, name):
        return self.values.get(name)


class Database:
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

    def yieldTables(self, attributes):
        """Iterate tables with selected attributes."""
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
                        values[attribute] = (
                            Value(table_row[position]))
                yield Table(schema_row[0], table_row[0], values)


class Output:
    def __init__(self, attribute, warning_limit=None, critical_limit=None):
        self.attribute = attribute
        self.warning_limit = warning_limit
        self.critical_limit = critical_limit

    def get_performance_data(self, name, value):
        """Format performance data"""
        message = name + '.' + self.attribute + '=' + str(value) + ';'
        if self.warning_limit:
            message += str(int(self.warning_limit))
        message += ';'
        if self.critical_limit:
            message += str(int(self.critical_limit))
        return message + ';0;'


class OutputAll(Output):
    def __init__(self, *args):
        Output.__init__(self, *args)
        self.message = ''

    def add_message(self, table):
        if self.message:
            self.message += ' '
        self.message += self.get_performance_data(
            str(table), int(table.get_value(self.attribute)))

    def check(self, table):
        if table.get_value(self.attribute):
            self.add_message(table)

    def get_message(self, name):
        if name == 'performance':
            return self.message


class OutputTables(OutputAll):
    def __init__(self, table_names, *args):
        OutputAll.__init__(self, *args)
        self.table_names = table_names

    def check(self, table):
        if table.get_value(self.attribute):
            for table_name in self.table_names:
                if table_name == str(table):
                    self.add_message(table)


class OutputUpperLimit(Output):
    def __init__(self, *args):
        Output.__init__(self, *args)
        self.messages = {}

    def add_message(self, name, table, limit):
        if name not in self.messages:
            self.messages[name] = ''
        else:
            self.messages[name] += ' '
        self.messages[name] += str(table) + '.' + self.attribute + ' = '
        self.messages[
            name] += str(table.get_value(self.attribute)) + ' reached '
        self.messages[name] += str(limit) + ';'

    def check(self, table):
        """Check for warning and critical limits"""
        if table.get_value(self.attribute):
            if (
                self.critical_limit and
                table.get_value(self.attribute) > self.critical_limit
            ):
                self.add_message('critical', table, self.critical_limit)
            elif (
                self.warning_limit and
                table.get_value(self.attribute) > self.warning_limit
            ):
                self.add_message('warning', table, self.warning_limit)

    def get_message(self, name):
        return self.messages.get(name)


class OutputAverage(Output):
    def __init__(self, *args):
        Output.__init__(self, *args)
        self.count = 0
        self.total = 0

    def check(self, table):
        """Count tables and sum values for average calculation."""
        if table.get_value(self.attribute):
            self.count += 1
            self.total += int(table.get_value(self.attribute))

    def get_value(self):
        return Value(round(self.total / self.count))

    def get_message(self, name):
        if self.count:
            if name == 'ok':
                return 'average {} = {};'.format(
                    self.attribute, self.get_value()
                )
            if name == 'performance':
                return self.get_performance_data(
                    'average', int(self.get_value())
                )


class OutputMaximum(Output):
    def __init__(self, *args):
        Output.__init__(self, *args)
        self.table = None

    def check(self, table):
        """Get table which has maximum value."""
        value = table.get_value(self.attribute)
        if value and not (
            self.table and value <= self.table.get_value(self.attribute)
        ):
            self.table = table

    def get_message(self, name):
        if self.table:
            if name == 'ok':
                return 'maximum {} = {} for table {};'.format(
                    self.attribute,
                    self.table.get_value(self.attribute),
                    self.table,
                )
            if name == 'performance':
                return self.get_performance_data(
                    'maximum', int(self.table.get_value(self.attribute))
                )


class OutputMinimum(Output):
    def __init__(self, *args):
        Output.__init__(self, *args)
        self.table = None

    def check(self, table):
        """Get table which has minimum value."""
        value = table.get_value(self.attribute)
        if value and not (
            self.table and value >= self.table.get_value(self.attribute)
        ):
            self.table = table

    def get_message(self, name):
        if self.table:
            if name == 'ok':
                return 'minimum {} = {} for table {};'.format(
                    self.attribute,
                    self.table.get_value(self.attribute),
                    self.table,
                )
            if name == 'performance':
                return self.get_performance_data(
                    'minimum', int(self.table.get_value(self.attribute))
                )


if __name__ == '__main__':
    main()
