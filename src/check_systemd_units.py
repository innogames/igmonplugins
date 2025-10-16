#!/usr/bin/env python3
"""Nagios systemd units check

This is a Nagios script to check all or some units of "systemd".
It checks for anomalies of those units like the ones not anymore
defined but still running, and them being inactive. Normally returns
at most warning, if no critical units are specified. Returns:

* critical when a critical unit is failed
* warning for other anomalies

Copyright (c) 2023 InnoGames GmbH
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

import argparse
import collections
import datetime
import logging
import subprocess
import sys
import time
import typing

CheckResult = collections.namedtuple('CheckResult', ['code', 'msg'])

logging.basicConfig(
    format='%(levelname)-8s [%(filename)s:%(lineno)d] %(message)s',
)
logger = logging.getLogger(__name__)


def parse_args():
    """Parse CLI arguments"""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-a',
        '--check-all',
        action='store_true',
        help='Check all units (it is the default when no services are passed)',
    )
    parser.add_argument(
        '-u',
        '--critical-units',
        action='append',
        default=[],
        help='Units to return critical when failed. Checking a timer unit'
             ' will implicitly check the related service unit as well',
    )
    parser.add_argument(
        '-i',
        '--ignored-units',
        action='append',
        default=[],
        help='Units to ignore',
    )
    parser.add_argument(
        '-w',
        '--timer-warn',
        default=3.,
        type=float,
        help='Warning threshold of timer (inactivity/min_monotonic_interval)',
    )
    parser.add_argument(
        '-c',
        '--timer-crit',
        default=7.,
        type=float,
        help='Critical threshold of timer (inactivity/min_monotonic_interval)',
    )
    parser.add_argument(
        '-l',
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL', 'FATAL'],
        default=logging.CRITICAL,
        help='Set the script verbosity',
    )

    return parser.parse_args()


def main():
    """Main entry point"""
    args = parse_args()
    logger.setLevel(args.log_level)

    exit_code, message = run_checks(args)
    print(message)
    sys.exit(exit_code)


def run_checks(args: argparse.Namespace) -> CheckResult:
    """Run all checks and generate Nagios results"""
    if args.check_all or len(args.critical_units) == 0:
        unit_filter = ['*']
    elif any(u.endswith('.timer') for u in args.critical_units):
        unit_filter = args.critical_units + ['*.service']
    else:
        unit_filter = args.critical_units

    raw_units = show_units(unit_filter)
    units = parse_units(raw_units)
    results = process(args, units)

    logger.info('Criticals are: {}'.format(results[2]))
    logger.info('Warnings are: {}'.format(results[1]))

    return gen_output(results)


def process(
    args: argparse.Namespace,
    units: dict,
) -> typing.Dict[int, typing.List[typing.Tuple[str, str]]]:
    """Run all unit checks"""
    results = {Codes.WARNING: [], Codes.CRITICAL: []}
    checker = UnitChecker(units, args.timer_warn, args.timer_crit)

    for unit_id in units:
        if unit_id not in args.critical_units:
            if unit_id in args.ignored_units:
                continue
            if len(args.critical_units) and not args.check_all:
                continue

        res = checker.check_unit(unit_id)
        res_code = res.code
        if unit_id not in args.critical_units:
            res_code = max(0, res_code - 1)

        if res_code == Codes.OK:
            continue

        logger.info('Problem for {} is: {} - {}'.format(
            unit_id, res_code, res.msg,
        ))
        results[res_code].append((unit_id, res.msg))

    return results


def gen_output(
    results: typing.Dict[int, typing.List[typing.Tuple[str, str]]],
) -> CheckResult:
    """Generate Nagios output from check results"""
    if len(results[Codes.CRITICAL]):
        message = 'CRITICAL: '
        exit_code = Codes.CRITICAL
    elif len(results[Codes.WARNING]):
        message = 'WARNING: '
        exit_code = Codes.WARNING
    else:
        return Codes.OK, 'OK'

    problems = {}
    for unit, problem in results[1] + results[2]:
        if problem in problems:
            problems[problem] += ', ' + unit
        else:
            problems[problem] = unit

    logger.info('Problems are: {}'.format(problems))
    message += '; '.join([': '.join(i) for i in problems.items()])

    return exit_code, message


def show_units(units: typing.List[str]) -> str:
    """Query relevant units from systemctl"""
    properties = [
        'ActiveEnterTimestamp',
        'ActiveState',
        'ConditionResult',
        'ExecMainStatus',
        'Id',
        'InactiveEnterTimestamp',
        'LastTriggerUSec',
        'LoadState',
        'SubState',
        'SuccessExitStatus',
        'Type',
        'Unit',
    ]
    args = [
        '/bin/systemctl',
        'show',
        '-al',
        '--no-pager',
        '--property',
        ','.join(properties),
    ]
    args += units
    res = subprocess.check_output(args, stderr=subprocess.STDOUT)

    return res.decode()


def parse_units(raw_units: str) -> typing.Dict[str, dict]:
    """Parse systemd units output"""
    units = {}
    curr_unit = {}

    for line in raw_units.splitlines():
        line = line.strip()

        # Check if a new unit section is starting
        if line == '':
            units[curr_unit['Id']] = curr_unit
            curr_unit = {}
            continue

        kv = line.split('=', 1)
        if len(kv) != 2:
            continue

        # Ignore unset params
        k, v = kv[0], kv[1]
        if v == '[not set]':
            continue

        # Parse dictionary values
        if v.startswith('{'):
            v = v.strip('{}')
            params = v.split(' ; ')
            param_dict = {}

            for param in params:
                kv = param.split('=')
                param_dict[kv[0].strip()] = kv[1].strip()

            curr_unit[k] = param_dict
        else:
            curr_unit[k] = v

    units[curr_unit['Id']] = curr_unit

    return units


class UnitChecker:
    def __init__(
        self,
        units: typing.Dict[str, dict],
        timer_warn: int,
        timer_crit: int,
    ) -> None:
        self._units = units
        self._timer_warn = timer_warn
        self._timer_crit = timer_crit
        self._now = time.time()

    def check_unit(self, unit_id: str, timer: bool = False) -> CheckResult:
        """
        Check for any problem with a systemd unit

        Args:
            unit_id (str): The unit to check
            timer (bool): Whether the service has a timer
        """
        # Ignore transient session and user scope units: not actionable + harmless
        if unit_id.endswith('.scope'):
            if unit_id.startswith('session-') or unit_id.startswith('user@'):
                return CheckResult(Codes.OK, '')

        unit = self._units[unit_id]
        logger.debug(
            'Load and active states for unit {} are: {} {}'.format(
                unit_id,
                unit['LoadState'],
                unit['ActiveState'],
            )
        )

        # Fast state checks first
        if unit['LoadState'] != 'loaded' and unit['ActiveState'] != 'inactive':
            return CheckResult(
                Codes.CRITICAL,
                'the unit is not loaded but not inactive',
            )
        elif unit['ActiveState'] == 'failed':
            return CheckResult(Codes.CRITICAL, 'the unit is failed')
        elif unit['LoadState'] != 'loaded':
            return CheckResult(Codes.WARNING, 'the unit is not loaded')

        # Check the specifics about the different unit types
        if unit_id.endswith('.timer'):
            return self.check_timer(unit_id)
        elif unit_id.endswith('.service'):
            return self.check_service(unit_id, timer)

        return CheckResult(Codes.OK, '')

    def check_service(self, unit_id: str, timer: bool = False) -> CheckResult:
        """Check for any problem with a service unit"""
        unit = self._units[unit_id]

        # Ignore service units that are currently restarting but only tell
        # us if they are failed. This allows us to use systemd to restart
        # services silently without raising a warning which requires no
        # manual action.
        if (
            unit['ActiveState'] == 'activating'
            and unit['SubState'] == 'auto-restart'
        ):
            return CheckResult(Codes.OK, '')

        # Systemd on Debian Buster contains a lot of services in inactive
        # state by "Condition*" parameters, it's fine to ignore them
        if 'ConditionResult' in unit and unit['ConditionResult'] == 'no':
            return CheckResult(Codes.OK, '')

        # Non-oneshot services should not exit
        if unit['Type'] != 'oneshot':
            if unit['ActiveState'] != 'active':
                return CheckResult(Codes.CRITICAL, 'the service is inactive')
            if unit['SubState'] == 'exited':
                return CheckResult(Codes.CRITICAL, 'the service is exited')
            return CheckResult(Codes.OK, '')

        # Check exit code
        res = self.check_exit_code(unit_id)
        if res.code != Codes.OK:
            return res

        # Check left-behind oneshot services
        if (
            unit['ActiveState'] == 'active'
            and unit['SubState'] == 'exited'
            and timer
        ):
            return CheckResult(
                Codes.CRITICAL,
                'the timer-related service is misconfigured,'
                ' set RemainAfterExit=false',
            )

        return CheckResult(Codes.OK, '')

    def check_exit_code(self, unit_id: str) -> CheckResult:
        """Checks expected exit code of the service"""
        unit = self._units[unit_id]

        # See the man 5 systemd.service for ExecMainStatus and SuccessExitStatus
        # All currently running services have ExecMainStatus=0
        success_codes = []
        if 'SuccessExitStatus' in unit and len(unit['SuccessExitStatus']):
            success_codes.extend(unit['SuccessExitStatus'].split())
        success_codes.append('0')

        exit_code = unit['ExecMainStatus']
        if exit_code not in success_codes:
            return CheckResult(
                Codes.WARNING,
                f'the service exited with {exit_code} code',
            )
        return CheckResult(Codes.OK, '')

    def check_timer(self, unit_id: str) -> CheckResult:
        """Check for any problem with a timer unit"""
        res = self.check_intervals(unit_id)
        if res.code != Codes.OK:
            return res

        unit = self._units[unit_id]
        if unit['ActiveState'] != 'active':
            return CheckResult(Codes.CRITICAL, 'the timer is not active')

        # This might check the service unit twice. We need to do that as we
        # would not check timer service unit at all if the user didn't
        # explicitly ask for them via arguments.
        return self.check_unit(unit['Unit'], timer=True)

    def check_intervals(self, unit_id: str) -> CheckResult:
        """Check all monotonic triggers of a timer unit"""
        unit = self._units[unit_id]

        # We check intervals only if timer has been triggered after reboot,
        # otherwise LastTriggerUSec=0 (1970-01-01:00:00:00)
        if unit['LastTriggerUSec'] == 0:
            return CheckResult(Codes.OK, '')

        # We only check monotonic timers
        if 'TimersMonotonic' not in unit:
            return CheckResult(Codes.OK, '')

        # We can check only monotonic triggers for regular execution
        checked_intervals = ['OnUnitActiveUSec', 'OnUnitInactiveUSec']
        intervals = [
            (p[0], p[1]) for p in unit['TimersMonotonic']
            if p[0] in checked_intervals
        ]
        logger.debug('Monotonic timers are: {}'.format(intervals))
        if not intervals:
            return CheckResult(Codes.OK, '')

        # Check each collected metric on its own
        for interval in intervals:
            result = self._check_interval(unit_id, interval)
            if result:
                return result

        return CheckResult(Codes.OK, '')

    def _check_interval(
        self,
        unit_id: str,
        interval: typing.Tuple[str, int],
    ) -> CheckResult:
        """Check a specific monotonic trigger of a timer unit"""
        unit = self._units[unit_id]

        # Doing the math
        m = 1000000  # Microseconds to seconds
        trigger, start_interval = interval
        start_interval /= m
        last_trigger = unit['LastTriggerUSec'] / m
        service_unit = self._units[unit['Unit']]

        if trigger == 'OnUnitActiveUSec':
            state_change = service_unit['ActiveEnterTimestamp'] / m
        else:
            state_change = service_unit['InactiveEnterTimestamp'] / m

        # If the unit was started everything is fine
        if last_trigger > state_change:
            return CheckResult(Codes.OK, '')

        # A ratio of 1 means the timer has exactly started the unit after
        # the amount of time it was configured. lower means it should not
        # execute, yet, and higher means it should have been executed.
        not_triggered_since = self._now - state_change
        ratio = not_triggered_since / start_interval
        last_trigger_human = datetime.datetime.fromtimestamp(last_trigger)

        logger.info(
            f'{unit_id}: interval={start_interval}, '
            f'last_trigger={last_trigger}, state_change={state_change}, '
            f'not_triggered_since={not_triggered_since}, '
            f'not_triggered_since / interval={ratio}'
        )

        # Check timer thresholds
        if self._timer_crit <= ratio:
            code = Codes.CRITICAL
        elif self._timer_warn <= ratio:
            code = Codes.WARNING
        else:
            code = Codes.OK

        if code != Codes.OK:
            return CheckResult(
                code,
                f"the timer hasn't been launched since {last_trigger_human}, "
                f"look at {service_unit['Id']}"
            )
        return CheckResult(Codes.OK, '')


class Codes:
    OK = 0
    WARNING = 1
    CRITICAL = 2
    UNKNOWN = 3


if __name__ == '__main__':
    main()
