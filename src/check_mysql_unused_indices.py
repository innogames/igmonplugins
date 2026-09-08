#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - MySQL Unused Indices Check

This script reports the disk space wasted by secondary indices that have
never been used by a query.  It combines the usage counters from
performance_schema.table_io_waits_summary_by_index_usage with the index
sizes from mysql.innodb_index_stats.

The performance_schema usage counters are held in memory and reset on
every MySQL restart, so a freshly restarted server would otherwise be
reported as having only unused indices.  This check avoids that false
positive by reporting OK, without evaluating anything, until the server
has been up for at least --min-uptime-days.  Indices that are only used
by weekly or monthly jobs, and indices created after the last restart,
are reported until they have been queried once; raise --min-uptime-days
accordingly and treat a newly created index as expected noise.  Manually
truncating the performance_schema summary tables also resets the
counters without touching the uptime and invalidates the result until
the next restart.

Servers with read_only or super_read_only set are skipped by default,
because a replication applier never reads secondary indices, so every
index of a replica that serves no queries would look unused.  Pass
--check-read-only for replicas that do serve queries.

UNIQUE and FOREIGN KEY indices are never reported: InnoDB checks those
constraints internally without the handler calls performance_schema
counts, and they cannot be dropped without giving up the constraint.
FULLTEXT and SPATIAL indices are not evaluated as InnoDB keeps no size
statistics for them.  Indices of non-InnoDB tables and of tables with
STATS_PERSISTENT=0 have no size either and are only counted separately.
The sizes are refreshed by ANALYZE TABLE or the automatic statistics
recalculation only, so the reported figures are approximate.

Authentication: This script is designed to use MySQL socket authentication.
Required privileges for the monitoring user:
    CREATE USER 'nagios'@'localhost' IDENTIFIED WITH auth_socket;
    GRANT SELECT ON performance_schema.* TO 'nagios'@'localhost';
    GRANT SELECT ON mysql.innodb_index_stats TO 'nagios'@'localhost';

