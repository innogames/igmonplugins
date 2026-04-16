#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - NVMe Health Check

This script checks the health of NVMe disks by discovering devices via sysfs
and querying SMART data with nvme-cli. It raises a warning or critical state
when the remaining life falls below the configured thresholds.

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
import os
import sys
from argparse import ArgumentParser
from subprocess import CalledProcessError, STDOUT, check_output


class ExitCodes():
    OK = 0
    WARNING = 1
    CRITICAL = 2
    UNKNOWN = 3

    @classmethod
    def label(cls, code):
        return {cls.OK: 'OK', cls.WARNING: 'WARNING', cls.CRITICAL: 'CRITICAL', cls.UNKNOWN: 'UNKNOWN'}[code]


def parse_args():
    parser = ArgumentParser(
        description='Check NVMe disk remaining life via nvme-cli smart-log',
    )
    parser.add_argument(
        '--warning', '-w',
        help='warning threshold for remaining life percentage (default: 20)',
        default=20,
        type=int,
    )
    parser.add_argument(
        '--critical', '-c',
        help='critical threshold for remaining life percentage (default: 10)',
        default=10,
        type=int,
    )
    return parser.parse_args()


def main():
    args = parse_args()

    devices = get_nvme_devices()
    if not devices:
        print('UNKNOWN - No NVMe devices found in /sys/class/nvme')
        sys.exit(ExitCodes.UNKNOWN)

    code = ExitCodes.OK
    summaries = []
    perfdata = []

    for device in devices:
        name = os.path.basename(device)

        try:
            smart = get_smart_log(device)
        except CalledProcessError as e:
            print(f'UNKNOWN - Failed to query {device}: {e.output.decode().strip()}')
            sys.exit(ExitCodes.UNKNOWN)
        except (OSError, ValueError) as e:
            print(f'UNKNOWN - Error reading {device}: {e}')
            sys.exit(ExitCodes.UNKNOWN)

        percent_used = smart.get('percent_used')
        if percent_used is None:
            print(f'UNKNOWN - percent_used missing in smart-log output for {device}')
            sys.exit(ExitCodes.UNKNOWN)

        remaining = 100 - percent_used

        if remaining <= args.critical:
            code = max(code, ExitCodes.CRITICAL)
        elif remaining <= args.warning:
            code = max(code, ExitCodes.WARNING)

        summaries.append(f'{name} life={remaining}%')
        perfdata.append(f'{name}_life={remaining}%;{args.warning};{args.critical};0;100')

    status = ExitCodes.label(code)
    if len(summaries) == 1:
        lines = [f'{status} - {summaries[0]} | {perfdata[0]}']
    else:
        lines = [status]
        for summary in summaries[:-1]:
            lines.append(summary)
        lines.append(f'{summaries[-1]} | {perfdata[0]}')
        for perf in perfdata[1:]:
            lines.append(perf)
    print('\n'.join(lines))
    sys.exit(code)


def get_nvme_devices():
    """Return sorted list of /dev/nvmeN device paths discovered via sysfs"""
    sysfs_path = '/sys/class/nvme'
    if not os.path.exists(sysfs_path):
        return []
    return sorted('/dev/' + entry for entry in os.listdir(sysfs_path))


def get_smart_log(device):
    """Run nvme smart-log on device and return parsed JSON dict"""
    raw = check_output(
        ['nvme', 'smart-log', '--output-format=json', device],
        stderr=STDOUT,
    )
    return json.loads(raw.decode())


if __name__ == '__main__':
    main()
