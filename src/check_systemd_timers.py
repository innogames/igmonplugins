#!/usr/bin/env python
#
# Nagios systemd timers check
#
# This is a Nagios script to check all or some timers of "systemd".
# It checks for anomalies of those timers, i.e. unloaded, long term
# unexecuted or problems in related service
#
# * critical when a timer unit is inactive of service unit is stoped
# * warning for long term unexecuted
#
# Copyright (c) 2018, InnoGames GmbH
#

from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from datetime import datetime
# python2/3 compatibility
from time import time
from systemd_dbus.manager import Manager
from systemd_dbus.exceptions import SystemdError
import sys
import logging

logging.basicConfig(
    format='%(levelname)-8s [%(filename)s:%(lineno)d] %(message)s'
)
logger = logging.getLogger(__name__)


class CheckTimers(object):
    """
    Check timers for status, last executed service time, service status
    """
    CODES = dict(
        OK=0,
        WARNING=1,
        CRITICAL=2,
        UNKNOWN=3,
    )
    REV_CODES = {v: k for k, v in CODES.items()}

    def __init__(self, check_all, crit_threshold, ignored_timers, timer_units,
                 warn_threshold, **kwargs):
        self._crit_threshold = crit_threshold
        self._warn_threshold = warn_threshold
        try:
            s_manager = Manager()
            timers = s_manager.list_timers()
            logger.debug(
                'Timers in system are: {}'
                .format([t.properties.Id for t in timers])
            )
            if check_all:
                self.timers = {
                    str(t.properties.Id): t for t in timers
                    if str(t.properties.Id) not in ignored_timers
                }
            else:
                self.timers = {
                    str(t.properties.Id): t for t in timers
                    if str(t.properties.Id) in timer_units
                }
            logger.debug('Timers after filtering are: {}'.format(self.timers))
            self.services = {
                str(t.properties.Id): s_manager.get_unit(t.properties.Unit)
                for t in timers
            }
        except SystemdError:
            print('UNKNOWN: Error while receive info for systemd from dbus')
            sys.exit(self.CODES['UNKNOWN'])

        if self.timers == {}:
            print('UNKNOWN: Timer units not found')
            sys.exit(self.CODES['UNKNOWN'])

        self.now = time()

    def check_timers(self):
        for t_unit in self.timers:
            self._check_timer(t_unit)

    def _check_timer(self, t_unit):
        checked_intervals = [
            'OnUnitActiveUSec',
            'OnActiveUSec',
            'OnUnitInactiveUSec',
        ]
        # Microseconds to seconds
        m = 1000000
        properties = self.timers[t_unit].properties
        if properties.LoadState != 'loaded':
            setattr(
                properties,
                'MonitoringState',
                (self.CODES['CRITICAL'], 'Timer is not loaded')
            )
            return

        if properties.ActiveState != 'active':
            setattr(
                properties,
                'MonitoringState',
                (self.CODES['CRITICAL'], 'Timer is not active')
            )
            return

        intervals = properties.TimersMonotonic
        if intervals:
            min_interval = min([
                p[1]/m for p in intervals
                if p[0] in checked_intervals
            ])
            since_last_execute = self.now - properties.StateChangeTimestamp/m
            last_execute = datetime.fromtimestamp(
                properties.StateChangeTimestamp/m
            )

            if (self._warn_threshold <= since_last_execute/min_interval
                    < self._crit_threshold):
                setattr(
                    properties,
                    'MonitoringState',
                    (
                        self.CODES['WARNING'],
                        "Timer wasn't launch since {}".format(last_execute)
                    )
                )
                return
            elif self._crit_threshold <= since_last_execute/min_interval:
                setattr(
                    properties,
                    'MonitoringState',
                    (
                        self.CODES['CRITICAL'],
                        "Timer wasn't launch since {}, look at {}"
                        .format(last_execute, properties.Unit)
                    )
                )
                return

        self._check_service(t_unit)

    def _check_service(self, t_unit):
        s_properties = self.services[t_unit].properties
        t_properties = self.timers[t_unit].properties
        if s_properties.LoadState != 'loaded':
            setattr(
                t_properties,
                'MonitoringState',
                (self.CODES['CRITICAL'], 'Related service is not loaded')
            )
            return

        if s_properties.ActiveState == 'failed':
            setattr(
                t_properties,
                'MonitoringState',
                (self.CODES['CRITICAL'], 'Related service is failed')
            )
            return

        if (s_properties.ActiveState == 'active'
                and s_properties.SubState == 'exited'):
            setattr(
                t_properties,
                'MonitoringState',
                (
                    self.CODES['CRITICAL'],
                    "Related service is misconfigured, "
                    "remove 'RemainAfterExit'"
                )
            )
            return

        setattr(t_properties, 'MonitoringState', (self.CODES['OK'], ''))

    def get_nagios(self):
        statuses = {name: self.timers[name].properties.MonitoringState
                    for name in self.timers}
        logger.debug('Statuses in get_nagios: {}'.format(statuses))
        exit_code = max([statuses[n][0] for n in statuses])
        logger.debug("Exit_code = {}".format(exit_code))
        if exit_code == 0:
            message = 'OK'
            return exit_code, message
        msg_format = '{}: {}'
        messages = [
            msg_format.format(t, statuses[t][1])
            for t in statuses if statuses[t][0] > 0
        ]
        messages[0] = msg_format.format(self.REV_CODES[exit_code], messages[0])
        return exit_code, ";".join(messages)


def parse_args():
    """Parse the arguments"""
    parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '-a', action='store_true', dest='check_all', default=False,
        help='check all units (it is the default when no timers are passed)',
    )
    parser.add_argument(
        '-i', action='append', dest='ignored_timers', default=[],
        help='unit to ignore',
    )
    parser.add_argument(
        '-t', action='append', dest='timer_units', default=[],
        help='timer unit, service unit will be recognized automatically',
    )
    parser.add_argument(
        '-w', action='store', dest='warn_threshold', default=3, type=float,
        help='warning threshold of timer (inactivity/max_monotonic_interval)',
    )
    parser.add_argument(
        '-c', action='store', dest='crit_threshold', default=7, type=float,
        help='critical threshold of timer (inactivity/max_monotonic_interval)',
    )
    parser.add_argument(
        '-l', action='store', dest='log_level', default=logging.CRITICAL,
        help='enable debug logging',
    )

    return parser.parse_args()


def main():
    """The main program"""
    args = parse_args()
    logger.setLevel(args.log_level)
    logger.debug('Initial arguments are: {}'.format(args))
    if not args.check_all and not args.timer_units:
        print('UNKNOWN: Either CHECK_ALL or TIMER_UNITS should be defined')
        sys.exit(CheckTimers.CODES['UNKNOWN'])

    check = CheckTimers(**vars(args))
    check.check_timers()
    exit_code, message = check.get_nagios()
    print(message)
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
