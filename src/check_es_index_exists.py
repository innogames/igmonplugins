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
import io
from argparse import ArgumentParser, RawTextHelpFormatter
from elasticsearch import Elasticsearch

def parse_args():
    parser = ArgumentParser(
        description=(
            'This Nagios check accepts an index prefix and checks '
            'if a matching index exists. The parameter `blafasel` '
            'would match an index named `blafasel-2019.01.01`'
        ),
        formatter_class=RawTextHelpFormatter
    )

    parser.add_argument(
        '--eshost', dest='eshost', required=True,
        help='Elasticsearch host to run the query against'
    )
    parser.add_argument(
        '-i', '--index', dest='index', required=True,
        help='Index Prefix to check for'
    )

    return parser.parse_args()

def main():
    args = parse_args()
    es = Elasticsearch(args.eshost)
    # suppress print output from es function
    text_trap = io.StringIO()
    sys.stderr = text_trap
    if not es.indices.exists(args.index + '*', allow_no_indices=False):
        print('Index not found in cluster: {}'.format(args.index))
        sys.exit(1)
    print('Index {} found'.format(args.index))

if __name__ == '__main__':
    main()
