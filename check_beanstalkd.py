#!/usr/bin/env python
#
# InnoGames Monitoring Plugins - check_beanstalkd.py
#
# Copyright (c) 2016, InnoGames GmbH
#
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
#

import re
import sys
import socket

from argparse import ArgumentParser


def parse_args():
    parser = ArgumentParser()
    parser.add_argument(
        '--host',
        default='localhost',
        help='The hostname',)
    parser.add_argument(
        '--port',
        default=11300,
        type=int,
        help='The port number',
    )
    parser.add_argument(
        '--timeout',
        default=2,
        type=int,
        help='The connection timeout in seconds',
    )
    parser.add_argument(
        'checks',
        metavar='CHECK',
        nargs='*',
        help=(
            'The check consist of the name of the metric, the operator, '
            'the warning and the critical limits separated by a double '
            'column (:).  The operator can be less than (<) or grater '
            'than (>).  The same metric can be used multiple times '
            'with different operators.  The critical limit is optional. '
            'This is an example "current-connections>100:10000".  This '
            'is the regular expression: "{0}".  '
            "Don't forget to quote the arguments on shell."
        ).format(Check.parser.pattern),
    )

    return vars(parser.parse_args())


def main(checks, **kwargs):
    """The main program
    """

    status, output = run(Check(c) for c in checks, **kwargs)

    print(status + ' ' + output)

    if status == 'OK':
        sys.exit(0)
    elif status == 'WARNING':
        sys.exit(1)
    elif status == 'CRITICAL':
        sys.exit(2)
    else:
        sys.exit(3)


def run(checks, **kwargs):
    """The main part of the program

    Parse the stats from beanstalkd.  Run the checks, if they are
    available.
    """

    try:
        response = read_stats(**kwargs)
    except socket.error as error:
        return 'CRITICAL', 'Error connecting to beanstalkd: ' + str(error)

    lines = response.splitlines()[2:-1]
    if len(lines) <= 3:
        return 'CRITICAL', "Couldn't get stats from beanstalkd: " + lines[0]

    stats = {}
    for line in lines:
        if ': ' in line:
            key, value = line.split(': ')
            stats[key] = value
        else:
            return 'UNKNOWN', 'Error parsing stats: ' + line

    warns = []
    crits = []
    perfs = set()
    for check in checks:
        if check.metric in stats:
            value = int(stats[check.metric])
            perfs.add('{0}={1}'.format(check.metric, value))

            if check.test(value, check.crit_limit):
                crits.append(check.get_message(value, check.crit_limit))
            elif check.test(value, check.warn_limit):
                warns.append(check.get_message(value, check.warn_limit))
        else:
            return 'UNKNOWN', "Metric {0} couldn't found.".format(check.metric)

    if crits:
        return 'CRITICAL', '; '.join(crits + warns) + '. | ' + ' '.join(perfs)
    if warns:
        return 'WARNING', '; '.join(warns) + '. | ' + ' '.join(perfs)
    return 'OK', 'Everything is okay. | ' + ' '.join(perfs)


def read_stats(host, port, timeout):
    """Read the stats from the local Beanstalkd service

    Beanstalkd implements Memcached like simple TCP plain text protocol.
    It is enough to send "stats" request to it to get the metrics.  It is
    capable of handling multiple requests with a single connection, so
    the connection will remain open after the response.  It also returns
    the length of the response for us to know how many bytes we need to
    read.  Thought, we won't bother with those details.  We don't need to
    reuse the connection.  We will fetch 4096 bytes which is more than
    enough for the stats.

    We want to make sure that the connection is closed in any case and
    the program wouldn't hang waiting for the server to respond.  We will use
    2 second timeout to achieve this.
    """

    conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        conn.settimeout(timeout)
        conn.connect((host, port))
        conn.send('stats\r\n')
        return conn.recv(4096)
    finally:
        conn.close()


class Check(object):
    parser = re.compile(
        r'^(?P<metric>[a-z\-]+)'
        r'(?P<operator><|>)'
        r'(?P<warn_limit>[0-9]+)'
        r'(:(?P<crit_limit>[0-9]+))?'
    )

    def __init__(self, check_str):
        matches = self.parser.match(check_str)
        if not matches:
            raise ValueError('Cannot parse check ' + check_str)
        self.metric = matches.group('metric')
        self.operator = matches.group('operator')
        self.warn_limit = int(matches.group('warn_limit'))
        self.crit_limit = int(matches.group('crit_limit') or 0)
        if self.crit_limit and self.test(self.warn_limit, self.crit_limit):
            raise ValueError(
                'Critical limit is more restrictive than warning for check ' +
                check_str
            )

    def test(self, value, limit):
        if self.operator == '<':
            return value < limit
        else:
            return value > limit

    def get_message(self, value, limit):
        if self.operator == '<':
            operator_str = 'less than'
        else:
            operator_str = 'greater than'

        return '{0} is {1} {2} {3}'.format(
            self.metric, value, operator_str, limit
        )


if __name__ == '__main__':
    main(**parse_args())
