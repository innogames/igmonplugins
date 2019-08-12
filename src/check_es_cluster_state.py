#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Check if an index exists with the
provided prefix

Copyright (c) 2019 InnoGames GmbH
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
from argparse import ArgumentParser, RawTextHelpFormatter
from elasticsearch import Elasticsearch

def parse_args():
    parser = ArgumentParser(
        description=(
            'This Nagios check investigates the cluster health.'
        ),
        formatter_class=RawTextHelpFormatter
    )

    parser.add_argument(
        'host', help='Elasticsearch host to run the query against'
    )

    return parser.parse_args()

def main():
    args = parse_args()
    es = Elasticsearch(args.host)
    health = es.cluster.health()
    if health['status'] == 'red':
        print('Cluster status is red')
        sys.exit(2)
    if health['status'] == 'yellow':
        print('Cluster status is yellow')
        sys.exit(1)
    print('Cluster status is green')

if __name__ == '__main__':
    main()
