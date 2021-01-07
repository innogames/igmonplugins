#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Libvirt Hosts Check

Copyright (c) 2021 InnoGames GmbH
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

import re
import socket
from sys import exit

import libvirt
from adminapi.dataset import Query
from libvirt import openReadOnly, libvirtError

reason_names = {
    libvirt.VIR_DOMAIN_RUNNING: {
        libvirt.VIR_DOMAIN_RUNNING_UNKNOWN: "VIR_DOMAIN_RUNNING_UNKNOWN",
        libvirt.VIR_DOMAIN_RUNNING_BOOTED: "VIR_DOMAIN_RUNNING_BOOTED",
        libvirt.VIR_DOMAIN_RUNNING_MIGRATED: "VIR_DOMAIN_RUNNING_MIGRATED",
        libvirt.VIR_DOMAIN_RUNNING_RESTORED: "VIR_DOMAIN_RUNNING_RESTORED",
        libvirt.VIR_DOMAIN_RUNNING_FROM_SNAPSHOT:
            "VIR_DOMAIN_RUNNING_FROM_SNAPSHOT",
        libvirt.VIR_DOMAIN_RUNNING_UNPAUSED:
            "VIR_DOMAIN_RUNNING_UNPAUSED",
        libvirt.VIR_DOMAIN_RUNNING_MIGRATION_CANCELED:
            "VIR_DOMAIN_RUNNING_MIGRATION_CANCELED",
        libvirt.VIR_DOMAIN_RUNNING_SAVE_CANCELED:
            "VIR_DOMAIN_RUNNING_SAVE_CANCELED",
        libvirt.VIR_DOMAIN_RUNNING_WAKEUP: "VIR_DOMAIN_RUNNING_WAKEUP",
        libvirt.VIR_DOMAIN_RUNNING_CRASHED: "VIR_DOMAIN_RUNNING_CRASHED",
        libvirt.VIR_DOMAIN_RUNNING_POSTCOPY: "VIR_DOMAIN_RUNNING_POSTCOPY",
        11: "VIR_DOMAIN_RUNNING_LAST"
    },
    libvirt.VIR_DOMAIN_BLOCKED: {
        libvirt.VIR_DOMAIN_BLOCKED_UNKNOWN: "VIR_DOMAIN_BLOCKED_UNKNOWN",
        1: "VIR_DOMAIN_BLOCKED_LAST"
    },
    libvirt.VIR_DOMAIN_PAUSED: {
        libvirt.VIR_DOMAIN_PAUSED_UNKNOWN: "VIR_DOMAIN_PAUSED_UNKNOWN",
        libvirt.VIR_DOMAIN_PAUSED_USER: "VIR_DOMAIN_PAUSED_USER",
        libvirt.VIR_DOMAIN_PAUSED_MIGRATION: "VIR_DOMAIN_PAUSED_MIGRATION",
        libvirt.VIR_DOMAIN_PAUSED_SAVE: "VIR_DOMAIN_PAUSED_SAVE",
        libvirt.VIR_DOMAIN_PAUSED_DUMP: "VIR_DOMAIN_PAUSED_DUMP",
        libvirt.VIR_DOMAIN_PAUSED_IOERROR: "VIR_DOMAIN_PAUSED_IOERROR",
        libvirt.VIR_DOMAIN_PAUSED_WATCHDOG: "VIR_DOMAIN_PAUSED_WATCHDOG",
        libvirt.VIR_DOMAIN_PAUSED_FROM_SNAPSHOT:
            "VIR_DOMAIN_PAUSED_FROM_SNAPSHOT",
        libvirt.VIR_DOMAIN_PAUSED_SHUTTING_DOWN:
            "VIR_DOMAIN_PAUSED_SHUTTING_DOWN",
        libvirt.VIR_DOMAIN_PAUSED_SNAPSHOT: "VIR_DOMAIN_PAUSED_SNAPSHOT",
        libvirt.VIR_DOMAIN_PAUSED_CRASHED: "VIR_DOMAIN_PAUSED_CRASHED",
        libvirt.VIR_DOMAIN_PAUSED_STARTING_UP: "VIR_DOMAIN_PAUSED_STARTING_UP",
        libvirt.VIR_DOMAIN_PAUSED_POSTCOPY: "VIR_DOMAIN_PAUSED_POSTCOPY",
        libvirt.VIR_DOMAIN_PAUSED_POSTCOPY_FAILED:
            "VIR_DOMAIN_PAUSED_POSTCOPY_FAILED",
        14: "VIR_DOMAIN_PAUSED_LAST",
    },
    libvirt.VIR_DOMAIN_SHUTDOWN: {
        libvirt.VIR_DOMAIN_SHUTDOWN_UNKNOWN: "VIR_DOMAIN_SHUTDOWN_UNKNOWN",
        libvirt.VIR_DOMAIN_SHUTDOWN_USER: "VIR_DOMAIN_SHUTDOWN_USER",
        2: "VIR_DOMAIN_SHUTDOWN_LAST"
    },
    libvirt.VIR_DOMAIN_SHUTOFF: {
        libvirt.VIR_DOMAIN_SHUTOFF_UNKNOWN: "VIR_DOMAIN_SHUTOFF_UNKNOWN",
        libvirt.VIR_DOMAIN_SHUTOFF_SHUTDOWN: "VIR_DOMAIN_SHUTOFF_SHUTDOWN",
        libvirt.VIR_DOMAIN_SHUTOFF_DESTROYED: "VIR_DOMAIN_SHUTOFF_DESTROYED",
        libvirt.VIR_DOMAIN_SHUTOFF_CRASHED: "VIR_DOMAIN_SHUTOFF_CRASHED",
        libvirt.VIR_DOMAIN_SHUTOFF_MIGRATED: "VIR_DOMAIN_SHUTOFF_MIGRATED",
        libvirt.VIR_DOMAIN_SHUTOFF_SAVED: "VIR_DOMAIN_SHUTOFF_SAVED",
        libvirt.VIR_DOMAIN_SHUTOFF_FAILED: "VIR_DOMAIN_SHUTOFF_FAILED",
        libvirt.VIR_DOMAIN_SHUTOFF_FROM_SNAPSHOT:
            "VIR_DOMAIN_SHUTOFF_FROM_SNAPSHOT",
        8: "VIR_DOMAIN_SHUTOFF_DAEMON",
        9: "VIR_DOMAIN_SHUTOFF_LAST"
    },
    libvirt.VIR_DOMAIN_CRASHED: {
        libvirt.VIR_DOMAIN_CRASHED_UNKNOWN: "VIR_DOMAIN_CRASHED_UNKNOWN",
        libvirt.VIR_DOMAIN_CRASHED_PANICKED: "VIR_DOMAIN_CRASHED_PANICKED",
        2: "VIR_DOMAIN_CRASHED_LAST"
    },
    libvirt.VIR_DOMAIN_NOSTATE: {
        libvirt.VIR_DOMAIN_NOSTATE_UNKNOWN: "VIR_DOMAIN_NOSTATE_UNKNOWN",
        1: "VIR_DOMAIN_NOSTATE_LAST",
    }
}


