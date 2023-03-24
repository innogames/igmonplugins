#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Elasticsearch Shard Checker

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
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OFi MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import sys
from argparse import ArgumentParser

from elasticsearch import Elasticsearch


def main():
    parser = ArgumentParser(description='Check Elasticsearch cluster shard count.')
    group = parser.add_mutually_exclusive_group(required=True)
    parser.add_argument('--url',
                        help='Elasticsearch URL (including port)', required=True)
    parser.add_argument('--username',
                        help='Elasticsearch username')
    parser.add_argument('--password',
                        help='Elasticsearch password')
    parser.add_argument('--warning',
                        help='Warning threshold in percent',
                        default=10, type=int)
    parser.add_argument('--critical',
                        help='Critical threshold in percent',
                        default=5, type=int)
    group.add_argument('--no-verify-cert',
                        help='Disable certificate validation',
                        action='store_true')
    group.add_argument('--use-certifi',
                        help='Use certifi trust store', action='store_true')
    group.add_argument("--ca-path", type=str,
                       help='Path of the CA cert')
    args = parser.parse_args()

    if args.ca_path:
        ca_certs = args.ca_path
    elif args.use_certifi:
        import certifi
        ca_certs = certifi.where()
    elif args.no_verify_cert:
        ca_certs = None


    es = Elasticsearch(args.url, http_auth=(args.username, args.password),
                       ca_certs=ca_certs,
                       verify_certs=False if args.no_verify_cert else True)

    cluster_health = es.cluster.health()

    try:
        shard_capacity_per_node = es.cluster.get_settings()[
            'cluster']['max_shards_per_node']

    # If the setting is not set explicitly
    # it needs to be fetched from defaults.
    except KeyError:
        shard_capacity_per_node = es.cluster.get_settings(
            include_defaults=True)['defaults']['cluster']['max_shards_per_node']

    node_count = len(es.nodes.info()['nodes'])
    used_shards = cluster_health['active_shards']
    available_shards = int(shard_capacity_per_node) * int(node_count)
    percentage_available = 100-(100 * int(used_shards) / int(available_shards))

    # Exit with appropriate code and message
    if percentage_available < args.critical:
        print(
            f"CRITICAL: Percentage of possible new shards is below "
            f"{args.critical}% ({used_shards}/{available_shards})")
        sys.exit(2)
    elif percentage_available < args.warning:
        print(
            f"WARNING: Percentage of possible new shards is below"
            f" {args.warning}% ({used_shards}/{available_shards})")
        sys.exit(1)
    else:
        print(f"OK: Shards are healthy ({used_shards}/{available_shards})")
        sys.exit(0)


if __name__ == '__main__':
    main()
