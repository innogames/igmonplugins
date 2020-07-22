#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - JSON Check

This Python Nagios check can validate and compare arbitrary JSON.

The check can either validate JSON string arguments, files and URLs.
To check certain values, JSONPath (http://jsonpath.com/) is used.

Operators: ~=, ==, !=, <=, >=, <, >

Requires:
    jsonpath_rw
    requests
    requests-toolbelt
    validators

Examples:
    To go critical if the status key holds the value DOWN:
    ./check_json.py --source /path/to/json\
        --critical='$.status == DOWN'

    You can additionally warn if status is not UP otherwise:
    ./check_json.py --source /path/to/json\
        --warning='$.status != UP'
        --critical='$.status == DOWN'

    Or go straight critical if status is not UP:
    ./check_json.py --source /path/to/json\
        --critical='$.status != UP'

    To monitor arbitrary metrics:
    ./check_json.py --source /path/to/json\
        --warning='$.value < 20'
        --critical='$.value == 0'

    You can also check values by regex:
    ./check_json.py --source /path/to/json\
        --warning='$.value ~= .* has problems$'\
        --critical='$.value ~= .* is down$'

Copyright (c) 2020 InnoGames GmbH
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
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from enum import Enum
from json import loads, JSONDecodeError
from jsonpath_rw import parse
from os.path import isfile
from re import compile
from requests import RequestException, Session
from requests_toolbelt.adapters import host_header_ssl
from validators import url


def parse_args():
    """Setup CLI interface"""
    parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)

    parser.add_argument('-s', '--source', help='source of json to check')
    parser.add_argument('-t', '--timeout', type=int, default=3000,
                        help='timeout in ms for requests')
    parser.add_argument('--host', help='host in case of ssl verification')
    parser.add_argument('-w', '--warning', action='append',
                        type=Check.from_string, default=[],
                        help='define warning conditions')
    parser.add_argument('-c', '--critical', action='append',
                        type=Check.from_string, default=[],
                        help='define critical conditions')

    return parser.parse_args()


def main():
    """Main entry point"""
    args = parse_args()
    runner = Runner(**vars(args))

    status, reason = runner.run()

    print('{} | {}'.format(status.name, reason))
    exit(status.value)


class ExitCodes(Enum):
    """Nagios exit codes"""
    OK = 0
    WARNING = 1
    CRITICAL = 2
    UNKNOWN = 3


class Check:
    """Check consists of the variable name, operator, and a value"""
    executors = {
        '~=': lambda b: b.match,
        '==': lambda b: lambda a: a == b,
        '!=': lambda b: lambda a: a != b,
        '<=': lambda b: lambda a: a <= b,
        '>=': lambda b: lambda a: a >= b,
        '<': lambda b: lambda a: a < b,
        '>': lambda b: lambda a: a > b,
    }

    def __init__(self, key, operator, value):
        self.key = key
        self.operator = operator
        self.value = value
        self.executor = self.executors[operator](value)

    def __str__(self):
        return '{} {} {}'.format(self.key, self.operator, self.value)

    def __call__(self, data):
        """Execute the check itself"""
        path = parse(self.key)
        matches = path.find(data)

        if not matches:
            return True

        return self.executor(matches[0].value)

    @classmethod
    def from_string(cls, pair):
        """Parse DSL from given arguments"""
        # We have to sort operators by length because otherwise
        # operator > would rule out >= and lead to unexpected behaviour
        for symbol in sorted(cls.executors.keys(), key=len, reverse=True):
            if symbol in pair:
                key, value = pair.split(symbol)
                value = cls.cast(value.strip())

                # if we have a regex operator we can already compile it
                if '~' in symbol:
                    value = compile(value)

                return cls(key.strip(), symbol.strip(), value)

        raise ValueError('Cannot parse {}'.format(pair))

    @staticmethod
    def cast(value):
        """Cast numerical values accordingly"""
        if value.isdigit():
            return int(value)
        if all(v.isdigit() for v in value.split('.', 1)):
            return float(value)
        return value


class Runner:
    """Run the whole thing"""

    def __init__(self, source, timeout, host, warning, critical):
        self.source = source
        self.timeout = timeout
        self.host = host
        self.checks = {
            ExitCodes.WARNING: warning,
            ExitCodes.CRITICAL: critical,
        }

    def load(self):
        """Load input"""
        if isfile(self.source):
            content = self._load_file(self.source)
        elif url(self.source):
            content = self._load_url(self.source, self.timeout, self.host)
        else:
            content = self.source

        if content is None:
            return None

        return loads(content)

    def run(self):
        """Run the checks"""
        try:
            data = self.load()
        except JSONDecodeError:
            return ExitCodes.UNKNOWN, 'Invalid JSON'
        except (RequestException, IOError) as e:
            return ExitCodes.UNKNOWN, 'Could not load data: ' + str(e)

        # if we have criticals, we need to prioritize them, obviously
        for severity in [ExitCodes.CRITICAL, ExitCodes.WARNING]:
            reasons = self._execute_checks(severity, data)

            if reasons:
                return severity, reasons

        return ExitCodes.OK, 'Everything is fine'

    def _execute_checks(self, severity, data):
        """Execute all checks of given severity"""
        reasons = []

        for check in self.checks[severity]:
            if check(data):
                reasons.append(str(check))

        return ', '.join(reasons)

    @staticmethod
    def _load_file(source):
        """Load contents from file"""
        with open(source) as f:
            return f.read()

    @staticmethod
    def _load_url(source, timeout, host):
        """Load contents from URL"""
        headers = {}
        if host:
            headers.update({'HOST': host})

        sess = Session()
        sess.mount('https://', host_header_ssl.HostHeaderSSLAdapter())
        response = sess.get(source, timeout=timeout, headers=headers)

        return response.text if response else None


if __name__ == '__main__':
    main()
