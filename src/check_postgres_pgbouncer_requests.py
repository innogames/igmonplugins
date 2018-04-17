#!/usr/bin/env python
#
# InnoGames Monitoring Plugins - check_postgres_pgbouncer_requests.py
#
# This script checks the requests per second on the connection pooler of
# postgresql called pgbouncer. It raises a warning state if
# a reasonable threshold is reached.
# Values for the database to be monitored, the used port of pgbouncer and
# the warning and critical thresholds can be specified using parameters.
#
# Copyright (c) 2018, InnoGames GmbH
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
#

import subprocess

from sys import exit
from argparse import ArgumentParser


def main():
    """Main entrypoint for script"""

    args = get_parser().parse_args()

    requests = int(get_pgbouncer_requests(args.port, args.dbname))

    code = 0

    if requests > args.warning:
        status = 'WARNING'
        code = 1
    else:
        status = 'OK'

    print('{} - pgbouncer requests per second: {}'.format(status, requests))

    exit(code)


def get_parser():
    """Get parser

    Get the argument parser to adjust arguments

    :return: ArgumentParser object
    """

    parser = ArgumentParser()

    parser.add_argument(
        '--dbname', '-d', help='database name to monitor',
        type=str,
    )
    parser.add_argument(
        '--port', '-p', help='the port pgbouncer is listening',
        default=6432,
        type=int,
    )
    parser.add_argument(
        '--warning', '-w', help='warning threshold for req/s',
        default=10000,
        type=int,

    )

    return parser


def get_pgbouncer_requests(port, dbname):
    """Get pgbouncer requests

    Get the actual pgbouncer requests per second on the regarding database

    :return: int
    """

    output = subprocess.check_output(
            'psql -p {} pgbouncer -Ac "show stats;"'.format(port), shell=True)

    rows = output.split('\n')
    header = rows.pop(0).split('|')

    # Fields changed across version 1.7.x to > 1.8.x so lets use header column
    # to be future safe or fail with proper error.
    if 'avg_req' in header:
        index = header.index('avg_req')
    elif 'avg_query_count' in header:
        index = header.index('avg_query_count')
    else:
        print('No column avg_req or avg_query_count found - check version!')
        exit(1)

    for db_columns in rows:
        columns = db_columns.split('|')
        if columns[0] == dbname:
            return columns[index]

    print('No database {} found'.format(dbname))
    exit(1)


if __name__ == '__main__':
    main()