Copyright (c) 2026 InnoGames GmbH
"""
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the 'Software'), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED 'AS IS', WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

from argparse import ArgumentParser, ArgumentTypeError, RawTextHelpFormatter
from contextlib import closing
from sys import exit

from mysql.connector import Error as MySQLError, connect

IGNORED_SCHEMAS = ('mysql', 'information_schema', 'performance_schema', 'sys')


class ExitCodes:
    ok = 0
    warning = 1
    critical = 2
    unknown = 3


def non_negative_int(value):
    number = int(value)
    if number < 0:
        raise ArgumentTypeError('must be >= 0')
    return number


def parse_args():
    parser = ArgumentParser(
        formatter_class=RawTextHelpFormatter, description=__doc__
    )
    parser.add_argument(
        '--host',
        default='localhost',
        help='Target MySQL server (default: %(default)s)',
    )
    parser.add_argument(
        '--unix-socket',
        default='/var/run/mysqld/mysqld.sock',
        help='Target unix socket (default: %(default)s)',
    )
    parser.add_argument('--port', type=int, default=3306)
    parser.add_argument(
        '--user', help='MySQL user (uses socket authentication)'
    )
    parser.add_argument('--passwd', help='MySQL password')
    parser.add_argument(
        '--warning',
        type=float,
        default=5120.0,
        help=(
            'Warning threshold in MiB of wasted space '
            '(default: %(default)s)'
        ),
    )
    parser.add_argument(
        '--critical',
        type=float,
        default=20480.0,
        help=(
            'Critical threshold in MiB of wasted space '
            '(default: %(default)s)'
        ),
    )
    parser.add_argument(
        '--min-uptime-days',
        type=float,
        default=7.0,
        help=(
            'Report OK without checking anything if the server has been '
            'up for less than this many days (default: %(default)s)'
        ),
    )
    parser.add_argument(
        '--check-read-only',
        action='store_true',
        help=(
            'Also evaluate servers with read_only or super_read_only set; '
            'skipped by default because a replication applier never '
            'reads secondary indices'
        ),
    )
    parser.add_argument(
        '--ignore-schemas',
        nargs='*',
        default=[],
        help='Additional schemas to ignore, besides the MySQL system ones',
    )
    parser.add_argument(
        '--top',
        type=non_negative_int,
        default=5,
        help='Number of biggest unused indices to list (default: %(default)s)',
    )
    parser.add_argument(
        '--perfdata',
        action='store_true',
        help='Include performance data in output',
    )

    return parser.parse_args()


def get_connection_kwargs(args):
    connection_kwargs = {'connection_timeout': 10}
    if args.host == 'localhost':
        connection_kwargs['unix_socket'] = args.unix_socket
    else:
        connection_kwargs['host'] = args.host
        connection_kwargs['port'] = args.port
    if args.user:
        connection_kwargs['user'] = args.user
    if args.passwd:
        connection_kwargs['passwd'] = args.passwd
    return connection_kwargs


def get_uptime_days(cursor):
    # fetchall() even for one row: after fetchone() the C extension cursor
    # keeps the result open and the next execute() fails with "Unread result"
    cursor.execute("SHOW GLOBAL STATUS LIKE 'Uptime'")
    rows = cursor.fetchall()
    if not rows:
        raise Exception('Uptime status variable not found')
    return float(rows[0][1]) / 86400.0


def is_read_only(cursor):
    cursor.execute('SELECT @@global.read_only OR @@global.super_read_only')
    return bool(cursor.fetchall()[0][0])


def check_instrumentation(cursor):
    """Raise unless table I/O waits are actually being counted

    Rows in table_io_waits_summary_by_index_usage are created whenever
    a table is opened, even with the instrument disabled; they just
    never get incremented then.  With performance_schema=OFF both
    lookups return NULL and the expression is NULL as well.
    """
    cursor.execute(
        """
        SELECT
          (SELECT ENABLED FROM performance_schema.setup_instruments
            WHERE NAME = 'wait/io/table/sql/handler') = 'YES'
          AND
          (SELECT ENABLED FROM performance_schema.setup_consumers
            WHERE NAME = 'global_instrumentation') = 'YES'
        """
    )
    if cursor.fetchall()[0][0] != 1:
        raise Exception(
            'performance_schema table I/O instrumentation is disabled, '
            'index usage counters are not collected'
        )


def get_unused_indices(cursor, ignored_schemas):
    """Get (schema, table, index) tuples never used since server start"""
    placeholders = ', '.join(['%s'] * len(ignored_schemas))
    cursor.execute(
        f"""
        SELECT OBJECT_SCHEMA, OBJECT_NAME, INDEX_NAME
        FROM performance_schema.table_io_waits_summary_by_index_usage
        WHERE COUNT_STAR = 0
          AND INDEX_NAME IS NOT NULL
          AND INDEX_NAME != 'PRIMARY'
          AND OBJECT_SCHEMA NOT IN ({placeholders})
        """,
        ignored_schemas,
    )
    return set(cursor.fetchall())


def get_excluded_indices(cursor, ignored_schemas):
    """Get (schema, table, index) tuples that must not count as unused

    UNIQUE and FOREIGN KEY indices are checked by InnoDB internally
    without going through the handler, so performance_schema never
    counts them as used.  FULLTEXT and SPATIAL indices have no size in
    innodb_index_stats.  The FOREIGN KEY match is deliberately loose:
    every index whose column at position N is the FK column at position
    N is kept, which is a superset of the indices MySQL refuses to drop.
    """
    placeholders = ', '.join(['%s'] * len(ignored_schemas))
    cursor.execute(
        f"""
        SELECT TABLE_SCHEMA, TABLE_NAME, INDEX_NAME
        FROM information_schema.STATISTICS
        WHERE (NON_UNIQUE = 0 OR INDEX_TYPE IN ('FULLTEXT', 'SPATIAL'))
          AND TABLE_SCHEMA NOT IN ({placeholders})
        UNION
        SELECT s.TABLE_SCHEMA, s.TABLE_NAME, s.INDEX_NAME
        FROM information_schema.KEY_COLUMN_USAGE AS k
        JOIN information_schema.STATISTICS AS s
          ON s.TABLE_SCHEMA = k.TABLE_SCHEMA
         AND s.TABLE_NAME = k.TABLE_NAME
         AND s.COLUMN_NAME = k.COLUMN_NAME
         AND s.SEQ_IN_INDEX = k.ORDINAL_POSITION
        WHERE k.REFERENCED_TABLE_NAME IS NOT NULL
          AND k.TABLE_SCHEMA NOT IN ({placeholders})
        """,
        ignored_schemas * 2,
    )
    return set(cursor.fetchall())


def get_index_sizes(cursor, ignored_schemas):
    """Get index sizes in MiB keyed by (schema, table, index)

    innodb_index_stats has one row per partition with the partition
    encoded in the table name as "table#p#p0" (MySQL 8.0) or
    "table#P#p0" (5.7), while performance_schema reports the plain
    table name.  Strip the suffix and sum up the partitions.
    """
    placeholders = ', '.join(['%s'] * len(ignored_schemas))
    cursor.execute(
        f"""
        SELECT database_name, table_name, index_name,
               stat_value * @@innodb_page_size / 1024 / 1024 AS size_mb
        FROM mysql.innodb_index_stats
        WHERE stat_name = 'size'
          AND index_name != 'PRIMARY'
          AND database_name NOT IN ({placeholders})
        """,
        ignored_schemas,
    )
    sizes = {}
    for schema, table, index, size_mb in cursor.fetchall():
        table = table.split('#p#', 1)[0].split('#P#', 1)[0]
        key = (schema, table, index)
        sizes[key] = sizes.get(key, 0) + size_mb
    return sizes


def get_wasted_indices(cursor, ignored_schemas):
    """Get (schema, table, index, size_mb) rows, biggest wasters first

    Also return the number of unused indices without a known size.
    """
    unused = get_unused_indices(cursor, ignored_schemas)
    unused -= get_excluded_indices(cursor, ignored_schemas)
    sizes = get_index_sizes(cursor, ignored_schemas)
    if unused and not sizes:
        raise Exception(
            'mysql.innodb_index_stats is empty, '
            'is innodb_stats_persistent enabled?'
        )

    wasted = [key + (sizes[key],) for key in unused if key in sizes]
    wasted.sort(key=lambda row: row[3], reverse=True)
    return wasted, len(unused) - len(wasted)


def format_message(wasted, unsized, top):
    total_mb = sum(row[3] for row in wasted)
    message = f'{len(wasted)} unused indices wasting {total_mb:.1f}MiB'
    if unsized:
        message += f' (+{unsized} without size statistics)'

    top_indices = ', '.join(
        f'{schema}.{table}.{index} ({size_mb:.1f}MiB)'
        for schema, table, index, size_mb in wasted[:top]
    )
    if top_indices:
        message += ': ' + top_indices

    return total_mb, message


def main():
    args = parse_args()
    ignored_schemas = IGNORED_SCHEMAS + tuple(args.ignore_schemas)

    try:
        with closing(connect(**get_connection_kwargs(args))) as connection:
            with closing(connection.cursor()) as cursor:
                uptime_days = get_uptime_days(cursor)
                if uptime_days < args.min_uptime_days:
                    print(
                        f'OK - server up for only {uptime_days:.1f}d '
                        f'(< {args.min_uptime_days:.1f}d), usage counters '
                        f'not reliable yet'
                    )
                    exit(ExitCodes.ok)

                if not args.check_read_only and is_read_only(cursor):
                    print(
                        'OK - server is read_only, usage counters of a '
                        'replica are not representative'
                    )
                    exit(ExitCodes.ok)

                check_instrumentation(cursor)
                wasted, unsized = get_wasted_indices(cursor, ignored_schemas)
    except MySQLError as error:
        print(f'UNKNOWN - MySQL error: {error}')
        exit(ExitCodes.unknown)
    except Exception as error:
        print(f'UNKNOWN - {error}')
        exit(ExitCodes.unknown)

    total_mb, message = format_message(wasted, unsized, args.top)

    if args.perfdata:
        message += (
            f' | wasted_mib={total_mb:.2f};{args.warning};{args.critical} '
            f'unused_indices={len(wasted)}'
        )

    if total_mb >= args.critical:
        print('CRITICAL - ' + message)
        exit(ExitCodes.critical)
    if total_mb >= args.warning:
        print('WARNING - ' + message)
        exit(ExitCodes.warning)
    print('OK - ' + message)
    exit(ExitCodes.ok)


if __name__ == '__main__':
    main()
