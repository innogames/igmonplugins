#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - RabbitMQ Check

This is a fully customizable Python Nagios check for RabbitMQ.

The script can check against any available metric that RabbitMQ
provides on its management API. Below you can find a list of available
operators that can be used to define thresholds and filters.
The keys you specify are directly mapped to the JSON response from RabbitMQ.
Nesting keys are separated by a dot (.).

Note you cannot use --overview together with a --filter for obvious reasons.
For a full help page you can invoke the script with --help.

See the following web page for a documentation about RabbitMQ stats:
https://cdn.rawgit.com/rabbitmq/rabbitmq-management/
rabbitmq_v3_6_12/priv/www/doc/stats.html

This check works on both Python 2 and Python 3.

Operators: ~=, ==, !=, <=, >=, <, >

Requires:
    requests

Examples:
    Checks all available queues for the ack rate, if any messages are in them.
    ./check_rabbitmq.py --port 15672 --user guest --password guest\
        --queue '.*'\
        --warning='message_stats.ack_details.rate <= 10'\
        --critical='message_stats.ack_details.rate == 0'\
        --filter='messages > 0'

    Checks a 'notifications' queue and make sure there are always messages in.
    ./check_rabbitmq.py --port 15672 --user guest --password guest\
        --queue 'notifications'\
        --warning='messages <= 10'\
        --critical='messages == 0'

    Checks all queues that are not named 'bla' and put a max messages limit.
    ./check_rabbitmq.py --port 15672 --user guest --password guest\
        --queue '(?!bla).*'\
        --warning='messages >= 100'\
        --critical='messages >= 200'

    Checks the 'test' vhost globally.
    ./check_rabbitmq.py --port 15672 --user guest --password guest\
        --vhost test\
        --warning='messages >= 100'\
        --critical='messages >= 200'

    Checks all numerically-named queues in the 'test' vhost only for data
    of the last 30 seconds.
    ./check_rabbitmq.py --port 15672 --user guest --password guest\
        --vhost test --queue '[0-9]'\
        --warning='message_stats.ack_details.rate <= 100'\
        --critical='message_stats.ack_details.rate == 0'\
        --filter='messages > 0'\
        --length 30

    There is also a special keyword "diff" for all places where samples
    are returned. In contrast to the rate it will then calculate the absolute
    difference between the latest and oldest sample. In this case there must
    have been more than 100 ACKs in the last 30 seconds for an OK state.
    ./check_rabbitmq.py --port 15672 --user guest --password guest\
        --vhost test --queue '[0-9]'\
        --warning='message_stats.ack_details.diff <= 100'\
        --critical='message_stats.ack_details.diff == 0'\
        --filter='messages > 0'\
        --length 30

    You can also have multiple critical, warning and filter statements.
    Critical and warning states are evaluated one after another, reporting
    always the highest severity found. Filters are treated as AND condition,
    meaning all filters have to apply for an entity to be checked.
    ./check_rabbitmq.py --port 15672 --user guest --password guest\
        --vhost test\
        --queue '[0-9]'\
        --warning='message_stats.ack_details.rate <= 100'\
        --warning='message_stats.deliver_details.rate <= 100'\
        --critical='message_stats.ack_details.rate == 0'\
        --critical='message_stats.deliver_details.rate == 0'\
        --filter='messages > 0'\
        --filter='backing_queue_status.mode == lazy'

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

import re
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter

from requests import request, RequestException
from requests.auth import HTTPBasicAuth
from requests.utils import quote


