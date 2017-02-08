#!/usr/bin/env python

import imp
import subprocess
import re

# Nagios return codes
exit_ok      = 0
exit_warn    = 1
exit_crit    = 2
exit_unknown = 3

def pairwise(it):
    it = iter(it)
    while True:
        yield next(it), next(it)


def master_status():
    carp_settings = imp.load_source('carp_settings', '/etc/iglb/carp_settings.py')

    ret = False
    for ifname in carp_settings.ifaces.keys():
        # Read interface configuration:
        p = subprocess.Popen(['/sbin/ifconfig', ifname], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        ifconfig, err = p.communicate()
        
        for line in ifconfig.split("\n"):
            # Find carp lines, the look like this:
            #carp: MASTER vhid 133 advbase 1 advskew 50
            ifconfig_match = re.match(".*carp: ([A-Z]+) vhid ([0-9]+) advbase.*", line)
            if ifconfig_match:
                status = ifconfig_match.group(1)
                if status == 'MASTER':
                    ret = True
    return ret


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
                'nodes_alive': int(subret['nodes_alive']),
                'backup_pool': subret['backup_pool'],
            }
    return ret


def load_known_pools():
    poolnames = imp.load_source('poolnames', '/etc/iglb/poolnames.py')
    return poolnames.poolnames


def compare_pools(pools, testtool, send):
    output = ''
    if send:
        separator = "\27"
    else:
        separator = "\n"
    for pool_k, pool_v in pools.items():
        in_testtool = False
        if pool_k in testtool:
            num_nodes = testtool[pool_k]['nodes_alive']
            in_testtool = True

        if pool_v['has_healthchecks']:
            if in_testtool:
                if num_nodes == 0:
                    exit_code = exit_crit
                else:
                    exit_code = exit_ok
                output += "{}\t{}\t{}\t{} nodes alive{}".format(
                    pool_v['nagios_host'],
                    pool_v['nagios_service'],
                    exit_code,
                    num_nodes,
                    separator,
                    )
                separator
            else:
                output += "{}\t{}\t{}\tNot monitored by testtool{}".format(
                    pool_v['nagios_host'],
                    pool_v['nagios_service'],
                    exit_unknown,
                    separator
                    )
        else:
            optimal_nodes = pool_v.get('optimal_nodes')
            if optimal_nodes == 1:
                output += "{}\t{}\t{}\tHas no healthchecks and only 1 node{}".format(
                    pool_v['nagios_host'],
                    pool_v['nagios_service'],
                    exit_ok,
                    separator
                    )
            else:
                output += "{}\t{}\t{}\tHas no healthchecks but {} nodes{}".format(
                    pool_v['nagios_host'],
                    pool_v['nagios_service'],
                    exit_warn,
                    optimal_nodes,
                    separator
                    )
    if send:
        for monitor in ('af', 'aw'):
            nsca = subprocess.Popen(
                [
                    '/usr/local/sbin/send_nsca',
                    '-H',
                    '{}-monitor.ig.local.'.format(monitor),
                    '-c',
                    '/usr/local/etc/nagios/send_nsca.cfg',
                ],
                stdin = subprocess.PIPE,
            )
            nsca.communicate(output)
    else:
        print output


def main():
    if not master_status():
        return
    known_pools = load_known_pools()
    testtool_status = load_testtool_status()
    result = compare_pools(known_pools, testtool_status, True)


if __name__ == "__main__":
    main()
