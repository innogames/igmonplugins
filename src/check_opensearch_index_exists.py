#!/usr/bin/env python3


"""InnoGames Monitoring Plugins - Check if an index exists with the
provided prefix

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
from datetime import datetime
from ssl import create_default_context

from opensearchpy import OpenSearch


def parse_args() -> Namespace:
    """Parse command line arguments for the monitoring script."""
    parser = ArgumentParser(
        description=(
            "This Nagios check accepts an index prefix and checks "
            "if a matching index exists. The parameter `blafasel` "
            "would match an index named `blafasel-2019.01.01`"
        ),
        formatter_class=RawTextHelpFormatter,
    )

    parser.add_argument("host", help="Opensearch host to run the query against")
    parser.add_argument("index", help="Index Prefix to check for")
    parser.add_argument("-u", "--user", help="Monitoring user")
    parser.add_argument("-p", "--password", help="Password for monitoring user")
    parser.add_argument("--root_ca", help="CA file matching the server's certificate")
    parser.add_argument(
        "--daily",
        action="store_true",
        help="Check if an index exists for datetime.now()",
    )

    parser.add_argument(
        "--date-format", default="%Y.%m.%d", help="Time format to use for --daily"
    )

    return parser.parse_args()


def main():
    """Main function to check for the existence of an index with a given prefix."""
    args = parse_args()

    connect_params = {}
    if args.root_ca:
        connect_params["scheme"] = "https"
        connect_params["ssl_context"] = create_default_context(cafile=args.root_ca)

    if args.user and args.password:
        connect_params["http_auth"] = (args.user, args.password)

    index_name = args.index
    if args.daily:
        index_name = index_name + "-" + datetime.now().strftime(args.date_format)

    opensearch = OpenSearch([args.host], **connect_params)

    # Suppress print output from OpenSearch function
    sys.stderr = None
    if not opensearch.indices.exists(index=index_name, allow_no_indices=False):
        print(f'Index not found in cluster: {format(index_name)}.')
        sys.exit(1)

    print(f'Index {format(index_name)} found')


if __name__ == "__main__":
    main()
