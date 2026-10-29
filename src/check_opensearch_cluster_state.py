#!/usr/bin/env python3


"""InnoGames Monitoring Plugins - Check Opensearch cluster health and
report shards which are not in a healthy state

Copyright (c) 2025 InnoGames GmbH
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

import sys
from argparse import ArgumentParser, Namespace, RawTextHelpFormatter
from typing import List

import requests

# Shards in these states are either serving requests or on their way to do
# so.  Everything else, UNASSIGNED above all, is counted as failed.
HEALTHY_SHARD_STATES = ('STARTED', 'RELOCATING', 'INITIALIZING')

# Listing every broken shard would blow up the Nagios output of a cluster
# which lost a whole node.
SHARDS_IN_OUTPUT = 5

# Counters of the cluster health worth graphing
PERFDATA_KEYS = (
    'number_of_nodes',
    'number_of_data_nodes',
    'active_primary_shards',
    'active_shards',
    'relocating_shards',
    'initializing_shards',
    'unassigned_shards',
    'delayed_unassigned_shards',
    'number_of_pending_tasks',
    'active_shards_percent_as_number',
)


def parse_args() -> Namespace:
    """Parse command line arguments for the monitoring script."""
    parser = ArgumentParser(
        description=('This Nagios check investigates the cluster health.'),
        formatter_class=RawTextHelpFormatter,
    )

    parser.add_argument(
        'host', help='Opensearch host to run the query against'
    )
    parser.add_argument('-u', '--user', help='Monitoring user')
    parser.add_argument(
        '-p', '--password', help='Password for monitoring user'
    )
    parser.add_argument(
        '--root_ca', help="CA file matching the server's certificate"
    )
    parser.add_argument(
        '--max_failed_shards',
        type=int,
        default=0,
        help='Number of failed shards tolerated before warning',
    )
    parser.add_argument(
        '--timeout',
        type=float,
        default=10,
        help='Timeout of a single API request in seconds',
    )

    return parser.parse_args()


def query(args: Namespace, path: str, **params) -> object:
    """Query one of the Opensearch API endpoints and return its JSON."""
    # The clusters speak TLS, but the port alone is a valid host argument
    base_url = args.host if '://' in args.host else f'https://{args.host}'

    response = requests.get(
        base_url.rstrip('/') + path,
        auth=(args.user, args.password)
        if args.user and args.password
        else None,
        verify=args.root_ca if args.root_ca else True,
        timeout=args.timeout,
        params=params,
    )
    response.raise_for_status()

    return response.json()


def get_failed_shards(args: Namespace) -> List[dict]:
    """Return the shards which are in none of the healthy states."""
    shards = query(
        args, '/_cat/shards', format='json', h='index,shard,prirep,state,node'
    )

    return [s for s in shards if s['state'] not in HEALTHY_SHARD_STATES]


def format_failed_shards(failed_shards: List[dict]) -> str:
    """Summarise the failed shards for the Nagios output."""
    if not failed_shards:
        # The shards got allocated between the two queries
        return 'already recovered'

    listed = ', '.join(
        '{index}[{shard}]{prirep} {state}'.format(**shard)
        for shard in failed_shards[:SHARDS_IN_OUTPUT]
    )
    if len(failed_shards) > SHARDS_IN_OUTPUT:
        listed += ', ...'

    return listed


def format_perfdata(health: dict) -> str:
    """Format the cluster health counters as Nagios performance data."""
    return ' '.join(
        f'{key}={health[key]}' for key in PERFDATA_KEYS if key in health
    )


def main():
    """Main function to check Opensearch cluster health."""
    args = parse_args()

    try:
        health = query(args, '/_cluster/health')
    except requests.RequestException as error:
        print(f'Cluster health is unavailable: {error}')
        sys.exit(3)

    messages = [f'Cluster status is {health["status"]}']
    exit_code = {'green': 0, 'yellow': 1, 'red': 2}.get(health['status'], 3)

    # The health already counts the shards nobody could allocate, so the
    # shard list is only fetched to name the indices behind the number.
    if health['unassigned_shards'] > args.max_failed_shards:
        try:
            details = format_failed_shards(get_failed_shards(args))
        except requests.RequestException as error:
            details = f'shard list unavailable: {error}'

        messages.append(
            f'{health["unassigned_shards"]} shards unassigned: {details}'
        )
        # Broken shards on their own never escalate above warning, a cluster
        # losing data reports it via the status above anyway.
        exit_code = max(exit_code, 1)

    print('{} | {}'.format('; '.join(messages), format_perfdata(health)))
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
