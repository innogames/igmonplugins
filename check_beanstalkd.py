#!/usr/bin/env python
#
# Graphite Beanstalkd Service Data Collector
#
# Copyright (c) 2015, InnoGames GmbH
#

import sys
import socket

def main():
    """The main program
    """

    status, output = run_checks()

    print(status + ' ' + output)

    if status == 'OK':
        sys.exit(0)
    elif status == 'WARNING':
        sys.exit(1)
    elif status == 'CRITICAL':
        sys.exit(2)
    else:
        sys.exit(3)

checks = (
        #   Metric              Minimum     Minimum     Maximum     Maximum
        #   Name                Critical    Warning     Warning     Critical
        ('current-connections',    None,      None,        100,       10000),
        ('current-jobs-buried',    None,      None,          1,         100),
        ('current-jobs-delayed',   None,      None,         10,        1000),
        ('current-jobs-reserved',  None,      None,         10,         100),
        ('current-jobs-ready',     None,      None,     100000,     1000000),
        ('current-jobs-urgent',    None,      None,          1,          10),
        ('current-producers',      None,      None,         10,        1000),
        ('current-tubes',          None,      None,      10000,      100000),
        ('current-waiting',        None,         1,          8,        None),
        ('current-workers',           0,         3,         10,          20),
        ('job-timeouts',           None,      None,          1,        None),
    )

def run_checks():
    """The main part of the program

    Parse the stats from beanstalkd.  Run the checks, it they are available.
    """

    try:
        response = read_stats()
    except socket.error as error:
        return 'CRITICAL', 'Error connecting to beanstalkd: ' + str(error)

    lines = response.splitlines()[2:-1]
    if len(lines) <= 3:
        return 'CRITICAL', 'Couldn\'t get stats from beanstalkd: ' + lines[0]

    stats = {}
    for line in lines:
        if ': ' in line:
            key, value = line.split(': ')
            stats[key] = value
        else:
            return 'UNKNOWN', 'Error parsing stats: ' + line

    warnings = []
    criticals = []
    perfs = []
    for metric, min_crit, min_warn, max_warn, max_crit in checks:
        if metric in stats:
            value = int(stats[metric])

            perfs.append('{0}={1}'.format(metric, value))

            if min_crit is not None and value <= min_crit:
                criticals.append('{0} is {1} less than {2}'.format(
                        metric, value, min_crit,
                    ))
            elif max_crit is not None and value >= max_crit:
                criticals.append('{0} is {1} greater than {2}'.format(
                        metric, value, max_crit,
                    ))
            elif min_warn is not None and value <= min_warn:
                warnings.append('{0} is {1} less than {2}'.format(
                        metric, value, min_warn,
                    ))
            elif max_warn is not None and value >= max_warn:
                warnings.append('{0} is {1} greater than {2}'.format(
                        metric, value, max_warn,
                    ))
        else:
            return 'UNKNOWN', 'Metric {0} couldn\'t found.'.format(metric)

    if criticals:
        return 'CRITICAL', '; '.join(criticals + warnings) + '. | ' + ' '.join(perfs)

    if warnings:
        return 'WARNING', '; '.join(warnings) + '. | ' + ' '.join(perfs)

    return 'OK', 'Everything is okay. | ' + ' '.join(perfs)

def read_stats():
    """Read the stats from the local Beanstalkd service

    Beanstalkd implements Memcached like simple TCP plain text protocol.
    It is enough to send "stats" request to it to get the metrics.  It is
    capable of handling multiple requests with a single connection, so
    the connection will remain open after the response.  It also returns
    the length of the response for us to know how many bytes we need to
    read.  Thought, we won't bother with those details.  We don't need to
    reuse the connection.  We will fetch 4096 bytes which is more than
    enough for the stats.

    We want to make sure that the connection is closed in any case and
    the program wouldn't hang waiting for the server to respond.  We will use
    2 second timeout to achieve this.
    """

    conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        conn.settimeout(2)
        conn.connect(('localhost', 11300))
        conn.send('stats\r\n')
        return conn.recv(4096)
    finally:
        conn.close()

if __name__ == '__main__':
    main()
