#!/usr/bin/env python
#
# Nagios systemd units check
#
# This is a Nagios script to check all or some units of "systemd".
# It checks for anomalies of those units like the ones not anymore
# defined but still running, and them being inactive.  Normally returns
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

from datetime import datetime
from dbus import INTROSPECTABLE_IFACE, Interface
from systemd_dbus.exceptions import SystemdError
from systemd_dbus.manager import Manager
from time import time
from xml.etree import ElementTree

import logging

logging.basicConfig(
    format='%(levelname)-8s [%(filename)s:%(lineno)d] %(message)s'
)
logger = logging.getLogger(__name__)

now = time()

systemd_manager = Manager()


class Codes(object):
    OK = 0
    WARNING = 1
    CRITICAL = 2
    UNKNOWN = 3


class Property(object):
    pass


class SystemdUnit:
    """Systemd unit"""

    def __init__(self, unit):
        self.__properties_interface = unit._Unit__properties_interface
        dbus_proxy = unit._Unit__proxy
        # Interface for getting info about other interfaces
        introspect_interface = Interface(
            dbus_proxy,
            INTROSPECTABLE_IFACE
        )
        # Get the type specific interface for the unit
        iface_tree = ElementTree.fromstring(introspect_interface.Introspect())
        self.__type_interface = [
            i.attrib['name']
            for i in iface_tree
            if i.attrib['name'].startswith('org.freedesktop.systemd1.') and
            i.attrib['name'] != 'org.freedesktop.systemd1.Unit'
        ][0]
        logger.debug(
            'Type interface for unit {} is: {}'.format(
                str(self),
                self.__type_interface
            )
        )
        self.unit_type = self.__type_interface.split('.')[-1].lower()
        logger.debug('Unit type is: {}'.format(self.unit_type))

    def __str__(self):
        return str(self.unit_properties.Id)

    def __lt__(self, other):
        return str(self) < str(other)

    @property
    def unit_properties(self):
        '''
        Returns properties from unit interface
        '''
        if hasattr(self, '__unit_properties'):
            return self.__unit_properties
        properties = self.__properties_interface.GetAll(
             'org.freedesktop.systemd1.Unit'
        )
        self.__unit_properties = Property()
        for k, v in properties.items():
            setattr(self.__unit_properties, k, v)
        return self.__unit_properties

    @property
    def type_properties(self):
        '''
        Returns properties from type specific interface
        '''
        if hasattr(self, '__type_properties'):
            return self.__type_properties
        properties = self.__properties_interface.GetAll(
            self.__type_interface
        )
        self.__type_properties = Property()
        for k, v in properties.items():
            setattr(self.__type_properties, k, v)
        return self.__type_properties

    def match(self, pattern):
        name = str(self)
        if pattern.endswith('@*') and '@' in name:
            return pattern[:-len('@*')] == name.split('@', 1)[0]
        logger.debug('Pattern is {}, name is {}'.format(pattern, name))
        return pattern == name

    def check(self, timer_warn, timer_crit, critical=True, timer=False):
        """
        Detects general problems of a unit
        """
        logger.debug(
            'Load and Active states for unit {} are: {} {}'.format(
                str(self),
                self.unit_properties.LoadState,
                self.unit_properties.ActiveState,
            )
        )
        self.__critical = critical
        if self.__critical:
            self._crit_level = Codes.CRITICAL
            self._warn_level = Codes.WARNING
        else:
            self._crit_level = Codes.WARNING
            self._warn_level = Codes.OK

        if self.unit_properties.LoadState != 'loaded':
            if self.unit_properties.ActiveState != 'inactive':
                return (
                    Codes.CRITICAL,
                    'the unit is not loaded but not inactive'
                )
            return (self._warn_level, 'the unit is not loaded')

        if self.unit_properties.ActiveState == 'failed':
            return (self._crit_level, 'the unit is failed')
        if self.unit_type == 'timer':
            return self._check_timer(timer_warn, timer_crit)
        elif self.unit_type == 'service':
            return self._check_service(timer)
        else:
            return (Codes.OK, '')

    def _check_service(self, timer=False):
        '''
        Detects problems for a service unit
        '''
        # Most probably, oneshot is related to some timer
        if self.type_properties.Type == 'oneshot':
            if self.type_properties.ExecMainStatus != 0:
                return (
                    self._warn_level,
                    'the service exited with {} code'.format(
                        self.type_properties.ExecMainStatus
                    )
                )
            if (
                self.unit_properties.ActiveState == 'active'
                and self.unit_properties.SubState == 'exited'
                and timer
            ):
                return (
                    self._crit_level,
                    'the timer-related service is misconfigured,'
                    ' set RemainAfterExit=false')
        else:
            if self.unit_properties.ActiveState != 'active':
                return (
                    self._warn_level, 'the service is inactive'
                )
            if self.unit_properties.SubState == 'exited':
                return (
                    self._warn_level, 'the service is exited'
                )
        return (Codes.OK, '')

    def _check_timer(self, timer_warn, timer_crit):
        '''
        Detects problems for a timer unit
        '''
        checked_intervals = [
            'OnUnitActiveUSec',
            'OnUnitInactiveUSec',
        ]
        # Microseconds to seconds
        m = 1000000
        if self.unit_properties.ActiveState != 'active':
            return (
                self._crit_level, 'the timer is not active'
            )
        intervals = self.type_properties.TimersMonotonic
        logger.debug('Monotonic timers are: {}'.format(intervals))
        if intervals:
            # We could check only monotonic triggers for regular execution
            min_interval = min(p[1] for p in intervals
                               if p[0] in checked_intervals) / m
            since_last_execute = (
                now - self.type_properties.LastTriggerUSec / m
            )
            last_execute = datetime.fromtimestamp(
                self.type_properties.LastTriggerUSec / m
            )
            logger.info(
                '{}: min_interval={}, since_last_execute={}, last_execute={}, '
                'since_last_execute / min_interval={}'
                .format(
                    str(self), min_interval, since_last_execute, last_execute,
                    since_last_execute / min_interval
                )
            )
            if (timer_warn <= since_last_execute / min_interval < timer_crit):
                return (
                    self._warn_level,
                    'the timer hasn\'t been launched since {}, look at {}'
                    .format(
                        last_execute, self.type_properties.Unit
                    )
                )
            if (timer_crit <= since_last_execute / min_interval):
                return (
                    self._crit_level,
                    'the timer hasn\'t been launched since {}, look at {}'
                    .format(
                        last_execute, self.type_properties.Unit
                    )
                )
        service_unit = SystemdUnit(
            systemd_manager.get_unit(self.type_properties.Unit)
        )
        return service_unit.check(
            timer_warn, timer_crit, self.__critical, timer=True
        )


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
        # TODO: remove
        '-s',
        action='append',
        dest='critical_units',
        default=[],
        help='[DEPRECATED, use -u]',
    )
    parser.add_argument(
        '-u',
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
        dest='timer_warn',
        default=3,
        type=float,
        help='warning threshold of timer (inactivity/max_monotonic_interval)',
    )
    parser.add_argument(
        '-c',
        action='store',
        dest='timer_crit',
        default=7,
        type=float,
        help='critical threshold of timer (inactivity/max_monotonic_interval)',
    )
    parser.add_argument(
        '-l',
        action='store',
        dest='log_level',
        default=logging.CRITICAL,
        help='set the script verbosity',
    )

    return parser.parse_args()