def main():
    try:
        domains = parse_libvirt_domains(query_libvirt_domains())
    except libvirtError as error:
        print_nagios_message(
            ExitCodes.warning,
            ['Could not connect to libvirt: {0}'.format(str(error))]
        )
        exit(ExitCodes.warning)

    vms = query_serveradmin_vms()

    code, reason = check(domains, vms)
    print_nagios_message(code, reason)
    exit(code)


def check(domains, vms):
    exit_code = ExitCodes.ok
    exit_message = []

    # We do a couple of different checks:
    #  - Check if retired VMs are still running on the hypervisor
    #  - Check if there are VMs defined in libvirt that are not associated to
    #  this hypervisor in Serveradmin
    #  - Check if there are VMs associated to this HV in Serveradmin but not
    #  defined in libvirt
    #  - Check if there are VMs in libvirt in a non-running state

    #  - Check if retired VMs are still running on the hypervisor
    retired_vms = set(
        vm['hostname'] for vm in vms.values() if vm['state'] == 'retired'
    )
    if len(retired_vms) > 0:
        exit_code = max(exit_code, ExitCodes.critical)
        exit_message.append(
            'HV contains retired VMs still running: {}'.format(
                ', '.join(retired_vms)
            )
        )

    vm_object_ids = set(vms.keys())
    domain_object_ids = set(domains.keys())

    #  - Check if there are VMs defined in libvirt that are not associated to
    #  this hypervisor in Serveradmin
    not_in_serveradmin = domain_object_ids - vm_object_ids
    if len(not_in_serveradmin) > 0:
        hostnames = [domains[id]['hostname'] for id in not_in_serveradmin]
        exit_code = max(exit_code, ExitCodes.critical)
        exit_message.append(
            'The following domains do not belong to this HV in Serveradmin: '
            '{}'.format(', '.join(hostnames))
        )

    #  - Check if there are VMs associated to this HV in Serveradmin but not
    #  defined in libvirt
    not_in_libvirt = vm_object_ids - domain_object_ids
    if len(not_in_libvirt) > 0:
        hostnames = [vms[id]['hostname'] for id in not_in_libvirt]
        exit_code = max(exit_code, ExitCodes.warning)
        exit_message.append(
            'The following VMs are assigned in Serveradmin but missing in '
            'libvirt: {}'.format(', '.join(hostnames))
        )

    #  - Check if there are VMs in libvirt in a non-running state
    inactive_domains = set(
        d['hostname'] for d in domains.values() if not d['is_active'])
    if len(inactive_domains) > 0:
        exit_code = max(exit_code, ExitCodes.warning)
        exit_message.append(
            'Found non-running domains: {}'.format(', '.join(inactive_domains))
        )

    # If none of the conditions are met, the exit code is still OK,
    # so we produce the OK message
    if exit_code == ExitCodes.ok:
        exit_message.append('All domains are running')

    return exit_code, exit_message


