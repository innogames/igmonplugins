#!/usr/bin/env python
#
# Nagios systemd units check
#
# This is a Nagios script to check all or some units of "systemd".
# It checks for anomalies of those units like the ones not anymore
# defined but still running, and them being dead.  Normally returns
# at most warning, if no critical units are specified.  Returns
#
# * critical when a critical unit is failed
# * warning when a critical unit is not running
# * warning when a non-critical unit is failed
# * warning for other anomalies.
#
# Copyright (c) 2018 InnoGames GmbH
#

from argparse import ArgumentParser
from sys import exit

from systemd_dbus.exceptions import SystemdError
from systemd_dbus.manager import Manager
from systemd_dbus.service import Service


class Problem:
    """Enum for problems that can apply to the units"""

    # From more important to less
    failed = 0
    activating_auto_restart = 1
    not_loaded_but_not_inactive = 2
    not_loaded_but_not_dead = 3
    dead = 4
    not_loaded = 5


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
            return Service(self.dbus_path).properties

    def match(self, pattern):
        name = str(self)
        if pattern.endswith('@*') and '@' in name:
            return pattern[:-len('@*')] == name.split('@', 1)[0]
        return pattern == name

    def check(self):
        """Detect problems of a unit"""
        if self.properties.LoadState != 'loaded':
            if self.properties.ActiveState != 'inactive':
                return Problem.not_loaded_but_not_inactive

            if self.properties.SubState != 'dead':
                return Problem.not_loaded_but_not_dead

            return Problem.not_loaded

        if self.properties.ActiveState == 'failed':
            return Problem.failed

        if self.properties.SubState == 'auto-restart':
            if self.specific_properties.ExecMainStatus != 0:
                return Problem.activating_auto_restart
        elif self.properties.SubState == 'dead':
            return Problem.dead
        elif self.properties.SubState == 'failed':
            return Problem.failed


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

    for unit in units:
        is_critical = any(unit.match(p) for p in args.critical_units)
        if not is_critical and not args.check_all:
            continue

        problem = unit.check()
        if problem is None:
            continue

        if not is_critical and problem >= Problem.dead:
            continue

        if is_critical and problem < Problem.dead:
            criticals.append((problem, unit))
        else:
            warnings.append((problem, unit))

    return criticals, warnings


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
