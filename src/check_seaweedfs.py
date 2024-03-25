#!/usr/bin/env python3
#
# InnoGames Monitoring Plugins - SeaweedFS Check
#
# Copyright © 2024 InnoGames GmbH
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

import argparse
import sys
from typing import Any

import requests


def get_args() -> argparse.Namespace:
    """
    Get the command line arguments

    :return: argparse.Namespace
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--port',
        type=int,
        default=9333,
        help='Port of the SeaweedFS master server to query',
    )
    parser.add_argument(
        '--readonly-ok',
        action='store_true',
        help='Do not consider readonly volumes as an error',
    )
    parser.add_argument(
        '--min-free-volumes',
        type=int,
        help='Minimum number of free volumes to consider as a problem',
        required=True,
    )
    parser.add_argument(
        '--min-free-percent',
        type=int,
        help='Minimum number of percentage each volume should have free',
        default=10,
    )
    return parser.parse_args()


def get_status(host: str, port: int, path: str = '') -> dict[str, Any]:
    """
    Get the status of the SeaweedFS from master server

    :param host: Host of the SeaweedFS server to query
    :param port: Port of the SeaweedFS server to query
    :param path: Path to query (e.g. /dir, /vol, etc.)

    :return: Whole dictionary of the status of the SeaweedFS
    """
    url = f'http://{host}:{port}{path}/status'
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        print(f'UNKNOWN: Unexpected response from SeaweedFS {path}/status')
        sys.exit(3)
    except requests.exceptions.Timeout:
        print(f'UNKNOWN: Timeout when querying SeaweedFS {path}/status')
        sys.exit(3)


def get_cluster_state(host: str, port: int) -> int:
    """
    Get the cluster state of the SeaweedFS from master server

    :param host: Host of the SeaweedFS server to query
    :param port: Port of the SeaweedFS server to query

    :return: max_severity (int)
    """
    url = f'http://{host}:{port}/cluster/healthz'
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return 0
        print('CRITICAL: SeaweedFS cluster reporting unhealthy (non-200 response)')
        return 2
    except requests.exceptions.Timeout:
        print('UNKNOWN: Timeout when querying SeaweedFS healthz endpoint')
        return 3


def _check_readonly_volumes(data: dict[str, Any]) -> int:
    """
    Check if there are any readonly volumes

    :param volumes: Dictionary of the volumes

    :return: max_severity (int)
    """
    readonly_volumes = []
    for datacenter in data['Volumes']['DataCenters'].values():
        for server in datacenter.values():
            for endpoint in server.values():
                for volume in endpoint:
                    if volume['ReadOnly']:
                        readonly_volumes.append(str(volume['Id']))

    if readonly_volumes:
        volumes_str = ', '.join(readonly_volumes)
        print(f'CRITICAL: Readonly volumes detected: {volumes_str}')
        return 2

    return 0


def _check_volume_host_statuses(
    data: dict[str, Any], min_free_percent: int
) -> int:
    """
    Check if there are any volumes with low free space

    :param data: Dictionary of the volumes
    :param min_free_percent: Minimum free percent to consider as a problem

    :return: max_severity (int)
    """

    disk_needed_volumes = []
    endpoints = set()
    for datacenter in data['Volumes']['DataCenters'].values():
        for server in datacenter.values():
            for endpoint in server:
                endpoints.add(endpoint)

    for endpoint in endpoints:
        host, port = endpoint.split(':')
        result = get_status(
            host=host,
            port=port,
        )
        if int(result['DiskStatuses'][0]['percent_free']) < min_free_percent:
            disk_needed_volumes.append(endpoint)

    if disk_needed_volumes:
        if len(disk_needed_volumes) == 1:
            warn_str = 'Following volume has'
        else:
            warn_str = 'Following volumes have'

        disk_needed_str = ', '.join(disk_needed_volumes)
        print(
            f'WARNING: {warn_str} less than {min_free_percent}% free: '
            f'{disk_needed_str}'
        )
        return 1

    return 0


def main() -> None:
    """
    Main function
    """
    args = get_args()

    max_severity = get_cluster_state(host='localhost', port=args.port)

    vol_status = get_status(host='localhost', path='/vol', port=args.port)
    if not args.readonly_ok:
        readonly_state = _check_readonly_volumes(vol_status)
        max_severity = max(max_severity, readonly_state)

    if vol_status['Volumes']['Free'] < args.min_free_volumes:
        print(
            f'WARNING: Free volume count: {vol_status["Volumes"]["Free"]} '
            f'(needed {args.min_free_volumes})'
        )
        max_severity = max(1, max_severity)

    volume_state = _check_volume_host_statuses(
        data=vol_status,
        min_free_percent=args.min_free_percent,
    )
    max_severity = max(max_severity, volume_state)

    if max_severity == 0:
        print('OK: All looks healthy')

    sys.exit(max_severity)


if __name__ == '__main__':
    main()
