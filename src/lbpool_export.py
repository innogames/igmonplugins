#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Load Balancing Pools Data Exporter

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
        '-H', dest='redis_servers', action='append', required=True,
        help='Redis servers to report the results to'
    )

    parser.add_argument(
        '-g', dest='hwlb_group',
        help='HWLB Group to send results for',
    )

    parser.add_argument(
        '-p', dest='redis_password',
        help='Password for Redis server authentication'
    )

    return parser.parse_args()


def main():
    args = parse_args()

    with \
            open('/etc/iglb/lbpools.json', 'r') as lbpools_f, \
            open('/var/run/iglb/carp_state.json') as carps_states_f, \
            open('/var/run/iglb/lbpools_state.json') as lbpools_states_f \
            :
        lbpools = json.load(lbpools_f)
        carps_states = json.load(carps_states_f)
        lbpools_states = json.load(lbpools_states_f)

        results = compare_pools(
            lbpools, carps_states, lbpools_states, args.hwlb_group
        )

        error = False
        for server in args.redis_servers:
            try:
                send_to_redis(
                    server, args.redis_password,
                    results, args.hwlb_group
                )
                print(f'Results successfully sent to {server}')
            except redis.exceptions.ConnectionError as e:
                print(str(e))
                error = True

        if error:
            exit(1)


def compare_pools(
        lbpools, carps_states, lbpools_states, hwlb_group
):
    results = []

    for pool_k, pool_v in lbpools.items():
        if not pool_v['nodes']:
            results.append(get_object_output(pool_k, pool_v, hwlb_group))
            continue

        # Skip LB Pools for which this HWLB is not master carp
        first_lbnode = list(pool_v['nodes'].values())[0]
        if not (
                first_lbnode['route_network'] in carps_states
                and
                carps_states[first_lbnode['route_network']]['carp_master']
        ):
            print(
                f'Skipping LB Pool {pool_k} because carp is not master '
                f'on {pool_v["route_network"]}'
            )
            continue

        if pool_k in lbpools_states:
            pool_v['alive_nodes'] = lbpools_states[pool_k]['nodes_alive']
            pool_v['nodes_states'] = lbpools_states[pool_k]['nodes']
            in_testtool = True
        else:
            in_testtool = False

        results.append(
            get_object_output(pool_k, pool_v, hwlb_group, in_testtool)
        )

    return results


def send_to_redis(redis_server, redis_password, results, hwlb_group):
    r = redis.Redis(
        host=redis_server, port=6379,
        db=0, password=redis_password,
        socket_connect_timeout=5,
        socket_timeout=5,
    )

    for result in results:
        if hwlb_group:
            redis_key = (f'{result["hostname"]}_{result["service"]}'
                         f'_{hwlb_group}')
        else:
            redis_key = f'{result["hostname"]}_{result["service"]}'

        # ex is the TTL for the key in seconds
        # If the HWLB stops sending data, the entries in Redis will
        # expired after this amount of time. On monitoring side,
        # we raise flags if no data is found for a given LBPool.
        r.set(redis_key, json.dumps(result), ex=180)


def get_object_output(hostname, pool_data, hwlb_group, in_testtool=False):
    output = {
        'hostname': hostname,
        'service': 'lbpool_nodes',
        'hwlb_group': hwlb_group,
        'in_testtool': in_testtool,
        'nodes': pool_data.get('nodes_states', {}),
        'alive_nodes': pool_data.get('alive_nodes', 0),
        'min_nodes': pool_data.get('min_nodes', 0),
        'max_nodes': pool_data.get('max_nodes', 0),
        'health_checks': True if pool_data['health_checks'] else False
    }

    return output


if __name__ == "__main__":
    main()