def parse_args():
    """Setup CLI interface"""

    parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)

    parser.add_argument('-H', '--host', default='localhost',
                        help='rabbitmq host')
    parser.add_argument('-p', '--port', type=int, default=15672,
                        help='rabbitmq management port')
    parser.add_argument('-u', '--user', default='guest', help='rabbitmq user')
    parser.add_argument('-P', '--password', default='guest',
                        help='rabbitmq password')
    parser.add_argument('-t', '--timeout', type=int, default=3000,
                        help='timeout in ms for requests')
    parser.add_argument('-l', '--length', type=int, default=300,
                        help='length of rabbitmq data in seconds')
    parser.add_argument('-i', '--incr', type=int, default=30,
                        help='increment of rabbitmq data in seconds')

    parser.add_argument('-v', '--vhost', help='rabbitmq vhost for the check')
    parser.add_argument('-q', '--queue', help='rabbitmq queue for the check')

    parser.add_argument('-w', '--warning', action='append',
                        type=Check.from_string, default=[],
                        help='define warning conditions')
    parser.add_argument('-c', '--critical', action='append',
                        type=Check.from_string, default=[],
                        help='define critical conditions')

    group = parser.add_mutually_exclusive_group()
    group.add_argument('-o', '--overview', action='store_true',
                       help='whether to check the overview instead of '
                            'queue/s or vhost/s')
    group.add_argument('-f', '--filter', action='append',
                       type=Check.from_string, default=[],
                       help='filter entities')

    return parser.parse_args()


def main():
    """Main entry point"""

    args = parse_args()
    runner = Runner(**vars(args))

    status, reason = runner.run()
    code = ExitCodes.get_code(status)

    print('{} - {}'.format(status, reason))

    exit(code)


class RabbitMQException(Exception):
    """Exception for reachability of RabbitMQ"""

    pass


class ExitCodes:
    """Nagios exit codes"""

    OK = 'OK'
    WARNING = 'WARNING'
    CRITICAL = 'CRITICAL'
    UNKNOWN = 'UNKNOWN'

    _code_map = {
        OK: 0,
        WARNING: 1,
        CRITICAL: 2,
        UNKNOWN: 3,
    }

    @classmethod
    def get_code(cls, status):
        """Return the exit code for a written nagios status"""

        status = status.upper()
        if status not in cls._code_map:
            raise RuntimeError('Status "{}" does not exist'.format(status))

        return cls._code_map[status]


