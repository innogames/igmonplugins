#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Redis Cluster Check

This script checks the status of redis cluster which consists of at least
6 instances (3 master + 3 slaves).

A warning state represents a degraded cluster if one of three nodes is down.
A critical state represents a broken cluster.

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

import subprocess

from argparse import ArgumentParser
from sys import exit


def main():
    """Main entrypoint for script"""

    args = get_parser().parse_args()

    master_addr, master_state, cluster_state_master, failed_master = (
        _get_cluster_status(rgs.master_port, args.password)
    )
    slave_addr, slave_state, cluster_state_slave, failed_slave = (
        _get_cluster_status(args.slave_port, args.password)
    )
    if master_state != 'unknown' and slave_state != 'unknown':
        failed_hosts = failed_master + failed_slave
        if cluster_state_master != 'ok' and cluster_state_slave != 'ok':
            print('CRITICAL - cluster is broken')
            code = 2
        elif failed_hosts:
            print('WARNING - cluster status is degraded')
            code = 1
            for host in failed_hosts:
                print('{} is in a failed state'.format(host))
        else:
            print('OK - cluster status is OK')
            print('{} - {}'.format(master_addr, master_state))
            print('{} - {}'.format(slave_addr, slave_state))
            code = 0
    else:
        print('UNKNOWN - cluster status is UNKNOWN')
        print(
            'master on port {0} - {1}'.format(
                args.master_port, cluster_state_master))
        print(
            'slave on port {0} - {1}'.format(
                args.slave_port, cluster_state_slave))
        code = 3

    exit(code)


def get_parser():
    """Get argument parser -> ArgumentParser

    We need ports and password to connect
    """

    parser = ArgumentParser()

    parser.add_argument(
        '--master-port',
        action='store',
        dest='master_port',
        type=int,
        default=7000,
        help='redis port of the master instance',
    )
    parser.add_argument(
        '--slave-port',
        action='store',
        dest='slave_port',
        type=int,
        default=7001,
        help='redis port of the slave instance',
    )
    parser.add_argument(
        '--password',
        action='store',
        dest='password',
        default='',
        help='redis password needed',
    )

    return parser


def _get_cluster_status(port, password):
    """Get the Cluster Information

    The status of the local instances will be checked
    """

    """The output from redis-cli cluser nodes has the following format:
    6 lines where each line is a space seperated list with the following data:
        <hex_string>                           (hash of the node)
        <ip>:7001@17001                        (ip:port@remote port)
        slave,fail                             (myself,)?(master|slave)(,fail)?
        <hex_string>                           (remote node hash)
        <number>                               (performance data)
        <number>                               (performance data)
        <number>                               (number of connected clients)
        connected                              (fixed string)

    The string ",fail" is optional. It will only exists on failed hosts
    """
    port_string = str(port)
    try:
        role = subprocess.check_output(
            'redis-cli -p {0} -a {1} cluster nodes'.format(
                port, password), shell=True).decode().split()
        # Find keyword myself in the output
        state_index = [i for i, s in enumerate(role) if 'myself' in s][0]
        # Remove "myself," from the string. It will be either master or slave
        role_state = role[state_index].replace('myself,', '')
        # Get ip:port information which is one to the left of mysql, string
        role_addr = role[state_index - 1]
        # Get ip:port of the node that uses the current port and
        # is in status "fail".
        failed_hosts = [role[i-1] for i, s in enumerate(role)
                        if 'fail' in s and port_string in role[i-1]]

        cluster_state = subprocess.check_output(
            'redis-cli -p {0} -a {1} cluster info'.format(
                port, password), shell=True).split()[0]
        cluster_state = cluster_state.decode().split(':')[1]
    except subprocess.CalledProcessError:
        role_addr = 'unknown'
        role_state = 'unknown'
        cluster_state = 'unknown'
        failed_hosts = 'unknown'

    return role_addr, role_state, cluster_state, failed_hosts


if __name__ == '__main__':
    main()
