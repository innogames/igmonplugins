#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Puppet Agent Health Check

Single health check for the puppet agent, based on the status file that
puppetrun.py writes at the end of every run. It reports both:

    - staleness: the last run is older than -w (warning) / -c (critical)
      seconds, i.e. the agent is not running as expected
    - outcome:   the last run had issues (non-zero exit), with the failure
      detail embedded in the output

A recent, clean run is OK. Because puppetrun.py overwrites the file on every
run, the check clears itself as soon as a clean run happens.

It expects a JSON status file with the following keys:
    - ts:      timestamp of the last run (int)
    - code:    exit code of the last run (int)
    - message: optional failure message (string)

Copyright (c) 2026 InnoGames GmbH
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
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import json
import platform
import time
from argparse import ArgumentParser

DEFAULT_WARNING_THRESHOLD_SEC = 8000
# We generally don't want to raise a critical alert for puppet problems
# and 0 means "disabled" for the threshold
DEFAULT_CRITICAL_THRESHOLD_SEC = 0
# Skip the check for some period after a fresh boot, the agent may not have run
# yet. Mirrors the old check_puppet_lastrun behaviour.
BOOT_GRACE_SECONDS = 8000


class ExitCodes:
    ok = 0
    warning = 1
    critical = 2
    unknown = 3

    text = {
        ok: 'OK',
        warning: 'WARNING',
        critical: 'CRITICAL',
        unknown: 'UNKNOWN',
    }


def get_status_file():
    if platform.system() == 'FreeBSD':
        return '/var/puppet/lastrun_status'
    if platform.system() in ['Linux', 'Darwin']:
        return '/var/tmp/puppet_lastrun_status'
    finish(ExitCodes.unknown, f'{platform.system()} is not supported')


def finish(code, reason):
    print('{0} - {1}'.format(ExitCodes.text.get(code, 'UNKNOWN'), reason))
    exit(code)


def get_args():
    parser = ArgumentParser(
        description=(
            'Check the age and outcome of the last puppetrun, as recorded by '
            'puppetrun wrapper.'
        )
    )
    parser.add_argument(
        '-w',
        dest='warning',
        type=int,
        default=DEFAULT_WARNING_THRESHOLD_SEC,
        help=f'Age warning threshold in seconds (0 = disable). Default {DEFAULT_WARNING_THRESHOLD_SEC}.',
    )
    parser.add_argument(
        '-c',
        dest='critical',
        type=int,
        default=DEFAULT_CRITICAL_THRESHOLD_SEC,
        help=f'Age critical threshold in seconds (0 = disable). Default {DEFAULT_CRITICAL_THRESHOLD_SEC}.',
    )
    parser.add_argument(
        '--critical-on-fail',
        action='store_true',
        help='Report CRITICAL instead of WARNING when the last run failed',
    )
    args = parser.parse_args()
    if args.critical > 0 and args.warning >= args.critical:
        finish(
            ExitCodes.warning,
            f'Warning threshold ({args.warning}) >= critical threshold ({args.critical})',
        )
    return args


def main():
    args = get_args()

    # Freshly booted host may not have run puppet yet.
    if int(time.monotonic()) < BOOT_GRACE_SECONDS:
        finish(ExitCodes.ok, 'Host recently booted, skipping')

    status_file = get_status_file()
    try:
        with open(status_file) as fd:
            status = json.load(fd)
    except FileNotFoundError:
        # No run recorded yet (fresh install / never completed).
        finish(ExitCodes.ok, 'no puppetrun status recorded yet')
    except (OSError, ValueError):
        finish(
            ExitCodes.unknown,
            f'status file {status_file} is missing or corrupt',
        )

    code = status.get('code')
    message = status.get('message', '')
    ts = status.get('ts')

    if not isinstance(ts, int):
        finish(
            ExitCodes.unknown,
            f'status file {status_file} has no valid timestamp',
        )

    age = int(time.time()) - ts

    # Staleness takes precedence over outcome: if the agent is not running at
    # all, that is the more important signal and the recorded outcome is stale.
    if args.critical > 0 and age >= args.critical:
        finish(ExitCodes.critical, f'last run {age}s ago (stale)')
    if args.warning > 0 and age >= args.warning:
        finish(ExitCodes.warning, f'last run {age}s ago (stale)')

    # Normally puppet agent exit codes 0 and 2 are considered successful,
    # but our wrapper script handles this, so non-zero means failure here.
    if code != 0:
        fail_code = (
            ExitCodes.critical if args.critical_on_fail else ExitCodes.warning
        )
        finish(
            fail_code,
            'last run failed (code {0}): {1}'.format(
                code, message or 'no details'
            ),
        )

    finish(ExitCodes.ok, f'last run clean, {age}s ago')


if __name__ == '__main__':
    main()
