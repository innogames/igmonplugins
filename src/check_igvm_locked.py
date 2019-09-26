#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - IGVM locked Check
This script checks if a vm or hypervisor is igvm_locked
if so the check will go to the state warning never critical.
Copyright (c) 2019 InnoGames GmbH
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

import argparse
import logging

from adminapi.dataset import Query
from adminapi.dataset.filters import Any, Not
from datetime import datetime, timedelta, timezone
from subprocess import Popen, DEVNULL, PIPE

logging.basicConfig(
    format='%(levelname)-8s [%(filename)s:%(lineno)d] %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description='nagios check for long running igvm_locked attribute',
    )
    parser.add_argument(
        'monitoring_master', type=str,
        help='Server which will receive the passive check results')
    parser.add_argument(
        '--time-in-minutes', type=int, default=480,
        help='Time in minutes that a machine can be igvm_locked before being '
             'considered stale'
    )
    parser.add_argument(
        '-v', action='store_true', dest='verbose',
        help='Run the check in verbose mode'
    )
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.ERROR)

    master = args.monitoring_master

    max_time = args.time_in_minutes
    max_hours = int(max_time / 60)
    max_minutes = int(max_time - max_hours * 60)

    hosts = Query({'servertype': Any('hypervisor', 'vm'),
                   'no_monitoring': False, 'state': Not('retired')},
                  ['igvm_locked', 'hostname'])

    hosts_not_locked = []
    hosts_locked = []

    for host in hosts:
        if not host['igvm_locked']:
            hosts_not_locked.append(host)
            continue

        locked_time = datetime.now(timezone.utc) - host['igvm_locked']
        if locked_time >= timedelta(minutes=max_time):
            hosts_locked.append(host)
        else:
            hosts_not_locked.append(host)

    console_out(hosts_locked, max_minutes, max_hours)

    results = nagios_create(
        hosts_locked, hosts_not_locked, max_minutes, max_hours
    )

    nsca_output = ""
    exit_code = 0
    for result in results:
        # send_nsca has a maximum input buffer of ~5100 bytes.
        # We need to split our data in chunks no bigger than 5000 characters,
        # otherwise Nagios will get partial output and a lot of services won't
        # get new data
        if (len(nsca_output) + len(result)) >= 5000:
            ret = nagios_send(master, nsca_output)
            if not ret:
                exit_code = 1
            nsca_output = result
        else:
            nsca_output += result

    # This last nagios send, cover the remaining output that wasn't sent
    # inside the loop.
    ret = nagios_send(master, nsca_output)
    if not ret:
        exit_code = 1

    if exit_code:
        logger.error('Failed to submit NSCA results')
    exit(exit_code)


def nagios_create(hosts_locked, hosts_not_locked, max_minutes, max_hours):
    template = (
        '{}\tigvm_locked\t{}\tWARNING - IGVM-locked longer than {}h {}m\x17'
    )
    out_locked = [
        template.format(
            host['hostname'], 1, max_hours, max_minutes
        ) for host in hosts_locked
    ]

    template = '{}\tigvm_locked\t{}\tOK\x17'
    out_not_locked = [
        template.format(host['hostname'], 0) for host in hosts_not_locked
    ]

    return out_locked + out_not_locked


def nagios_send(host, nsca_output):
    nsca = Popen(
        [
            '/usr/sbin/send_nsca',
            '-H', host,
            '-c', '/etc/send_nsca.cfg',
        ],
        stdin=PIPE,
        stdout=DEVNULL,
        stderr=DEVNULL,
    )
    nsca.communicate(nsca_output.encode())
    returncode = nsca.wait()

    return not bool(returncode)


def console_out(hosts_locked, max_minutes, max_hours):
    locked_hosts = ['{}:{}'.format(host['hostname'], host['igvm_locked'])
                    for host in hosts_locked]

    if not locked_hosts:
        logger.info(
            'No servers locked for more than {}h and {}m'.format(
                max_hours, max_minutes
            )
        )
        return

    logger.info(
        '{} servers are locked for more than {}h and {}m: \n{}'.format(
            len(locked_hosts), max_hours, max_minutes, '\n'.join(locked_hosts)
        )
    )


if __name__ == '__main__':
    main()
