#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Load Balancing Pools Check

Copyright (c) 2021 InnoGames GmbH
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

import json
import redis

from argparse import ArgumentParser


def parse_args():
    parser = ArgumentParser()

    parser.add_argument(
        '-s', dest='redis_server', required=True,
        help='Redis servers to report the results to'
    )

    parser.add_argument(
        '-p', dest='redis_password',
        help='Password for Redis server authentication'
    )

    parser.add_argument(
        '-H', dest='lbpool_name', required=True,
        help='LBPool name to query data for'
    )

    return parser.parse_args()


def main():
    args = parse_args()

    data = get_redis_data(
        args.redis_server, args.redis_password, args.lbpool_name
    )

    exit_codes, outputs = evaluate_state(data)

    # TODO: Make the check aware of the cluster type and implement proper
    #  logic for selecting the final state of the check
    exit_code = None
    for i in exit_codes:
        if exit_code is None:
            exit_code = i
        if exit_code != ExitCodes.ok and i != ExitCodes.ok:
            exit_code = get_worse_exit_code(exit_code, i)
        elif exit_code != ExitCodes.ok and i == ExitCodes.ok:
            exit_code = ExitCodes.ok

    if exit_code == ExitCodes.ok:
        outputs.insert(0, 'LBPool is healthy')
    else:
        outputs.insert(0, 'LBPool is unhealthy')

    for line in outputs:
        print(line)
    exit(exit_code)


def evaluate_state(data):
    output = []
    exit_codes = []

    if len(data) < 1:
        return (
            [ExitCodes.critical],
            ['No data could be retrieved for given LBPool']
        )

    for pool_k, pool_v in data.items():
        hwlb_group = pool_v['hwlb_group']
        if not pool_v['nodes']:
            output.append(
                f'LBPool in {hwlb_group} has no LBNodes configured'
            )
            exit_codes.append(ExitCodes.critical)
            continue

        exit_code = ExitCodes.ok
        optimal_nodes = len(pool_v['nodes'])

        # We want to keep "None" text as it is nicer than 0 for human
        # perception.
        min_nodes = pool_v['min_nodes']
        if min_nodes == 0:
            min_nodes = None
        max_nodes = pool_v['max_nodes']
        if max_nodes == 0:
            max_nodes = None
        alive_nodes = pool_v['alive_nodes']

        if pool_v['health_checks']:
            if pool_v['in_testtool']:
                # All nodes are down
                if alive_nodes == 0:
                    exit_code = ExitCodes.critical
                # Less than min_nodes are alive
                elif min_nodes is not None and (alive_nodes < min_nodes):
                    exit_code = ExitCodes.critical
                # More than max_nodes are alive
                elif max_nodes is not None and (alive_nodes > max_nodes):
                    exit_code = ExitCodes.warning
                # All nodes are alive
                elif alive_nodes == optimal_nodes:
                    exit_code = ExitCodes.ok
                # More than min_nodes are alive, but not all of them
                elif min_nodes is not None and (alive_nodes >= min_nodes):
                    exit_code = ExitCodes.warning
                else:
                    exit_code = ExitCodes.unknown

                local_output = (
                    f'{hwlb_group}: {alive_nodes} of {optimal_nodes} '
                    f'alive (min: {min_nodes}, max: {max_nodes})'
                )
                local_output += get_nodes_output(pool_v['nodes'].items())

                output.append(local_output)
            else:
                exit_code = ExitCodes.unknown
                output.append(
                    f'{hwlb_group}: LBPool not monitored by testtool'
                )
        else:
            if optimal_nodes == 1:
                exit_code = ExitCodes.ok
                output.append(
                    f'{hwlb_group}: LBPool has no health checks and '
                    f'only 1 node'
                )
            else:
                exit_code = ExitCodes.warning
                output.append(
                    f'{hwlb_group}: LBPool has no health checks but '
                    f'{optimal_nodes} nodes'
                )

        exit_codes.append(exit_code)

    return exit_codes, output


def get_nodes_output(nodes):
    output = ''

    nodes_up = [k for k, v in nodes if v['state'] == 'up']
    nodes_down = [k for k, v in nodes if v['state'] == 'down']

    if nodes_up:
        output += '\n\tNodes up:\n\t\t'
        output += '\n\t\t'.join(nodes_up)

    if nodes_down:
        output += '\n\tNodes down:\n\t\t'
        output += '\n\t\t'.join(nodes_down)

    return output


# Unfortunately we can't just compare if the new exit code is bigger than
# the old exit code, as unknown (=3) is bigger than critical (=2) but
# critical is worse and should then take precedence.
def get_worse_exit_code(old_exit_code, new_exit_code):
    if old_exit_code <= new_exit_code < ExitCodes.unknown:
        return new_exit_code
    if old_exit_code == ExitCodes.ok and new_exit_code == ExitCodes.unknown:
        return new_exit_code
    if old_exit_code == ExitCodes.unknown and new_exit_code != ExitCodes.ok:
        return new_exit_code

    return old_exit_code


def get_redis_data(redis_server, redis_password, lbpool_name):
    r = redis.Redis(
        host=redis_server, port=6379, db=0, password=redis_password
    )

    keys = [key.decode() for key in r.keys(f'{lbpool_name}_lbpool_nodes*')]
    values = [json.loads(value.decode()) for value in r.mget(keys)]

    data = dict(zip(keys, values))

    return data


class ExitCodes:
    ok = 0
    warning = 1
    critical = 2
    unknown = 3


if __name__ == "__main__":
    main()