def query_serveradmin_vms():
    """Query Serveradmin for the VMs associated to this Hypervisor

    This function will return a dictionary where the keys are
    <objectid>_<hostname>, just like our libvirt domains and the values are
    another dictionary which holds the DatasetObject data.
    """
    hostname = socket.gethostname()

    vms = Query(
        {'servertype': 'vm', 'hypervisor': hostname},
        ['hostname', 'state', 'object_id']
    )
    # This is a trick to get pure dicts out of the serveradmin data, since
    # we don't need to edit the queried objects.
    vms = {f"{vm['object_id']}_{vm['hostname']}": vm.copy() for vm in vms}

    return vms


def query_libvirt_domains():
    try:
        conn = openReadOnly(None)
    except libvirtError as error:
        raise

    libvirt_domains = conn.listAllDomains()

    return libvirt_domains


def parse_libvirt_domains(domains):
    parsed_domains = {}

    for d in domains:
        state, reason = d.state()

        m = re.match(
            r'(?P<object_id>\d+)?_?(?P<hostname>[\w\.\d-]+)',
            d.name()
        )
        hostname = m.group('hostname')
        object_id = m.group('object_id')

        parsed_domains.setdefault(
            d.name(),
            {
                'object_id': int(object_id),
                'hostname': hostname,
                'state': reason_names.get(state, {}).get(reason, "unknown"),
                'is_active': d.isActive(),
            }
        )

    return parsed_domains


def print_nagios_message(code, reason):
    if code == ExitCodes.ok:
        state_text = 'OK'
    elif code == ExitCodes.warning:
        state_text = 'WARNING'
    elif code == ExitCodes.critical:
        state_text = 'CRITICAL'
    else:
        state_text = 'UNKNOWN'
    print("{0} - {1}".format(state_text, reason.pop(0)))
    for line in reason:
        print(line)


class ExitCodes:
    ok = 0
    warning = 1
    critical = 2
    unknown = 3


if __name__ == '__main__':
    main()
