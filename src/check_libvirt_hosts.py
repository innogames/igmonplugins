#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Libvirt Hosts Check

This check evaluates if the domains running on the hypervisor match the VM
information contained in Serveradmin. It will also make sure that unused
volumes are reported for cleanup.

Copyright (c) 2024 InnoGames GmbH
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
import collections
import os
import re
import socket
from sys import exit

import libvirt
import psutil
from adminapi.dataset import Query
from argparse import ArgumentParser
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


def parse_args():
    parser = ArgumentParser()
    parser.add_argument(
        'pool', help='Storage pool', type=str,
    )
    parser.add_argument(
        '--ignore', help='Ignore volumes by regexp', type=str, default=None
    )

    return parser.parse_args()


def main():
    args = parse_args()

    try:
        libvirt_connection = get_libvirt_connection()
    except libvirtError as error:
        print_nagios_message(
            ExitCodes.warning,
            [f'Could not connect to libvirt: {str(error)}']
        )
        exit(ExitCodes.warning)

    domains = parse_libvirt_domains(query_libvirt_domains(libvirt_connection))
    volumes = query_libvirt_volumes(libvirt_connection, args.pool)

    vms = query_serveradmin_vms()

    exit_code = 0
    outputs = collections.defaultdict(lambda: [])

    for code, reason in [
        check_inactive_domains(domains),
        check_extraneous_domains(domains, vms),
        check_missing_domains(domains, vms),
        check_retired_vms(vms),
        check_volumes(domains, volumes, args.ignore),
    ]:
        exit_code = get_worst_exit_code(exit_code, code)
        outputs[code].append(reason)

    print_nagios_message(exit_code, outputs)
    exit(exit_code)


def check_missing_domains(domains, vms):
    vm_object_ids = set(vms.keys())
    domain_object_ids = set(domains.keys())

    #  - Check if there are VMs associated to this HV in Serveradmin but not
    #  defined in libvirt
    not_in_libvirt = vm_object_ids - domain_object_ids
    if len(not_in_libvirt) > 0:
        hostnames = [vms[id]['hostname'] for id in not_in_libvirt]
        exit_code = ExitCodes.warning
        exit_message = (
            'The following VMs are assigned in Serveradmin but missing in '
            f'libvirt: {indent_hostname_list(hostnames)}'
        )
    else:
        exit_code = ExitCodes.ok
        exit_message = 'All VMs assigned in Serveradmin are defined in libvirt'

    return exit_code, exit_message


def check_extraneous_domains(domains, vms):
    #  - Check if there are VMs defined in libvirt that are not associated to
    #  this hypervisor in Serveradmin
    vm_object_ids = set(vms.keys())
    domain_object_ids = set(domains.keys())

    not_in_serveradmin = domain_object_ids - vm_object_ids
    if len(not_in_serveradmin) > 0:
        hostnames = [domains[id]['hostname'] for id in not_in_serveradmin]
        exit_code = ExitCodes.critical
        exit_message = (
            'The following domains do not belong to this HV in '
            f'Serveradmin: {indent_hostname_list(hostnames)}'
        )
    else:
        exit_code = ExitCodes.ok
        exit_message = 'All domains are assigned to this HV in Serveradmin'

    return exit_code, exit_message


def check_inactive_domains(domains):
    #  - Check if there are VMs in libvirt in a non-running state
    inactive_domains = set(
        d['hostname'] for d in domains.values() if not d['is_active'])
    if len(inactive_domains) > 0:
        code = ExitCodes.warning
        message = 'Found non-running domains:'
        message += indent_hostname_list(inactive_domains)
    else:
        code = ExitCodes.ok
        message = 'All domains are running'

    return code, message


def check_retired_vms(vms):
    #  - Check if retired VMs are still running on the hypervisor
    # We are only checking if VMs with retired state are associated to the
    # hypervisor. We don't check if the VM is still present on libvirt.
    # If you just clean up the hypervisor attribute in Serveradmin, then the
    # check will complain that the VM doesn't belong on this Hypervisor.
    retired_vms = set(
        vm['hostname'] for vm in vms.values() if vm['state'] == 'retired'
    )
    if len(retired_vms) > 0:
        code = ExitCodes.critical
        message = 'HV contains retired VMs assigned:'
        message += indent_hostname_list(retired_vms)
    else:
        code = ExitCodes.ok
        message = 'No retired VMs were found assigned'

    return code, message


