#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - MySQL InnoDB Buffer Pool Check

This script monitors the usage of the InnoDB buffer pool by issuing a query that calculates
the percentage of the buffer pool currently utilized. It raises alerts based on defined thresholds.

Warning at 90% usage.

Copyright (c) 2020 InnoGames GmbH
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

from argparse import ArgumentParser
from mysql.connector import (
    connect,
    DatabaseError,
)


def parse_args():
    """Get argument parser -> ArgumentParser"""

    parser = ArgumentParser()
    parser.add_argument('--user', default='root')
    parser.add_argument('--host', default='localhost')
    parser.add_argument('--password', default='password')
    parser.add_argument(
        '--unix-socket',
        default='/var/run/mysqld/mysqld.sock',
    )

    return parser.parse_args()


def main():
    """The main program"""
    args = parse_args()

    try:
        buffer_pool_usage = get_buffer_pool_usage(
            args.user, args.password, args.host, args.unix_socket)
    except DatabaseError as error:
        print('UNKNOWN: ' + str(error))
        exit(3)

    if buffer_pool_usage >= 90:
        print('WARNING: Buffer Pool Usage is at {}%'.format(buffer_pool_usage))
        exit(1)

    print('OK: Buffer Pool Usage is at {}%'.format(buffer_pool_usage))
    exit(0)


def get_buffer_pool_usage(user, password, host, unix_socket):
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


def query_database(user, password, host, unix_socket, query):
    """Query database

    Query the specified database to obtain results from the query.

    :param: :user: The username to connect to database
    :param: :password: The password to connect to database
    :param: :host: The hostname/hostaddress to connect
    :param: :unix_socket: Try unix_socket as auth_method to connect

    :return: result
    """

    cnx = connect(
        user=user,
        password=password,
        host=host,
        unix_socket=unix_socket,
    )

    cur = cnx.cursor()

    cur.execute(query)

    res = cur.fetchall()
    result = res[0][0]  # Expecting a single result

    cur.close()
    cnx.close()

    return result


if __name__ == '__main__':
    main()
