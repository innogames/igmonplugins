#!/usr/bin/env python
"""InnoGames Monitoring Plugins - MySQL Master Flapping

This script is used to check if both loadbalancers have the same opinion about
which of our MySQL servers should serve the traffic. It uses data provided by
the mysqllbcheck tool which sets read/write states.

Whenever mysqllbcheck receives a query from the loadbalancer and determines the
local host should be master, it writes a timestamp to a table. As both of the
loadbalancers might not have the same opinion, both servers could be set to
write. This we then can see in the timestamps and use that for the detection.

When two or more servers write a heartbeat within <flapping_time_limit> seconds
it is considered as flapping. Be aware that a failover will likely trigger a
warning, depending how often the check is run and when the failover occured.

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

from argparse import ArgumentParser
from mysql.connector import (
    connect,
    DatabaseError,
)

class TooFewTimestampsError(Exception):
   """Raised when there are too few timestamps to compare"""
   pass

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
    parser.add_argument('--database', default='mysqllbcheck')
    parser.add_argument('--table', default='heartbeat')
    parser.add_argument(
        '--flapping_time_limit',
        default=60,
        type=int
    )

    return parser.parse_args()


def main():
    """The main program"""
    args = parse_args()

    try:
        heartbeat_delta_min = get_heartbeat_delta_min(
            args.user, args.password, args.host, args.unix_socket,
            args.database, args.table)
    except DatabaseError as error:
        print('UNKNOWN: ' + str(error))
        exit(3)
    except TooFewTimestampsError:
        print('OK: No flapping detected')
        exit(0)

    if heartbeat_delta_min < args.flapping_time_limit:
        print('WARNING: Two hosts claim to be master within {} seconds.'.format(
            heartbeat_delta_min))
        exit(1)

    print('OK: No flapping detected')
    exit(0)


def get_heartbeat_delta_min(user, password, host, unix_socket, database, table):
    """Get the minimum time difference between two or more timestamps

    :param: :user: The username to connect to database

    :param: :password: The password to connect to database

    :param: :host: The hostname/hostaddress to connect

    :param: :unix_socket: Try unix_socket as auth_method to connect

    :param: :database: The database where heartbeats are stored

    :param: :table: The table where heartbeats are stored

    :return: int
    """

    timestamps = query_database(
        user,
        password,
        host,
        unix_socket,
        'SELECT heartbeat from {}.{} ORDER BY heartbeat DESC LIMIT 2'.format(
            database, table
        ),
    )

    # When we have less than 2 values, there is a maximum of one master,
    # therefore we return a number which is higher than any sane value for
    # flapping_time_limit
    if len(timestamps) < 2:
        raise TooFewTimestampsError

    # We got the 2 biggest timestamps from the query above
    heartbeat_delta_min = timestamps[1] - timestamps[0]

    return heartbeat_delta_min


def query_database(user, password, host, unix_socket, query):
    """Query database

    Query the regarding database to get the stored master timestamps

    :param: :user: The username to connect to database

    :param: :password: The password to connect to database

    :param: :host: The hostname/hostaddress to connect

    :param: :unix_socket: Try unix_socket as auth_method to connect

    :return: [ datetime.datetime ]
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

    timestamps = []
    for item in res:
        timestamps.append(int(item[0].timestamp()))

    cur.close()
    cnx.close()

    return timestamps


if __name__ == '__main__':
    main()