def check_volumes(domains, volumes, ignore):
    domain_names = domains.keys()
    mounts = {resolve_symlink(m.device) for m in psutil.disk_partitions()}

    ignore_re = re.compile(ignore) if ignore else None

    bad_volumes = []
    for volume in volumes:
        vol_path = volume.path()

        if ignore_re and ignore_re.match(os.path.basename(vol_path)):
            continue

        if os.path.basename(vol_path) in domain_names:
            continue

        mounted = resolve_symlink(vol_path) in mounts

        bad_volumes.append((vol_path, mounted))

    if len(bad_volumes) > 0:
        code = ExitCodes.warning
        message = 'Found volumes not corresponding to defined VMs:'
        message += parse_bad_volumes(bad_volumes)
    else:
        code = ExitCodes.ok
        message = 'All volumes are used by VMs'

    return code, message


def query_serveradmin_vms():
    """Query Serveradmin for the VMs associated to this Hypervisor

    This function will return a dictionary where the keys are
    <objectid>_<hostname>, just like our libvirt domains and the values are
    another dictionary which holds the DatasetObject data.
    """
    hostname = socket.gethostname()

    vms = Query(
        {'servertype': 'vm', 'hypervisor': hostname},
        ['hostname', 'object_id', 'state']
    )
    # This is a trick to get pure dicts out of the serveradmin data, since
    # we don't need to edit the queried objects.
    vms = {f"{vm['object_id']}_{vm['hostname']}": vm.copy() for vm in vms}

    return vms


def query_libvirt_domains(libvirt_connection):
    libvirt_domains = libvirt_connection.listAllDomains()

    return libvirt_domains


def query_libvirt_volumes(libvirt_connection, pool):
    pool = libvirt_connection.storagePoolLookupByName(pool)
    volumes = [
        pool.storageVolLookupByName(vol_name)
        for vol_name in pool.listVolumes()
    ]

    return volumes


def get_libvirt_connection():
    try:
        conn = openReadOnly(None)
    except libvirtError as error:
        raise
    return conn


def parse_libvirt_domains(domains):
    parsed_domains = {}

    for d in domains:
        state, reason = d.state()

        split_name = d.name().split('_')
        hostname = split_name[1]
        object_id = split_name[0]

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


def parse_bad_volumes(bad_volumes):
    output = ''
    for path, mounted in bad_volumes:
        state = 'unused and mounted' if mounted else 'unused'
        output += f'\n\t- {path}: {state}'
    return output


def resolve_symlink(path):
    if os.path.islink(path):
        try:
            return os.path.realpath(os.readlink(path))
        except FileNotFoundError:
            # There is a slight chance that libvirt will delete some storage
            # volumes while this check is running. Let's just pretend we
            # didn't see it.
            return None
    return path


# Unfortunately we can't just compare if the new exit code is bigger than
# the old exit code, as unknown (=3) is bigger than critical (=2) but
# critical is worse and should then take precedence.
def get_worst_exit_code(old_exit_code, new_exit_code):
    if old_exit_code <= new_exit_code < ExitCodes.unknown:
        return new_exit_code
    if old_exit_code == ExitCodes.ok and new_exit_code == ExitCodes.unknown:
        return new_exit_code
    if old_exit_code == ExitCodes.unknown and new_exit_code != ExitCodes.ok:
        return new_exit_code

    return old_exit_code


def indent_hostname_list(hostnames):
    output = ''
    for name in hostnames:
        output += f'\n\t- {name}'

    return output


def print_nagios_message(code, outputs):
    if code == ExitCodes.ok:
        print(f'{get_state_text(code)} - Host and VMs are in a good state')
    else:
        print(f'{get_state_text(code)} - There are inconsistencies')

    for code, output in outputs.items():
        print(f'{get_state_text(code)}:')
        for entry in output:
            print(f'\t{entry}')


def get_state_text(exit_code):
    if exit_code == ExitCodes.ok:
        state_text = 'OK'
    elif exit_code == ExitCodes.warning:
        state_text = 'WARNING'
    elif exit_code == ExitCodes.critical:
        state_text = 'CRITICAL'
    else:
        state_text = 'UNKNOWN'

    return state_text


class ExitCodes:
    ok = 0
    warning = 1
    critical = 2
    unknown = 3


if __name__ == '__main__':
    main()
