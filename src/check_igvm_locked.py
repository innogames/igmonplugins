#!/usr/bin/env python
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

from adminapi.dataset import Query
from adminapi.dataset.filters import Not, Any
from datetime import datetime, timezone, timedelta
from subprocess import Popen, PIPE, DEVNULL

import argparse


def main():
    parser = argparse.ArgumentParser(
        description='nagios check for long running igvm_locked attribute',
    )
    parser.add_argument("monitoring_master", type=str)
    parser.add_argument("--time-in-minutes", type=int, default=480)
    parser.add_argument("-v")
    args = parser.parse_args()

    max_minutes = args.time_in_minutes
    master = args.monitoring_master

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
        if locked_time > timedelta(minutes=max_minutes):
            hosts_locked.append(host)
        else:
            hosts_not_locked.append(host)
    if args.v:
        console_out(hosts_locked, max_minutes)
    nsca_out = nagios_create(hosts_locked, hosts_not_locked, max_minutes)
    nagios_send(master, nsca_out)


def nagios_create(hosts_locked, hosts_not_locked, max_minutes):
    nsca_output = ""
    for host in hosts_locked:
        nsca_output += ("{}\tigvm_locked\t{}\tWARNING - IGVM-locked longer"
                        " than {}h {}m\x17"
                        .format(host['hostname'], 1, int(max_minutes / 60),
                                int(max_minutes - 60 * (max_minutes / 60))))

    for host in hosts_not_locked:
        nsca_output += ('{}\tigvm_locked\t{}\tOK\x17'
                        .format(host['hostname'], 0))

    return nsca_output


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


def console_out(hosts_locked, max_minutes):
    count_locked_servers = 0
    locked_hosts = ""
    for host in hosts_locked:
        locked_hosts += "{}:{}\n".format(host['hostname'], host['igvm_locked'])
        count_locked_servers += 1

    if locked_hosts == "":
        print("No igvm_locked Servers !!!")
    else:
        hours = int(max_minutes / 60)
        minutes = max_minutes - (int(max_minutes / 60) * 60)

        print("({}) server/s are/is locked longer than {}h and {}m : \n{}"
              .format(count_locked_servers, hours, minutes, locked_hosts))


if __name__ == '__main__':
    main()
