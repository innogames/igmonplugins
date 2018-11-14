#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - check_status_codes.py

This is a rather simple check to parse and monitor nginx status codes in
its access log. It calculates an error rate and returns appropriate statuses
whose thresholds are configurable.
It is possible to exclude certain status codes or monitor only certain HTTP
verbs. By default it goes critical when it finds a 504, which can be disabled.

Examples:
    In its simplest form, you can just call it without any arguments:
    ./check_status_codes.py
    This would parse the last 5 minutes from /var/log/nginx/access.log and
    go into warning state if the error rate reaches 10% and critical if it
    reaches 20%.

    Custom log location, only GET requests and ignore 404s:
    ./check_status_codes.py --log /path/to/access.log --verbs GET --ignore 404

    Custom thresholds over the last hour:
    ./check_status_codes.py --warning 0.3 --critical 0.5 --range 3600
"""

# The MIT License (MIT)
#
# Copyright (c) 2018 InnoGames GmbH
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
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser
from time import mktime, strptime, time


def parse_args():
    """Setup CLI interface"""
    p = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)
    p.add_argument('-l', '--log', default='/var/log/nginx/access.log',
                   help='log file to check')
    p.add_argument('-r', '--range', type=int, default=300,
                   help='time range in seconds to take into account')
    p.add_argument('-t', '--time_group', type=int, default=4,
                   help='group number where to find the local time')
    p.add_argument('-q', '--query_group', type=int, default=5,
                   help='group number where to find the request query')
    p.add_argument('-s', '--status_group', type=int, default=6,
                   help='group number where to find the status code')

    p.add_argument('-i', '--ignore', action='append', default=[],
                   help="status codes to ignore, it doesn't matter which "
                        'verbs are monitored')
    p.add_argument('-v', '--verbs', nargs='+',
                   default=['GET', 'POST', 'PUT', 'DELETE'],
                   help='http verbs to monitor')
    p.add_argument('--no-504-critical', action='store_true',
                   help='disable instant critical on 504')
    p.add_argument('-w', '--warning', type=float, default=0.1,
                   help='warning if error ratio raises above configured value')
    p.add_argument('-c', '--critical', type=float, default=0.2,
                   help='critical if error ratio raises above configured '
                        'value')

    return p.parse_args()


def main():
    """Main entry point"""
    args = parse_args()
    runner = Runner(**vars(args))

    status, reason = runner.run()
    code = ExitCodes.get_code(status)

    print('{} | {}'.format(status, reason))
    exit(code)


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


class Runner:
    """Check runner"""

    def __init__(self, log, range, time_group, query_group, status_group,
                 ignore, verbs, no_504_critical, warning, critical):
        self.log = log
        self.range = range
        self.time_group = time_group
        self.query_group = query_group
        self.status_group = status_group
        self.ignore = ignore
        self.no_504_critical = no_504_critical
        self.warning = warning
        self.critical = critical

        self.verbs = []
        for verb in verbs:
            self.verbs.append(verb.upper())

    def run(self):
        """Run the check"""
        codes = {
            'success': 0,
            'error': 0,
            '504': 0,
        }
        now = time()

        # Read file backwards because we only take most recent entries into
        # account, configured in "range"
        with open(self.log) as fd:
            for line in reversed(list(fd)):
                groups = Runner._group(line)
                log_time = self._parse_time(groups)

                # When we reached end of time range we can stop searching.
                if now - self.range > log_time:
                    break

                # Parse and check the HTTP verb.
                verb = groups[self.query_group - 1].split(' ')[0]
                if verb not in self.verbs:
                    continue

                code = groups[self.status_group - 1]
                # Ignore configured status codes.
                if code in self.ignore:
                    continue

                # 504s are a special case here because that typically means the
                # backend is down. We want to go critical here in most cases.
                if code == '504':
                    if not self.no_504_critical:
                        return ExitCodes.CRITICAL, 'Bad Gateway'

                    codes['error'] += 1
                    codes['504'] += 1

                    continue

                # Classify the request.
                c = code[:1]
                if c in ['1', '2', '3']:
                    codes['success'] += 1
                elif c in ['4', '5']:
                    codes['error'] += 1

        return self._summarize(codes)

    @staticmethod
    def _group(line):
        """Parses the groups from the log entry"""
        line = line.rstrip('\n')
        parts = line.split(' ')
        in_group = False
        group = ''
        groups = []

        # Group nginx log output.
        for part in parts:
            prefix = ' ' if in_group else ''

            if (part.startswith('"') and part.endswith('"')) or (
                    part.startswith('[') and part.endswith(']')):
                groups.append(part[1:-1])
            elif part.startswith('"') or part.startswith('['):
                group += prefix + part[1:]
                in_group = True
            elif part.endswith('"') or part.endswith(']'):
                in_group = False
                groups.append(group + prefix + part[:-1])
                group = ''
            elif not in_group:
                groups.append(group + prefix + part)
            else:
                group += prefix + part

        return groups

    def _parse_time(self, groups):
        """Parse nginx local_time"""
        struct_time = strptime(
            groups[self.time_group - 1], '%d/%b/%Y:%H:%M:%S %z'
        )

        return mktime(struct_time)

    def _summarize(self, codes):
        """Summarize our findings and return the code"""
        total = codes['error'] + codes['success']
        ratio = (codes['error'] / total) if total > 0 else 0
        msg = '{} errors out of {} total requests'.format(
            codes['error'], total
        )

        # Return accordingly.
        if ratio >= self.critical:
            return ExitCodes.CRITICAL, msg

        if ratio >= self.warning:
            return ExitCodes.WARNING, msg

        return ExitCodes.OK, msg


if __name__ == '__main__':
    main()
