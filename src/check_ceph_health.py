#!/usr/bin/env python3
#
#  Modified version of check_ceph_health from:
#  https://github.com/ceph/ceph-nagios-plugins/blob/0010cf88f8a8c8b670f3ecf59631eccb4342168e/src/check_ceph_health
#
#  Only supports Ceph Luminous (12) and newer versions.
#
#  Copyright (c) 2013-2016 SWITCH http://www.switch.ch
#  Copyright (c) 2024 Innogames GmbH https://www.innogames.com
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

import argparse
import json
import os
import re
import subprocess
import sys
from shutil import which

# nagios exit codes
STATUS_OK = 0
STATUS_WARNING = 1
STATUS_ERROR = 2
STATUS_UNKNOWN = 3


def main():
    parser = argparse.ArgumentParser(
        description="'ceph health' nagios plugin."
    )
    parser.add_argument(
        '-e',
        '--exe',
        help='ceph executable',
        default='/usr/bin/ceph',
    )
    parser.add_argument('--cluster', help='ceph cluster name')
    parser.add_argument('-c', '--conf', help='alternative ceph conf file')
    parser.add_argument(
        '-m', '--monaddress', help='ceph monitor address[:port]'
    )
    parser.add_argument('-i', '--id', help='ceph client id')
    parser.add_argument('-n', '--name', help='ceph client name')
    parser.add_argument('-k', '--keyring', help='ceph client keyring file')
    parser.add_argument(
        '--check',
        help='regexp of which check(s) to check, '
        "Can be inverted, e.g. '^((?!(PG_DEGRADED|OBJECT_MISPLACED)$).)*$'",
    )
    parser.add_argument(
        '-w', '--whitelist', help='whitelist regexp for ceph health warnings'
    )
    parser.add_argument(
        '-d', '--detail', help="exec 'ceph health detail'", action='store_true'
    )
    parser.add_argument(
        '-s', '--skip-muted', help='skip muted checks', action='store_false'
    )
    args = parser.parse_args()

    if not which(args.exe):
        print(f"ERROR: ceph executable '{args.exe}' doesn't exist")
        return STATUS_UNKNOWN

    if args.conf and not os.path.exists(args.conf):
        print(f"ERROR: ceph conf file '{args.conf}' doesn't exist")
        return STATUS_UNKNOWN

    if args.keyring and not os.path.exists(args.keyring):
        print(f"ERROR: keyring file '{args.keyring}' doesn't exist")
        return STATUS_UNKNOWN

    ceph_health = [args.exe]

    if args.monaddress:
        ceph_health.append('-m')
        ceph_health.append(args.monaddress)
    if args.cluster:
        ceph_health.append('--cluster')
        ceph_health.append(args.cluster)
    if args.conf:
        ceph_health.append('-c')
        ceph_health.append(args.conf)
    if args.id:
        ceph_health.append('--id')
        ceph_health.append(args.id)
    if args.name:
        ceph_health.append('--name')
        ceph_health.append(args.name)
    if args.keyring:
        ceph_health.append('--keyring')
        ceph_health.append(args.keyring)
    ceph_health.append('health')
    if args.detail:
        ceph_health.append('detail')

    ceph_health.append('--format')
    ceph_health.append('json')

    # exec command
    p = subprocess.Popen(
        ceph_health, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    output, err = p.communicate()
    try:
        output = json.loads(output)
    except ValueError:
        output = dict()

    if output:
        ret = STATUS_OK
        msg = ''
        extended = []
        for check, status in output['checks'].items():
            # skip check if not explicitly requested
            if args.check and not re.search(args.check, check):
                continue

            # skip check if muted
            if args.skip_muted and ('muted' in status and status['muted']):
                continue

            check_detail = f'{check}: {status["summary"]["message"]}'

            if status['severity'] == 'HEALTH_ERR':
                extended.append(msg)
                msg = f'CRITICAL: {check_detail}'
                ret = STATUS_ERROR
                continue

            if args.whitelist and re.search(
                args.whitelist, status['summary']['message']
            ):
                continue

            check_msg = f'WARNING: {check_detail}'
            if not msg:
                msg = check_msg
                ret = STATUS_WARNING
            else:
                extended.append(check_msg)

        if msg:
            print(msg)
        else:
            print('HEALTH OK')
        if extended:
            print('\n'.join(extended))

        return ret

    if err:
        # read only first line of error
        one_line = str(err).split('\n')[0]
        if '-1 ' in one_line:
            idx = one_line.rfind('-1 ')
            print(f'ERROR: {args.exe}: {one_line[idx + len("-1 "):]}')
        else:
            print(one_line)

    return STATUS_UNKNOWN


if __name__ == '__main__':
    sys.exit(main())
