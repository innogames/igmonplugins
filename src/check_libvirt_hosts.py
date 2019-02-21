#!/usr/bin/env python
"""InnoGames Monitoring Plugins - Libvirt Hosts Check

Copyright (c) 2019 InnoGames GmbH
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

from sys import exit

from libvirt import openReadOnly, libvirtError
import libvirt
import re

reason_names = {
    libvirt.VIR_DOMAIN_RUNNING: {
        libvirt.VIR_DOMAIN_RUNNING_UNKNOWN:       "VIR_DOMAIN_RUNNING_UNKNOWN",
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


class ExitCodes:
    ok = 0
    warning = 1
    critical = 2
    unknown = 3


def print_nagios_message(code, reason):
    if code == ExitCodes.ok:
        state_text = 'OK'
    elif code == ExitCodes.warning:
        state_text = 'WARNING'
    elif code == ExitCodes.critical:
        state_text = 'CRITICAL'
    else:
        state_text = 'UNKNOWN'
    print("{0} - {1}".format(state_text, reason))


def print_domains(domains):
    for d in domains:
        state, reason = d.state()
        m = re.match(r'(\d+_)?(?P<vmname>[\w\.\d-]+)', d.name())
        name = m.group('vmname')
        print("{0} - {1}".format(name, reason_names.get(state, "unknown")
              .get(reason, "unknown")))


def check(domains):
    inactive_domains = [d for d in domains if not d.isActive()]
    if inactive_domains:
        return ExitCodes.warning, 'Found non-running domains: {0}'.format(
            ', '.join(d.name() for d in inactive_domains)
            )
    return ExitCodes.ok, 'All defined domains are running'


def main():
    try:
        conn = openReadOnly(None)
    except libvirtError as error:
        print_nagios_message(ExitCodes.warning,
                             'Could not connect to libvirt: {0}'
                             .format(str(error))
                             )
        exit(ExitCodes.warning)

    domains = conn.listAllDomains()
    code, reason = check(domains)
    print_nagios_message(code, reason)
    print_domains(domains)
    exit(code)


if __name__ == '__main__':
    main()
