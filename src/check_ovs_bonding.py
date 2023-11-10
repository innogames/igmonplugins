#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Linux OVS Bond Check

This script checks the status of bonded network interfaces on OVS.

Copyright (c) 2023 InnoGames GmbH
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

import shutil
import sys
from subprocess import check_output, PIPE


def main():
    if not shutil.which('ovs-appctl'):
        print('CRITICAL: There is no ovs-appctl available to query the bond status')
        sys.exit(2)

    bonds = get_bonds()

    reports = []

    for bond, data in bonds.items():
        data.update(get_bond_information(bond))

        # Check for LACP state
        if data['bond_mode'] != 'active-backup' and data['lacp_status'] != 'negotiated':
            reports.append(f'{bond}: Inconsistent LACP state')

        # Check for down members
        down_members = [member for member, status in data['members'].items() if status != 'enabled']
        if len(down_members) == 1:
            reports.append(f'{bond}: Member {down_members[0]} is not up')
        elif len(down_members) > 1:
            reports.append(f'{bond}: Members {down_members.join(",")} are not up')

    if len(reports) == 0:
        print('OK: All bonded interfaces are healthy')
        sys.exit(0)

    for report in reports:
        print(f'WARNING: {report}')

    sys.exit(1)


def get_bonds():
    """
    # ovs-appctl bond/list
    bond	type	recircID	members
    bond0	balance-slb	1	eno2, eno1
    """
    res = {}
    bond_list = run_command('ovs-appctl bond/list')
    bond_list = bond_list[1:]
    for bond in bond_list:
        data = bond.split('\t')
        bond_name = data[0]
        bond_type = data[1]
        res[bond_name] = {'bond_mode': bond_type}

    return res


def get_bond_information(bond_name):
    """
    # ovs-appctl bond/show bond0
    ---- bond0 ----
    bond_mode: active-backup
    bond may use recirculation: no, Recirc-ID : -1
    bond-hash-basis: 0
    lb_output action: disabled, bond-id: -1
    updelay: 200 ms
    downdelay: 200 ms
    lacp_status: off
    lacp_fallback_ab: false
    active-backup primary: <none>
    active member mac: 5c:6f:69:85:5f:e0(enp2s0f0np0)

    member enp2s0f0np0: enabled
    active member
    may_enable: true

    member enp2s0f1np1: enabled
    may_enable: true
    """
    bond_info = run_command(f'ovs-appctl bond/show {bond_name}')
    res = {'members': {}}
    for line in bond_info:
        if line.startswith('lacp_status'):
            res['lacp_status'] = line.split()[1]
        if line.startswith('member'):
            data = line.split()
            member = data[1][:-1]
            state = data[2]
            res['members'][member] = state

    return res


def run_command(command):
    res = check_output(
        command.split(' '),
        close_fds=False, universal_newlines=True, stderr=PIPE
    )
    return res.splitlines()


if __name__ == '__main__':
    main()
