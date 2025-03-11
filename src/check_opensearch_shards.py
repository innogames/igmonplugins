#!/usr/bin/env python3

"""InnoGames Monitoring Plugins - Opensearch Shard Checker

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
from argparse import ArgumentParser, Namespace
from typing import Tuple

from opensearchpy import OpenSearch


def parse_args() -> Namespace:
    """Parse command line arguments for the monitoring script."""
    parser = ArgumentParser(description="Check Opensearch cluster shard count.")
    group = parser.add_mutually_exclusive_group(required=True)
    parser.add_argument("--url", help="Opensearch URL (including port)", required=True)
    parser.add_argument("-u", "--user", help="Monitoring user")
    parser.add_argument("-p", "--password", help="Password for monitoring user")
    parser.add_argument(
        "--warning", help="Warning threshold in percent", default=10, type=int
    )
    parser.add_argument(
        "--critical", help="Critical threshold in percent", default=5, type=int
    )
    group.add_argument(
        "--no-verify-cert", help="Disable certificate validation", action="store_true"
    )
    group.add_argument(
        "--use-certifi", help="Use certifi trust store", action="store_true"
    )
    group.add_argument("--root_ca", help="CA file matching the server's certificate")
    return parser.parse_args()


def get_shards_capacity(opensearch: OpenSearch) -> int:
    """Retrieve the shard capacity per node from the Opensearch cluster settings."""
    try:
        shard_capacity_per_node = opensearch.cluster.get_settings()["cluster"][
            "max_shards_per_node"
        ]
    except KeyError:  # If the setting is not set explicitly, fetch from defaults.
        shard_capacity_per_node = opensearch.cluster.get_settings(
            include_defaults=True
        )["defaults"]["cluster"]["max_shards_per_node"]
    return shard_capacity_per_node


def calculate_available(
    opensearch: OpenSearch, cluster_health: dict, shard_capacity_per_node: int
) -> Tuple[int, int, float]:
    """Calculate the available shard capacity as a percentage."""
    node_count = len(opensearch.nodes.info()["nodes"])
    used_shards = cluster_health["active_shards"]
    available_shards = int(shard_capacity_per_node) * int(node_count)
    percentage_available = 100 - (100 * int(used_shards) / int(available_shards))
    return used_shards, available_shards, percentage_available


def main():
    """Main function to evaluate shard capacity and report status."""
    args = parse_args()

    if args.root_ca:
        ca_certs = args.root_ca
    elif args.use_certifi:
        import certifi
        ca_certs = certifi.where()
    elif args.no_verify_cert:
        ca_certs = None

    opensearch = OpenSearch(
        args.url,
        http_auth=(args.user, args.password),
        ca_certs=ca_certs,
        verify_certs=False if args.no_verify_cert else True,
    )

    cluster_health = opensearch.cluster.health()
    shard_capacity_per_node = get_shards_capacity(opensearch)
    used_shards, available_shards, percentage_available = calculate_available(
        opensearch, cluster_health, shard_capacity_per_node
    )

    if percentage_available < args.critical:
        print(
            f"CRITICAL: Percentage of possible new shards is below "
            f"{args.critical}% ({used_shards}/{available_shards})"
        )
        sys.exit(2)
    elif percentage_available < args.warning:
        print(
            f"WARNING: Percentage of possible new shards is below"
            f" {args.warning}% ({used_shards}/{available_shards})"
        )
        sys.exit(1)
    else:
        print(f"OK: Shards are healthy ({used_shards}/{available_shards})")
        sys.exit(0)


if __name__ == "__main__":
    main()