class Check:
    """Check consists of the variable name, operator, and a value"""

    executors = {
        '~=': lambda b: re.compile(b).match,
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

        name = data['name'] if 'name' in data else 'overview'

        for part in self.key.split('.'):
            part = part.strip()

            # We also support a special keyword "diff" that calculates the
            # actual sample difference.
            if part == 'diff':
                # Make sure we get what we expect.
                if 'samples' not in data:
                    raise ValueError('No samples are found to calculate diff')

                if len(data['samples']) < 3:
                    raise RabbitMQException(
                        'Expected at least three samples, got {}'.format(
                            len(data['samples']),
                        ),
                    )

                # We receive three samples but ignore the oldest one.
                # Check _build_url for the reasoning.
                samples = data['samples']
                data = samples[0]['sample'] - samples[-2]['sample']
            elif part not in data:
                return None, None, None, None
            else:
                data = data[part]

        return self.executor(data), self, name, data

    def get_reason(self, name):
        """Format a reason text with given entity name"""

        return '{}/{} {} {}'.format(name, self.key, self.operator, self.value)

    @classmethod
    def from_string(cls, pair):
        """Parse DSL from given arguments"""

        for symbol in sorted(cls.executors.keys(), key=len, reverse=True):
            if symbol in pair:
                key, value = pair.split(symbol)
                value = cls.cast(value.strip())

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


class Checker:
    """Executor for checks on RabbitMQ entities"""

    def __init__(self, checks, entities):
        self.checks = checks
        self.entities = entities

    def execute(self):
        """Execute all checks for all RabbitMQ entities"""

        reasons = []
        for entity in self.entities:
            check, name, value = self._execute_checks(entity, self.checks)
            if check:
                reasons.append('{} ({})'.format(check.get_reason(name), value))

        return ', '.join(reasons) if len(reasons) else ''

    @staticmethod
    def _execute_checks(entity, checks):
        """Execute checks on a RabbitMQ entity"""
        for check in checks:
            result, check, name, value = check(entity)

            if result:
                return check, name, value

        return None, None, None


class Gateway:
    """RabbitMQ gateway capable of fetching data from the management API"""

    def __init__(self, base_url='http://localhost:15672/api', auth=None,
                 timeout=3000, length=300, incr=30):
        self.base_url = base_url.rstrip('/')
        self.auth = auth
        self.timeout = timeout
        self.length = length
        self.incr = incr

    def get_overview(self):
        """Fetch the overview from RabbitMQ management API"""

        url = self.base_url + '/overview'

        try:
            response = request('GET', url, auth=self.auth,
                               timeout=self.timeout / 1000)
        except RequestException:
            raise RabbitMQException('Not reachable at {}'
                                    .format(self.base_url))

        if not response:
            raise RabbitMQException('Bad status code at GET {}'.format(url))

        return response.json()

    def get_entities(self, vhost, queue):
        """Fetch requested entities from RabbitMQ management API"""

        entities = []

        if queue:
            # check queue/s of given vhost/s
            url = self._build_url(vhost, queues=True)
            entities = self._get_entities(url, vhost=vhost, queue=queue)
        elif vhost:
            # check whole vhost alone (overview)
            url = self._build_url(vhost)
            entities = self._get_entities(url, vhost=vhost)

        return entities

    def _get_entities(self, url, vhost=None, queue=None):
        """Fetch given entities from pre-crafted url"""

        try:
            response = request('GET', url, auth=self.auth,
                               timeout=self.timeout / 1000)
        except RequestException:
            raise RabbitMQException('Not reachable at {}'.format(
                self.base_url))

        if not response:
            raise RabbitMQException('Bad status code at GET {}'.format(url))

        parsed = response.json()
        matching = []

        for data in parsed:
            pattern = '^{}$'.format(queue if queue is not None else vhost)
            if not re.search(pattern, data['name']):
                continue

            matching.append(data)

        return matching

    def _build_url(self, vhost, queues=False):
        """Build the management api url for the requested entities"""

        url = self.base_url
        if queues:
            url += '/queues'

            if vhost:
                url += '/{}'.format(quote(vhost, safe=''))
        else:
            url += '/vhosts'

        samples = []
        for metric in ['lengths', 'data_rates', 'msg_rates', 'node_stats']:
            # When requesting two samples from RabbitMQ (eg. now and
            # 30 seconds ago), the older sample has an inaccurate value,
            # causing false positives from the check. To get accurate and
            # un-truncated samples, we add the increment to the length as
            # being queried, ending up with one additional sample.
            # We drop the oldest one, since it's inaccurate and older than
            # our selected interval. We can then trust the remaining values.
            incr = min(self.length, self.incr)
            samples.append('{}_age={}'.format(metric, self.length + incr))
            samples.append('{}_incr={}'.format(metric, incr))

        url += '?{}'.format('&'.join(samples))

        return url


class Runner:
    """Run the whole thing"""

    def __init__(self, host, port, user, password, timeout, length, incr,
                 overview, vhost, queue, warning, critical, filter):
        self.timeout = timeout
        self.overview = overview
        self.vhost = vhost
        self.queue = queue
        self.filters = filter
        self.checks = {
            ExitCodes.WARNING: warning,
            ExitCodes.CRITICAL: critical,
        }

        base_url = 'http://{}:{}/api'.format(host, port)
        auth = HTTPBasicAuth(user, password)
        self.gateway = Gateway(
            base_url=base_url,
            auth=auth,
            length=length,
            incr=incr,
        )

    def run(self):
        """Run the checks"""

        # first, get the requested entities from RabbitMQ
        try:
            if self.overview:
                entities = [self.gateway.get_overview()]
            else:
                entities = self.gateway.get_entities(self.vhost, self.queue)
        except RabbitMQException as entity:
            return ExitCodes.CRITICAL, str(entity)

        # if nothing was matched, we assume something is not right
        if not entities:
            return ExitCodes.CRITICAL, 'Found no matching entities'

        # apply filter, if any
        # filters are considered AND-linked
        filtered = []
        for entity in entities:
            for filter_check in self.filters:
                result, _, _, _ = filter_check(entity)

                if not result:
                    break
            else:
                filtered.append(entity)

        # if the filters crossed everything out, there is nothing left to check
        if not filtered:
            return ExitCodes.OK, 'Everything is fine'

        # if we have criticals, we need to prioritize them, obviously
        for severity in [ExitCodes.CRITICAL, ExitCodes.WARNING]:
            checker = Checker(self.checks[severity], filtered)
            reasons = checker.execute()

            if reasons:
                return severity, reasons

        return ExitCodes.OK, 'Everything is fine'


if __name__ == '__main__':
    main()
