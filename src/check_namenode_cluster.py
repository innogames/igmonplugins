#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Namenode cluster health

This script checks that there is exactly one active node in the cluster
and that the cluster nodes have not entered safe mode.

Copyright (c) 2024 InnoGames GmbH
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

import subprocess
import sys
from typing import (
    Dict,
    Iterable,
    List,
    Tuple,
)


def main() -> Tuple[int, str]:
    service_states = get_service_state()
    safemode_states = get_safemode_state()
    warns, crits, unknowns = get_problems(service_states, safemode_states)
    code, out = get_output(warns, crits, unknowns)

    return code, out


def get_problems(
    service_states: Dict[str, str],
    safemode_states: Dict[str, str],
) -> Tuple[List[str], List[str], List[str]]:
    warns = []
    crits = []
    unknowns = []

    if len(service_states.keys()) < 2:
        unknowns.append('There are less than two nodes in the cluster')

    # Make sure there is exactly one active node
    active_node = None
    for node, service_state in service_states.items():
        if service_state == 'active':
            if active_node is not None:
                crits.append('Multiple active nodes found')

            active_node = node
        elif service_state != 'standby':
            crits.append(f'Unexpected service state: {service_state}')

    if active_node is None:
        crits.append('No active node found')

    # Make sure active node is not in safe mode
    if active_node is not None:
        if active_node in safemode_states:
            safemode_state = safemode_states[active_node]
            if safemode_state == 'ON':
                crits.append(f'Active node {active_node} is in safe mode')
        else:
            crits.append(f'No safe mode state found for {active_node}')

    # Check if there are other nodes in safe mode
    for node, safemode_state in safemode_states.items():
        if node == active_node:
            continue
        if safemode_state == 'ON':
            warns.append(f'Standby node {node} is in safe mode')

    return warns, crits, unknowns


def get_output(
    warns: List[str],
    crits: List[str],
    unknowns: List[str],
) -> Tuple[int, str]:
    if len(crits) > 0:
        code = 2
        out = 'CRITICAL'
    elif len(warns) > 0:
        code = 1
        out = 'WARNING'
    elif len(unknowns) > 0:
        code = 3
        out = 'UNKNOWN'
    else:
        return 0, 'OK'

    out += f' - {", ".join(crits + warns + unknowns)}'

    return code, out


def get_service_state() -> Dict[str, str]:
    res = call_hdfs(['haadmin', '-getAllServiceState'])
    service_state = {}
    for line in res.splitlines():
        line = line.strip()
        if line == '':
            continue

        addr, state = line.split(maxsplit=1)
        service_state[addr] = state

    return service_state


def get_safemode_state() -> Dict[str, str]:
    res = call_hdfs(['dfsadmin', '-safemode', 'get'])
    safemode_state = {}
    for line in res.splitlines():
        line = line.strip()
        if line == '':
            continue

        parts = line.split()
        state = parts[3]
        addr = parts[5]
        addr_parts = addr.split(':')
        host = addr_parts[0].split('/')[0]
        addr = f'{host}:{addr_parts[1]}'

        safemode_state[addr] = state

    return safemode_state


def call_hdfs(args: Iterable[str]) -> str:
    cmd = subprocess.run(
        ['hdfs', *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return cmd.stdout.decode()


if __name__ == '__main__':
    exit_code, output = main()
    print(output)
    sys.exit(exit_code)
