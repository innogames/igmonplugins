#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Check if lifecycles are defined for
elasticsearch indices

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
            'This Nagios check investigates every index (except '
            'system indices) if an index lifecycle is attached. '
            'This lifecycle takes care of deleting the index after '
            'a specified amount of time.'
        ),
        formatter_class=RawTextHelpFormatter
    )

    parser.add_argument(
        'host', help='Elasticsearch host to run the query against'
    )

    return parser.parse_args()

def main():
    failed_indices = []
    args = parse_args()
    es = Elasticsearch(args.host)
    indices = es.indices.get_settings()
    for index in indices:
        # Except system indices
        if index.startswith('.'):
            continue
        try:
            indices[index]['settings']['index']['lifecycle']
        except KeyError:
            failed_indices.append(index)
    if failed_indices:
        print('No lifecycle policy found for {}'.format(failed_indices))
        sys.exit(1)
    print('Found a lifecycle policy for every index')

if __name__ == '__main__':
    main()
