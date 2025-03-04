#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - MySQL InnoDB Buffer Pool Check

This script monitors the usage of the InnoDB buffer pool by issuing a query that calculates
the percentage of the buffer pool currently utilized. It raises alerts based on defined thresholds.

The Warning threshold is set to 90% by default.

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

from argparse import ArgumentParser, Namespace
from contextlib import closing

from mysql.connector import (
    connect,
    DatabaseError,
)


def parse_args() -> Namespace:
    """Get argument parser"""

    parser = ArgumentParser()
    parser.add_argument('--user', default='root')
    parser.add_argument('--host', default='localhost')
    parser.add_argument('--password', default='')
    parser.add_argument('--threshold', type=float, default=90.0)
    parser.add_argument(
        '--unix-socket',
        default='/var/run/mysqld/mysqld.sock',
    )

    return parser.parse_args()


def main() -> None:
    """Main function"""
    args = parse_args()

    try:
        buffer_pool_usage = get_buffer_pool_usage(
            args.user, args.password, args.host, args.unix_socket)
    except DatabaseError as error:
        print('UNKNOWN: ' + str(error))
        exit(3)

    if buffer_pool_usage >= args.threshold:
        print(f'WARNING: Buffer Pool Usage is at {buffer_pool_usage}%')
        exit(1)

    print(f'OK: Buffer Pool Usage is at {buffer_pool_usage}%')
    exit(0)


def get_buffer_pool_usage(user: str, password: str, host: str, unix_socket: str) -> float:
    """Get buffer pool usage percentage

    Query the database to obtain the percentage of buffer pool used.

    :param: :user: The username to connect to database
    :param: :password: The password to connect to database
    :param: :host: The hostname/hostaddress to connect
    :param: :unix_socket: Try unix_socket as auth_method to connect

    :return: float
    """

    query = """
    SELECT
        ROUND((data.used * 100) / pool.total, 2) AS "Buffer Pool Usage (%)"
    FROM
        (SELECT
            VARIABLE_VALUE AS used
        FROM
            performance_schema.global_status
        WHERE
            VARIABLE_NAME = 'Innodb_buffer_pool_pages_data') AS data,
        (SELECT @@innodb_buffer_pool_size / @@innodb_page_size AS total) AS pool;
    """

    buffer_pool_usage = query_database(user, password, host, unix_socket, query)

    return float(buffer_pool_usage)


def query_database(user: str, password: str, host: str, unix_socket: str, query: str) -> float:
    """Query the database

    Query the specified database to obtain results from the query.

    :param user: The username to connect to the database
    :param password: The password to connect to the database
    :param host: The hostname/host address to connect
    :param unix_socket: Try unix_socket as auth_method to connect
    :param query: The SQL query to execute

    :return: The result as a float
    """

    conn_info = {
        'user': user,
        'password': password,
        'host': host,
        'unix_socket': unix_socket,
    }

    with closing(connect(**conn_info)) as cnx:
        with closing(cnx.cursor()) as cur:
            cur.execute(query)
            row = cur.fetchone()
            if row is None:
                raise ValueError("Query returned no results")


    return float(row[0])


if __name__ == '__main__':
    main()
