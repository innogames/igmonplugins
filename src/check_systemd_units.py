#!/usr/bin/env python3
"""Nagios systemd units check

This is a Nagios script to check all or some units of "systemd".
It checks for anomalies of those units like the ones not anymore
defined but still running, and them being inactive.  Normally returns
at most warning, if no critical units are specified.  Returns

* critical when a critical unit is failed
* warning when a critical unit is not running
* warning when a non-critical unit is failed
* warning for other anomalies.

Copyright (c) 2020 InnoGames GmbH
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

import dbus
import logging
import time

from argparse import ArgumentParser
from contextlib import ExitStack
from datetime import datetime
from fnmatch import fnmatch
from sys import exit
#from time import time

logging.basicConfig(
    format='%(levelname)-8s [%(filename)s:%(lineno)d] %(message)s'
)
logger = logging.getLogger(__name__)

now = time.time()

bus = dbus.SystemBus()

systemd = bus.get_object(
    'org.freedesktop.systemd1',
    '/org/freedesktop/systemd1'
)

systemd_manager = dbus.Interface(
    systemd,
    'org.freedesktop.systemd1.Manager'
)

unit_properties_time = 0
type_properties_time = 0

class Codes(object):
    OK = 0
    WARNING = 1
    CRITICAL = 2
    UNKNOWN = 3


class UnitProperty(object):
    def __str__(self):
        return str(vars(self))

class SystemdUnit:
    """
    Systemd unit

    This class implements basic properties of a Systemd unit as received via dbus
    """

    def __init__(self, unit):
        global unit_properties_time
        global type_properties_time

        logger.debug(unit)
        self.unit_type = unit[0].rsplit('.', 1)[-1]

        self.__unit_proxy = bus.get_object(
            'org.freedesktop.systemd1',
            unit[6]
        )

        self.__unit_interface = dbus.Interface(
            self.__unit_proxy,
            'org.freedesktop.systemd1.Unit',
        )

        self.__properties_interface = dbus.Interface(
            self.__unit_proxy,
            'org.freedesktop.DBus.Properties',
        )

        if self.unit_type in ['service', 'timer']:

            properties_time_1 = time.perf_counter()

            unit_properties = self.__properties_interface.GetAll(
                self.__unit_interface.dbus_interface,
            )
            properties_time_2 = time.perf_counter()

            unit_properties_time += properties_time_2 - properties_time_1

        #else:
        unit_properties = {
            'Id': unit[0],
            'LoadState': unit[2],
            'ActiveState': unit[3],
            'SubState': unit[4],
        }

        tmp_properties = UnitProperty()
        for k, v in unit_properties.items():
            setattr(tmp_properties, k, v)
        setattr(self, '__unit_properties', tmp_properties)

        #logger.debug(f'#### unit properties 1: {self.__unit_properties}')
        logger.debug(f'#### unit properties 2: {self.unit_properties}')

        unit_type_interface = None
        if self.unit_type == 'service':
            unit_type_interface = 'org.freedesktop.systemd1.Service'
        if self.unit_type == 'timer':
            unit_type_interface = 'org.freedesktop.systemd1.Timer'

        if unit_type_interface:

            self.__unit_type_interface = dbus.Interface(
                self.__unit_proxy,
                unit_type_interface,
            )

            #self.__unit_type_properties_interface = dbus.Interface(
            #    self.__unit_proxy,
            #    'org.freedesktop.DBus.Properties'
            #)

            properties_time_1 = time.perf_counter()
            unit_type_properties = self.__properties_interface.GetAll(
                self.__unit_type_interface.dbus_interface,
            )
            properties_time_2 = time.perf_counter()
            type_properties_time += properties_time_2 - properties_time_1

            tmp_properties = UnitProperty()
            for k, v in unit_type_properties.items():
                setattr(tmp_properties, k, v)
            setattr(self, '__type_properties', tmp_properties)

            #logger.debug(f'#### unit type properties 1: {self.__type_properties}')
            logger.debug(f'#### unit type properties 2: {self.type_properties}')
        #print()

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
        return getattr(self, '__unit_properties')

    @property
    def type_properties(self):
        '''
        Returns properties from type specific interface
        '''
        if hasattr(self, '__type_properties'):
            logger.debug('yes type properties')
            return getattr(self, '__type_properties')
        logger.debug('no type properties')

    def match(self, pattern):
        name = str(self)
        logger.debug('Pattern is {}, name is {}'.format(pattern, name))
        return fnmatch(name, pattern)

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

        if (
                self.unit_properties.LoadState != 'loaded' and
                self.unit_properties.ActiveState != 'inactive'
        ):
            return (
                Codes.CRITICAL,
                'the unit is not loaded but not inactive'
            )
        if self.unit_properties.LoadState != 'loaded':
            return (self._warn_level, 'the unit is not loaded')
        if self.unit_properties.ActiveState == 'failed':
            return (self._crit_level, 'the unit is failed')
        if self.unit_type == 'timer':
            return self._check_timer(timer_warn, timer_crit)
        if self.unit_type == 'service':
            return self._check_service(timer)

        return (Codes.OK, '')

    def _check_service(self, timer=False):
        '''
        Detects problems for a service unit
        '''

        if (
            self.unit_properties.ActiveState == 'activating' and
            self.unit_properties.SubState == 'auto-restart'
        ):
            # Ignore service units that are currently restarting but only tell
            # us if they are failed. This allows us to use systemd to restart
            # services silently without raising a warning which requires no
            # manual action.
            return (Codes.OK, '')
        if (
            hasattr(self.unit_properties, 'ConditionResult') and
            not self.unit_properties.ConditionResult
        ):
            # systemd on Debian Buster contains a lot of services in inactive
            # state by "Condition*" parameters, it's fine to ignore them
            return (Codes.OK, '')

        # Most probably, oneshot is related to some timer
        if self.unit_type == 'oneshot':
            # See the man 5 systemd.service for ExecMainStatus and
            # SuccessExitStatus
            # All currently running services have ExecMainStatus=0

            # SuccessExitStatus is not always present in older versions
            # of systemd.
            # SuccessExitStatus[0] is an array that could be empty.
            if hasattr(self.type_properties, 'SuccessExitStatus') and \
                    len(self.type_properties.SuccessExitStatus[0]):
                last_run_failed = self.type_properties.ExecMainStatus not in \
                                  self.type_properties.SuccessExitStatus[0]
            else:
                # We only want to rely purely on ExecMainStatus != 0 if
                # we don't have the SuccessExitStatus attribute or if the
                # SuccessExitStatus array is empty.
                last_run_failed = self.type_properties.ExecMainStatus != 0

            if last_run_failed:
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
                    self._crit_level, 'the service is inactive'
                )
            if self.unit_properties.SubState == 'exited':
                # Non oneshot services should not exit
                return (
                    self._crit_level, 'the service is exited'
                )

        return (Codes.OK, '')

    def _check_timer(self, timer_warn, timer_crit):
        '''
        Detects problems for a timer unit
        '''
        # This might check the service unit twice. We need to do that as we
        # would not check timer service unit at all if the user didn't
        # explicitly ask for them via arguments.
        logger.debug(f'Checking type property unit 1 {self.type_properties.Unit}')
        logger.debug(f'Checking type property unit 2 {systemd_manager.GetUnit(self.type_properties.Unit)}')
        service_unit = SystemdUnit(
            systemd_manager.GetUnit(self.type_properties.Unit)
        )

        long_not_running = self._check_intervals(
            service_unit,
            timer_warn,
            timer_crit,
        )
        if long_not_running:
            return long_not_running

        if self.unit_properties.ActiveState != 'active':
            return (
                self._crit_level, 'the timer is not active'
            )

        return service_unit.check(
            timer_warn, timer_crit, self.__critical, timer=True
        )

    def _check_intervals(self, service_unit, timer_warn, timer_crit):
        # We check intervals only if timer has been triggered after reboot,
        # otherwise LastTriggerUSec=0 (1970-01-01:00:00:00)
        if self.type_properties.LastTriggerUSec == 0:
            return None

        # We can check only monotonic triggers for regular execution
        checked_intervals = ['OnUnitActiveUSec', 'OnUnitInactiveUSec']

        intervals = [
            (p[0], p[1]) for p in self.type_properties.TimersMonotonic
            if p[0] in checked_intervals
        ]
        logger.debug('Monotonic timers are: {}'.format(intervals))
        if not intervals:
            return None

        # Check each collected metric on its own
        for interval in intervals:
            result = self._check_interval(
                service_unit,
                interval,
                timer_warn,
                timer_crit,
            )

            if result:
                return result

        return None

    def _check_interval(self, service_unit, interval, timer_warn, timer_crit):
        # Microseconds to seconds
        m = 1000000

        # Doing the math
        trigger, start_interval = interval
        start_interval /= m
        last_trigger = self.type_properties.LastTriggerUSec / m

        if trigger == 'OnUnitActiveUSec':
            state_change = (
                service_unit.unit_properties.ActiveEnterTimestamp / m
            )
        else:
            state_change = (
                service_unit.unit_properties.InactiveEnterTimestamp / m
            )

        # If the unit was started everything is fine
        if last_trigger > state_change:
            return None

        # A ratio of 1 means the timer has exactly started the unit after
        # the amount of time it was configured. lower means it should not
        # execute, yet, and higher means it should have been executed.
        not_triggered_since = now - state_change
        ratio = not_triggered_since / start_interval

        logger.info(
            '{}: interval={}, last_trigger={}, state_change={}, '
            'not_triggered_since={}, '
            'not_triggered_since / interval={}'.format(
                str(self),
                start_interval,
                last_trigger,
                state_change,
                not_triggered_since,
                ratio,
            )
        )

        last_trigger_human = datetime.fromtimestamp(last_trigger)

        if timer_crit <= ratio:
            return (
                self._crit_level,
                'the timer hasn\'t been launched since {}, look at {}'
                    .format(last_trigger_human, str(service_unit))
            )

        if timer_warn <= ratio:
            return (
                self._warn_level,
                'the timer hasn\'t been launched since {}, look at {}'
                    .format(last_trigger_human, str(service_unit))
            )

        return None


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
        help='unit to return critical when failed. Checking a timer unit'
             ' will implicitly check the related service unit as well',
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
        help='warning threshold of timer (inactivity/min_monotonic_interval)',
    )
    parser.add_argument(
        '-c',
        action='store',
        dest='timer_crit',
        default=7,
        type=float,
        help='critical threshold of timer (inactivity/min_monotonic_interval)',
    )
    parser.add_argument(
        '-l',
        action='store',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL', 'FATAL'],
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
        units = systemd_manager.ListUnits()
    except SystemdError as error:
        print('UNKNOWN: ' + str(error))
        exit_code = 3
    else:
        units = [SystemdUnit(u) for u in units]
        logger.info(f'Unit properties time: {unit_properties_time:.1f}s')
        logger.info(f'Type properties time: {type_properties_time:.1f}s')
        results = process(units, args)
        logger.info(
            'criticals are: {}\nwarnings are: {}'
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
        logger.info('Ignored units are: {}'.format(args.ignored_units))
        for unit in units:
            logger.debug('Unit name is: {}'.format(unit))
            if str(unit) in args.ignored_units:
                continue
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
