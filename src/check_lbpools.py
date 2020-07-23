#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Load Balancing Pools Check

Copyright (c) 2020 InnoGames GmbH
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
import subprocess

from argparse import ArgumentParser

# Nagios return codes
exit_ok = 0
exit_warn = 1
exit_crit = 2
exit_unknown = 3


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
        compare_pools(lbpools, carps_states, lbpools_states, args.nsca_servers)


def pairwise(it):
    it = iter(it)
    while True:
        yield next(it), next(it)


def parse_args():
    parser = ArgumentParser()

    parser.add_argument(
        '-H', dest='nsca_servers', action='append',
        help='Nagios servers to report the results to'
    )

    return parser.parse_args()


def compare_pools(lbpools, carps_states, lbpools_states, nsca_servers):
    output = ''

    if nsca_servers:
        separator = "\27"
        print('Sending to NSCA')
    else:
        separator = "\n"
        print('Sending to stdout')

    for pool_k, pool_v in lbpools.items():
        # Skip NAT-only rules
        if not pool_v.get('protocol_port'):
            print(
                'Skipping LB Pool {} because it has no protocol_ports'.format(
                    pool_k
            ))
            continue

        if not pool_v['nodes']:
            output += nagios_output(
                pool_k, exit_crit, separator, 'has no LB nodes',
            )
            continue

        # Skip LB Pools for which this HWLB is not master carp
        first_lbnode = list(pool_v['nodes'].values())[0]
        if not (
            first_lbnode['route_network'] in carps_states
            and
            carps_states[first_lbnode['route_network']]['carp_master']
        ):
            print(
                'Skipping LB Pool {} because carp is not master {}'.format(
                    pool_k, pool_v['route_network']
                )
            )
            continue

        if pool_k in lbpools_states:
            num_nodes = lbpools_states[pool_k]['nodes_alive']
            in_testtool = True
        else:
            in_testtool = False

        optimal_nodes = len(pool_v['nodes'])

        # We want to keep "None" text as it is nicer
        # than 0 for human perception.
        min_nodes = pool_v.get('min_nodes', None)
        if min_nodes == 0:
            min_nodes = None
        max_nodes = pool_v.get('max_nodes', None)
        if max_nodes == 0:
            max_nodes = None

        if pool_v['health_checks']:
            if in_testtool:
                if num_nodes == 0:
                    exit_code = exit_crit
                elif max_nodes is not None and (num_nodes > max_nodes):
                    exit_code = exit_warn
                elif num_nodes == optimal_nodes:
                    exit_code = exit_ok
                elif min_nodes is not None and (num_nodes >= min_nodes):
                    exit_code = exit_ok
                else:
                    exit_code = exit_warn

                output += nagios_output(
                    pool_k, exit_code, separator,
                    '{} of (min: {}, max: {}, all: {}) nodes alive'.format(
                        num_nodes,
                        min_nodes,
                        max_nodes,
                        optimal_nodes,
                    )
                )
            else:
                output += nagios_output(
                    pool_k, exit_unknown, separator,
                    'Not monitored by testtool'
                )
        else:
            if optimal_nodes == 1:
                output += nagios_output(
                    pool_k, exit_ok, separator,
                    'Has no healthchecks and only 1 node'
                )
            else:
                output += nagios_output(
                    pool_k, exit_ok, separator,
                    'Has no healthchecks but {} nodes'.format(optimal_nodes)
                )
    if nsca_servers:
        for nsca_server in nsca_servers:
            nsca = subprocess.Popen(
                [
                    '/usr/local/sbin/send_nsca',
                    '-H', nsca_server,
                    '-c', '/usr/local/etc/nagios/send_nsca.cfg',
                ],
                stdin=subprocess.PIPE,
            )
            nsca.communicate(output.encode())
    else:
        print(output)


def nagios_output(pool, exit_code, separator, message):
    output = ''
    for nagios_service in ['check_lbpool', ]:
        output += (
            '{}\t{}\t{}\t{}{}'
        ).format(
            pool,
            nagios_service,
            exit_code,
            message,
            separator,
        )
    return output

if __name__ == "__main__":
    main()
