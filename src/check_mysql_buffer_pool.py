#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - MySQL InnoDB Buffer Pool Check

This script gets the configured innodb_buffer_pool_size at runtime and
compares this value with the data_size of the database.  It's also possible
to multiply the buffer_pool_size with a factor, to keep track on growing
databases, which are too big to fit into the available memory.
It raises a warning if the data_size of the database (this includes indexes)
is greater than the configured buffer_pool.
It raises a unknown if the connect/query could not be executed.

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
    parser.add_argument(
        '--buffer_pool_factor',
        default=1.0,
        type=float
    )

    return parser.parse_args()


def main():
    """The main program"""
    args = parse_args()

    try:
        buffer_pool_size, data_size = get_buffer_and_data_size(
            args.user, args.password, args.host, args.unix_socket)
    except DatabaseError as error:
        print('UNKNOWN: ' + str(error))
        exit(3)

    if (buffer_pool_size * args.buffer_pool_factor) < data_size:
        print('WARNING: buffer_pool_size ({}MB) < data_size ({}MB)'.format(
            buffer_pool_size, data_size))
        exit(1)

    print('OK: buffer_pool_size ({}MB) >= data_size ({}MB)'.format(
        buffer_pool_size, data_size))
    exit(0)


def get_buffer_and_data_size(user, password, host, unix_socket):
    """Get buffer_pool and data_size

    Get the configured buffer_pool and the data_size of the database at
    runtime.

    :param: :user: The username to connect to database

    :param: :password: The password to connect to database

    :param: :host: The hostname/hostaddress to connect

    :param: :unix_socket: Try unix_socket as auth_method to connect

    :return: int
    """

    buffer_pool_size = query_database(
        user,
        password,
        host,
        unix_socket,
        'SELECT (@@innodb_buffer_pool_size / POWER(1024,2))',
    )

    data_size = query_database(
        user,
        password,
        host,
        unix_socket,
        'SELECT FLOOR(SUM(DATA_LENGTH+INDEX_LENGTH)/POWER(1024,2)) '
        'FROM information_schema.TABLES WHERE ENGINE="InnoDB";'
    )

    return buffer_pool_size, data_size


def query_database(user, password, host, unix_socket, query):
    """Query database

    Query the regarding database to get the configured buffer_pool and
    data_size of the database.

    :param: :user: The username to connect to database

    :param: :password: The password to connect to database

    :param: :host: The hostname/hostaddress to connect

    :param: :unix_socket: Try unix_socket as auth_method to connect

    :return: int
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
    size = int([r[0] for r in res][0])

    cur.close()
    cnx.close()

    return size


if __name__ == '__main__':
    main()
