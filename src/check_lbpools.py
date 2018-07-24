#!/usr/bin/env python
#
# InnoGames Monitoring Plugins - check_lbpools.py
#
# Copyright (c) 2017, InnoGames GmbH
#
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
#

import imp
import json
import subprocess
import re

# Nagios return codes
exit_ok = 0
exit_warn = 1
exit_crit = 2
exit_unknown = 3


def main():
    if not master_status():
        return
    known_pools = load_pools()
    testtool_status = load_testtool_status()
    compare_pools(known_pools, testtool_status, True)


def master_status():
    carp_settings = imp.load_source(
        'carp_settings',
        '/etc/iglb/carp_settings.py'
    )

    ret = False
    for ifname in carp_settings.ifaces_carp.keys():
        # Read interface configuration:
        p = subprocess.Popen(
            ['/sbin/ifconfig', ifname],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        ifconfig, err = p.communicate()

        for line in ifconfig.split("\n"):
            # Find carp lines, the look like this:
            # carp: MASTER vhid 133 advbase 1 advskew 50
            ifconfig_match = re.match(
                ".*carp: ([A-Z]+) vhid ([0-9]+) advbase.*",
                line
            )
            if ifconfig_match:
                status = ifconfig_match.group(1)
                if status == 'MASTER':
                    ret = True
    return ret


def load_pools():
    with open('/etc/iglb/iglb.json') as jsonfile:
        return json.load(jsonfile)['lbpools']


def pairwise(it):
    it = iter(it)
    while True:
        yield next(it), next(it)


def load_testtool_status():
    ret = {}
    with open('/var/log/testtool.status', 'r') as tsf:
        for line in iter(tsf.readline, ''):
            if 'lbpool:' not in line:
                continue
            line = iter(line.strip().split(' '))
            subret = {}
            for k, v in pairwise(line):
                k = k.split(':')[0]
                subret[k] = v
            ret[subret['lbpool']] = {
                'nodes_alive': int(subret.get('nodes_alive')),
                'backup_pool': subret['backup_pool'],
            }
    return ret


def compare_pools(pools, testtool, send):
    output = ''

    if send:
        separator = "\27"
    else:
        separator = "\n"

    for pool_k, pool_v in pools.items():
        # Skip NAT-only rules
        if not pool_v['protocol_port']:
            continue

        for proto in ['4', '6']:
            if not pool_v.get('ip' + proto):
                continue

            if proto == '6':
                nagios_service = 'check_lbpool_6'
            else:
                nagios_service = 'check_lbpool'

            in_testtool = False
            testtool_name = pool_v['pf_name'] + '_' + proto
            if testtool_name in testtool:
                num_nodes = testtool[testtool_name]['nodes_alive']
                in_testtool = True

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
                    output += (
                        '{}\t{}\t{}\t{} of '
                        '(min: {}, max: {}, all: {}) nodes alive{}'
                    ).format(
                        pool_k,
                        nagios_service,
                        exit_code,
                        num_nodes,
                        min_nodes,
                        max_nodes,
                        optimal_nodes,
                        separator,
                        )
                    separator
                else:
                    output += '{}\t{}\t{}\tNot monitored by testtool{}'.format(
                        pool_k,
                        nagios_service,
                        exit_unknown,
                        separator
                        )
            else:
                if optimal_nodes == 1:
                    output += (
                        '{}\t{}\t{}\t'
                        'Has no healthchecks and only 1 node{}'
                    ).format(
                        pool_k,
                        nagios_service,
                        exit_ok,
                        separator
                        )
                else:
                    output += (
                        '{}\t{}\t{}\t'
                        'Has no healthchecks but {} nodes{}'
                    ).format(
                        pool_k,
                        nagios_service,
                        exit_warn,
                        optimal_nodes,
                        separator
                        )
    if send:
        for monitor in ('af-monitor.admin', 'aw-monitor'):
            nsca = subprocess.Popen(
                [
                    '/usr/local/sbin/send_nsca',
                    '-H', '{}.ig.local.'.format(monitor),
                    '-to', '20',
                    '-c', '/usr/local/etc/nagios/send_nsca.cfg',
                ],
                stdin=subprocess.PIPE,
            )
            nsca.communicate(output)
    else:
        print(output)


if __name__ == "__main__":
    main()
