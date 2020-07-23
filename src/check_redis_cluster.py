#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Redis Cluster Check

This script checks the status of redis cluster which consists of at least
6 instances (3 master + 3 slaves).  The status can be fully functional
but degraded.

=> administrative intervention required

It raises a warning state if the cluster is degraded but still working.
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

    master_addr, master_state, cluster_state_master = _get_cluster_status(
        args.master_port, args.password)
    slave_addr, slave_state, cluster_state_slave = _get_cluster_status(
        args.slave_port, args.password)

    if master_state != 'unknown' and slave_state != 'unknown':
        if cluster_state_master != 'ok' and cluster_state_slave != 'ok':
            print('CRITICAL - cluster is broken')
            code = 2
        elif master_state != 'master' or slave_state != 'slave':
            print('WARNING - cluster status is degraded')
            if master_state != 'master':
                print('{} got demoted to slave'.format(master_addr))
                code = 1
            if slave_state != 'slave':
                print('{} got promoted to master'.format(slave_addr))
                code = 1
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

    try:
        role = subprocess.check_output(
            'redis-cli -p {0} -a {1} cluster nodes'.format(
                port, password), shell=True).decode().split()
        state_index = [i for i, s in enumerate(role) if 'myself' in s][0]
        role_state = role[state_index].replace('myself,', '')
        role_addr = role[state_index - 1]

        cluster_state = subprocess.check_output(
            'redis-cli -p {0} -a {1} cluster info'.format(
                port, password), shell=True).split()[0]
        cluster_state = cluster_state.decode().split(':')[1]
    except subprocess.CalledProcessError:
        role_addr = 'unknown'
        role_state = 'unknown'
        cluster_state = 'unknown'

    return role_addr, role_state, cluster_state


if __name__ == '__main__':
    main()
