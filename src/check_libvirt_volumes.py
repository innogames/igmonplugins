#!/usr/bin/env python3

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

from argparse import ArgumentParser
from libvirt import openReadOnly, libvirtError
from sys import exit

import libvirt
import psutil
import re
import os


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
        conn = openReadOnly(None)
    except libvirtError as error:
        print_nagios_message(
            ExitCodes.unknown,
            'Could not connect to libvirt: {0}'.format(str(error))
        )
        exit(ExitCodes.unknown)

    domains = conn.listAllDomains()
    pool = conn.storagePoolLookupByName(args.pool)
    volumes = [
        pool.storageVolLookupByName(vol_name)
        for vol_name in pool.listVolumes()
    ]

    code, reason, bad_volumes = check(domains, volumes, args.ignore)
    print_nagios_message(code, reason)
    print_bad_volumes(bad_volumes)
    exit(code)


def check(domains, volumes, ignore):
    code = ExitCodes.ok
    reason = 'All volumes are used by VMs'
    
    domain_names = {d.name() for d in domains}
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
        
        code = ExitCodes.warning
        reason = 'Found volumes not corresponding to defined VMs'
        bad_volumes.append((vol_path, mounted))

    return code, reason, bad_volumes


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


def print_bad_volumes(bad_volumes):
    for path, mounted in bad_volumes:
        print('{}: {}'.format(
            path,
            'unused and mounted' if mounted else 'unused')
        )


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


class ExitCodes:
    ok = 0
    warning = 1
    critical = 2
    unknown = 3


if __name__ == '__main__':
    main()
