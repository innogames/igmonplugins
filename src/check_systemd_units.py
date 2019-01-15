#!/usr/bin/env python
"""InnoGames Monitoring Plugins - Systemd Units Check

This is a Nagios script to check all or some units of "systemd".
It checks for anomalies of those units like the ones not anymore
defined but still running, and them being inactive.  Normally returns
at most warning, if no critical units are specified.  Returns

It returns:

* Critical when a critical unit is failed
* Warning when a critical unit is not running
* Warning when a non-critical unit is failed
* Warning for other anomalies

Copyright (c) 2018 InnoGames GmbH
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

from argparse import ArgumentParser
from sys import exit
from time import time

from systemd_dbus.exceptions import SystemdError
from systemd_dbus.manager import Manager
from systemd_dbus.service import Service
from systemd_dbus.timer import Timer


class Problem:
    """Enum for problems that can apply to the units"""

    # From more important to less
    failed = 0
    timer_missed_critical = 1
    not_loaded_but_not_inactive = 2
    inactive = 3
    timer_missed_warning = 4
    exited = 5
    not_loaded = 6


class SystemdUnit:
    """Systemd unit"""

    def __init__(self, unit):
        self.properties = unit.properties
        self.unit_type = unit.properties.Id.rsplit('.', 1)[-1]
        # TODO: Don't access the private properties after the library
        # provides a way
        self.dbus_path = unit._Unit__proxy.__dbus_object_path__

    def __str__(self):
        return str(self.properties.Id)

    @property
    def specific_properties(self):
        if self.unit_type == 'service':
            cls = Service
        elif self.unit_type == 'timer':
            cls = Timer

        return cls(self.dbus_path).properties

    def match(self, pattern):
        name = str(self)
        if pattern.endswith('@*') and '@' in name:
            return pattern[:-len('@*')] == name.split('@', 1)[0]
        return pattern == name

    def check(self, args):
        """Detect problems of a unit"""
        if self.properties.LoadState != 'loaded':
            if self.properties.ActiveState != 'inactive':
                return Problem.not_loaded_but_not_inactive
            return Problem.not_loaded

        if self.properties.ActiveState == 'failed':
            return Problem.failed

        if self.unit_type == 'timer':
            return self._check_timer(args)
        elif self.unit_type == 'service':
            return self._check_service()

    def _check_service(self):
        if self.specific_properties.ExecMainStatus != 0:
            return Problem.failed

        if self.specific_properties.Type != 'oneshot':
            if self.properties.ActiveState != 'active':
                return Problem.inactive

            if self.properties.SubState == 'exited':
                return Problem.exited

    def _check_timer(self, args):
        if self.properties.ActiveState != 'active':
            return Problem.inactive

        intervals = self.specific_properties.TimersMonotonic
        if not intervals:
            return

        now = time()
        second_devider = 1000000
        checked_intervals = [
            'OnUnitActiveUSec',
            'OnUnitInactiveUSec',
        ]

        min_interval_sec = min(
            interval[1] for interval in intervals
            if interval[0] in checked_intervals
        ) / second_devider

        sec_since_executed = (
            now - (self.specific_properties.LastTriggerUSec / second_devider)
        )

        runs_missed = sec_since_executed / min_interval_sec
        if runs_missed > args.timer_missed_critical:
            return Problem.timer_missed_critical
        if runs_missed > args.timer_missed_warning:
            return Problem.timer_missed_warning


def parse_args():
    """Parse the arguments

    We are returning them as a dict for callers convenience.
    """
    parser = ArgumentParser()
    parser.add_argument(
        '-a',
        action='store_true',
        dest='check_all',
        default=False,
        help='check all units (it is the default when no services are passed)',
    )
    parser.add_argument(
        '-s',
        action='append',
        dest='critical_units',
        default=[],
        help='unit to return critical when failed',
    )
    parser.add_argument(
        '-i',
        action='append',
        dest='ignored_units',
        default=[],
        help='unit to ignore',
    )
    parser.add_argument(
        '-w',
        action='store',
        dest='timer_missed_warning',
        default=3,
        type=float,
        help='warning threshold of timer runs missed',
    )
    parser.add_argument(
        '-c',
        action='store',
        dest='timer_missed_critical',
        default=7,
        type=float,
        help='critical threshold of timer runs missed',
    )
    return parser.parse_args()


def main():
    """The main program"""
    args = parse_args()

    try:
        units = Manager().list_units()
    except SystemdError as error:
        print('UNKNOWN: ' + str(error))
        exit_code = 3
    else:
        criticals, warnings = process([SystemdUnit(u) for u in units], args)
        if criticals:
            print('CRITICAL: ' + get_message(criticals + warnings))
            exit_code = 2
        elif warnings:
            print('WARNING: ' + get_message(warnings))
            exit_code = 1
        else:
            print('OK')
            exit_code = 0

    exit(exit_code)


def process(units, args):
    criticals = []
    warnings = []

    # First, all critical units
    critical_timer_service_ids = []
    for unit in filter_out(units, args.critical_units):
        problem = unit.check(args)
        if problem:
            if problem < Problem.inactive:
                criticals.append((problem, unit))
            else:
                warnings.append((problem, unit))

        if unit.unit_type == 'timer':
            critical_timer_service_ids.append(unit.specific_properties.Unit)

    # Then, the services of the critical timer units
    for unit in filter_out(units, critical_timer_service_ids):
        problem = unit.check(args)
        if problem and problem != Problem.inactive:
            criticals.append((problem, unit))

    # Last, the others
    if args.check_all:
        for unit in units:
            problem = unit.check(args)
            if problem and problem < Problem.inactive:
                warnings.append((problem, unit))

    return criticals, warnings


def filter_out(units, ids):
    if not ids:
        return

    remaining_units = []
    for unit in units:
        if any(unit.match(i) for i in ids):
            yield unit
        else:
            remaining_units.append(unit)

    units[:] = remaining_units


def get_message(problems):
    """Format the message to print out"""
    problem_names = {
        v: k.replace('_', ' ')
        for k, v in vars(Problem).items()
        if isinstance(v, int)
    }
    message = ''
    last_problem = None
    for problem, unit in problems:
        if problem != last_problem:
            message += problem_names[problem] + ': '
            last_problem = problem
        message += str(unit) + ' '

    return message


if __name__ == '__main__':
    main()