def main():
    """The main program"""
    args = parse_args()
    logger.setLevel(args.log_level)
    logger.info('Initial arguments are: {}'.format(args))

    try:
        units = systemd_manager.list_units()
    except SystemdError as error:
        print('UNKNOWN: ' + str(error))
        exit_code = 3
    else:
        results = process([SystemdUnit(u) for u in units], args)
        logger.info(
            "criticals are: {}\nwarnings are: {}"
            .format(results[2], results[1])
        )
        exit_code, message = gen_output(results)
        print(message)

    exit(exit_code)


def process(units, args):
    criticals = []
    warnings = []
    results = [None, warnings, criticals]

    # First, all critical units
    for unit in filter_out(units, args.critical_units):
        check_result = unit.check(args.timer_warn, args.timer_crit)
        logger.info('Problem for filtered units are: {}'.format(check_result))
        if check_result[0]:
            results[check_result[0]].append((str(unit), check_result[1]))

    # Last, the others
    if args.check_all:
        for unit in units:
            check_result = unit.check(args.timer_warn, args.timer_crit,
                                      critical=False)
            if check_result[0]:
                logger.info('Problem for {} in all units are: {}'
                            .format(str(unit), check_result))
                results[check_result[0]].append((str(unit), check_result[1]))
    return results


def filter_out(units, ids):
    logger.debug('ids are: {}'.format(ids))
    if not ids:
        return

    remaining_units = []
    for unit in units:
        if any(unit.match(i) for i in ids):
            yield unit
        else:
            remaining_units.append(unit)

    units[:] = remaining_units


def gen_output(results):
    """Get the exit code and format the message to print out"""
    if results[2]:
        message = 'CRITICAL: '
        exit_code = 2
    elif results[1]:
        message = 'WARNING: '
        exit_code = 1
    else:
        return 0, 'OK'
    problems = {}
    for unit, problem in results[1] + results[2]:
        if problem in problems:
            problems[problem] += ', ' + unit
        else:
            problems[problem] = unit
    logger.info('Problems are: {}'.format(problems))
    message += '; '.join([': '.join(i) for i in problems.items()])

    return exit_code, message


if __name__ == '__main__':
    main()
