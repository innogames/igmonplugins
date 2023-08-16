#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Redis Cluster Check

This script checks the status of a Redis Cluster.

A warning state represents a degraded cluster.
A critical state represents a broken cluster.

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


import argparse
import collections
import subprocess
import sys
import traceback
import typing

EXIT_OK = 0
EXIT_WARN = 1
EXIT_CRIT = 2
EXIT_UNKNOWN = 3

ClusterInfo = collections.namedtuple('ClusterInfo', [
    'cluster_current_epoch',
    'cluster_known_nodes',
    'cluster_my_epoch',
    'cluster_size',
    'cluster_slots_assigned',
    'cluster_slots_fail',
    'cluster_slots_ok',
    'cluster_slots_pfail',
    'cluster_state',
    'cluster_stats_messages_received',
    'cluster_stats_messages_sent',
])
ClusterNode = collections.namedtuple('ClusterNode', [
    'id', 'addr', 'flags', 'master', 'ping_sent', 'pong_recv', 'config_epoch',
    'link_state', 'slots',
])


def parse_args():
    """Parse CLI arguments"""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-p',
        '--port',
        type=int,
        default=7000,
        help='Port number of the Redis Cluster instance',
    )
    parser.add_argument(
        '-a',
        '--password',
        help='Redis password',
    )

    return parser.parse_args()


def main():
    """Main entrypoint for script"""
    args = parse_args()
    port = args.port
    password = args.password

    # Query the node for cluster state
    try:
        info = get_cluster_info(port, password)
        nodes = get_cluster_nodes(port, password)
    except ExecutionError:
        print('UNKNOWN - Could not retrieve cluster state')
        traceback.print_exc()
        sys.exit(EXIT_UNKNOWN)

    # Evaluate if there are any problems
    warns, crits = get_problems(info, nodes)
    if len(crits) > 0:
        print('CRITICAL - Cluster is broken')
        code = EXIT_CRIT
    elif len(warns) > 0:
        print('WARNING - Cluster is degraded')
        code = EXIT_WARN
    else:
        print('OK - Cluster is good')
        code = EXIT_OK

    # Print the details and exit
    for crit in crits:
        print(crit)
    for warn in warns:
        print(warn)

    sys.exit(code)


def get_problems(info: ClusterInfo, nodes: typing.Iterable[ClusterNode]):
    warns = []
    crits = []

    # Check the general cluster state from the point of view of the node
    if info.cluster_state != 'ok':
        crits.append('Cluster state is not ok')
    if int(info.cluster_slots_fail) > 0:
        crits.append(
            f'{info.cluster_slots_fail} slots are not reachable for all nodes',
        )
    if int(info.cluster_slots_pfail) > 0:
        warns.append(
            f'{info.cluster_slots_pfail} slots are not reachable for us',
        )

    # Check all known cluster nodes
    masters_by_ip = collections.defaultdict(lambda: 0)
    for node in nodes:
        flags = node.flags.split(',')
        if 'fail?' in flags:
            warns.append(f'{node.addr} is not reachable for us')
        elif 'fail' in flags:
            crits.append(f'{node.addr} is not reachable for all nodes')
        if 'noaddr' in flags:
            warns.append(f'No address known for {node.id}')
            continue

        # Count how many masters we got per host
        if 'master' in flags:
            ip = node.addr.split('@')[0].rsplit(':', 1)[0]
            masters_by_ip[ip] += 1

    # Report if a node has the same role twice. This is not important for
    # the functionality of the cluster, but the load on the double master
    # is increased, and we would like to make this visible in Nagios
    for ip, masters in masters_by_ip.items():
        if masters > 1:
            warns.append(f'{ip} has {masters} masters')

    return warns, crits


def get_cluster_info(port: int, password: str) -> ClusterInfo:
    """Get Redis Cluster info"""
    lines = execute_redis_cluster_cmd(port, password, 'info')

    # Parse command output
    fields = {}
    for line in lines:
        k, v = line.split(':')
        if k == 'Warning':
            continue

        fields[k] = v

    # There might be more stats depending on certain conditions, but we are
    # only interested in the ones that are always present
    relevant_keys = set(ClusterInfo._fields).intersection(fields.keys())
    relevant_fields = {k: fields[k] for k in relevant_keys}

    return ClusterInfo(**relevant_fields)


def get_cluster_nodes(
    port: int,
    password: str,
) -> typing.Generator[ClusterNode, None, None]:
    """Get Redis Cluster nodes"""
    lines = execute_redis_cluster_cmd(port, password, 'nodes')

    # Parse command output
    for line in lines:
        fields = line.split(maxsplit=9)
        if len(fields) < 8 or fields[7] not in ['connected', 'disconnected']:
            # Nothing we would expect here
            continue

        # Slaves don't have slots assigned
        if 'slave' in fields[2]:
            fields.append('')

        yield ClusterNode(*fields)


def execute_redis_cluster_cmd(
    port: int,
    password: str,
    cluster_cmd: str,
) -> typing.List[str]:
    """Execute an arbitrary Redis command on the node"""
    # Build command
    cmd = ['redis-cli', '-p', str(port)]
    if password:
        cmd.extend(['-a', password])
    cmd.append('cluster')
    cmd.append(cluster_cmd)

    # Execute
    try:
        res = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        lines = res.decode().splitlines()
    except subprocess.CalledProcessError as e:
        # Mask password inside exception
        if password:
            e.cmd[4] = '******'
        raise ExecutionError('Failed to execute command') from e

    # Check for NOAUTH auth error
    for line in lines:
        if line.startswith('NOAUTH'):
            raise ExecutionError(line)

    return lines


class ExecutionError(Exception):
    pass


if __name__ == '__main__':
    main()
