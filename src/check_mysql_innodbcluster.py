#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - MySQL InnoDB Cluster Check

This script checks the health of a MySQL InnoDB Cluster by examining
member states, quorum, and replication status with role-aware lag detection.

Copyright (c) 2025 InnoGames GmbH
"""

from argparse import ArgumentParser, ArgumentTypeError, RawTextHelpFormatter
from sys import exit
from mysql.connector import connect
import re


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
    parser.add_argument(
        '--user',
        help='MySQL user',
    )
    parser.add_argument(
        '--passwd',
        help='MySQL password',
    )
    parser.add_argument(
        '--warning',
        nargs='*',
        type=ClusterFilter,
        default=[ClusterFilter('1 offline'), ClusterFilter('lag 60s'), ClusterFilter('transaction_queue 5000')],
        help='Warning threshold (default: %(default)s)',
    )
    parser.add_argument(
        '--critical',
        nargs='*',
        type=ClusterFilter,
        default=[ClusterFilter('no primary'), ClusterFilter('lag 120s'), ClusterFilter('transaction_queue 10000')],
        help='Critical threshold (default: %(default)s)',
    )
    parser.add_argument(
        '--perfdata',
        action='store_true',
        help='Include performance data in output',
    )

    return parser.parse_args()


def main():
    args = parse_args()

    # Build connection kwargs
    connection_kwargs = {}
    if args.host == 'localhost':
        connection_kwargs['unix_socket'] = args.unix_socket
    else:
        connection_kwargs['host'] = args.host
    if args.user:
        connection_kwargs['user'] = args.user
        if args.passwd:
            connection_kwargs['passwd'] = args.passwd

    try:
        db = ClusterDatabase(connect(**connection_kwargs))
    except Exception as e:
        print(f'UNKNOWN - Cannot connect to MySQL: {e}')
        exit(ExitCodes.unknown)

    check = ClusterCheck(db)

    # Check critical conditions first
    critical_problems = check.get_problems(args.critical)
    if critical_problems:
        output = 'CRITICAL - ' + ', '.join(critical_problems)
        if args.perfdata:
            output += ' | ' + check.get_perfdata()
        print(output)
        exit(ExitCodes.critical)

    # Check warning conditions
    warning_problems = check.get_problems(args.warning)
    if warning_problems:
        output = 'WARNING - ' + ', '.join(warning_problems)
        if args.perfdata:
            output += ' | ' + check.get_perfdata()
        print(output)
        exit(ExitCodes.warning)

    # All good
    status_info = check.get_status_summary()
    output = f'OK - Cluster healthy: {db.get_cluster_name()} - {status_info}'
    if args.perfdata:
        output += ' | ' + check.get_perfdata()
    print(output)
    exit(ExitCodes.ok)


class ExitCodes:
    ok = 0
    warning = 1
    critical = 2
    unknown = 3


class ClusterFilter:
    pattern = re.compile(r'''
        \A
        (?:
            (?P<no>no)\s+(?P<no_what>primary|quorum|writer)
            |
            (?P<lag>lag)\s+(?P<lag_duration>\d+)(?P<lag_unit>s|min|h)
            |
            (?P<transaction_queue>transaction_queue)\s+(?P<queue_size>\d+)
            |
            (?P<queue>queue)\s+(?P<queue_size_alt>\d+)
            |
            (?P<errors>errors)
            |
            (?P<count>\d+)(?P<percent>%?)
            \s+
            (?P<state>offline|recovering|error|unreachable)
            (?:\s+for\s+(?P<duration>\d+)(?P<unit>s|min|h))?
        )
        \Z
    ''', re.VERBOSE)

    def __init__(self, arg):
        matches = self.pattern.match(arg.lower())
        if not matches:
            raise ArgumentTypeError(f'"{arg}" cannot be parsed')

        self.no = matches.group('no')
        self.no_what = matches.group('no_what')
        self.lag = matches.group('lag')
        self.lag_duration = int(matches.group('lag_duration') or 0)
        self.lag_unit = matches.group('lag_unit')
        self.transaction_queue = matches.group('transaction_queue')
        self.queue = matches.group('queue')
        # Support both 'queue X' and 'transaction_queue X' syntax
        self.queue_size = int(matches.group('queue_size') or matches.group('queue_size_alt') or 0)
        self.errors = matches.group('errors')
        self.count = int(matches.group('count') or 0)
        self.percent = bool(matches.group('percent'))
        self.state = matches.group('state')
        self.duration = int(matches.group('duration') or 0)
        self.unit = matches.group('unit')

        # Convert durations to seconds
        multipliers = {'s': 1, 'min': 60, 'h': 3600}

        if self.lag_duration and self.lag_unit:
            self.lag_seconds = self.lag_duration * multipliers.get(self.lag_unit, 1)
        else:
            self.lag_seconds = 0

        if self.duration and self.unit:
            self.duration_seconds = self.duration * multipliers.get(self.unit, 1)
        else:
            self.duration_seconds = 0

    def __str__(self):
        if self.no:
            return f'no {self.no_what}'
        if self.lag:
            return f'lag {self.lag_duration}{self.lag_unit}'
        if self.transaction_queue:
            return f'transaction_queue {self.queue_size}'
        if self.queue:
            return f'queue {self.queue_size}'
        if self.errors:
            return 'errors'

        result = str(self.count)
        if self.percent:
            result += '%'
        result += f' {self.state}'
        if self.duration:
            result += f' for {self.duration}{self.unit}'
        return result


class ClusterDatabase:
    def __init__(self, connection):
        self.connection = connection
        self.cursor = connection.cursor()
        self._members = None
        self._cluster_info = None
        self._member_stats = None
        self._local_member_role = None
        self._replication_lag = None

    def __del__(self):
        if hasattr(self, 'connection'):
            self.connection.close()

    def execute(self, statement):
        """Return the results as a list of dicts"""
        try:
            self.cursor.execute(statement)
            col_names = [desc[0].lower() for desc in self.cursor.description]
            return [dict(zip(col_names, r)) for r in self.cursor.fetchall()]
        except Exception:
            return []

    def get_members(self):
        if self._members is None:
            self._members = self.execute('''
                                         SELECT MEMBER_ID,
                                                MEMBER_HOST,
                                                MEMBER_PORT,
                                                MEMBER_STATE,
                                                MEMBER_ROLE,
                                                MEMBER_VERSION
                                         FROM performance_schema.replication_group_members
                                         ''')
        return self._members

    def get_local_member_role(self):
        """Get the role of the current member (PRIMARY or SECONDARY)"""
        if self._local_member_role is None:
            result = self.execute('''
                                  SELECT MEMBER_ROLE
                                  FROM performance_schema.replication_group_members
                                  WHERE MEMBER_ID = @@server_uuid
                                  ''')
            if result:
                self._local_member_role = result[0]['member_role']
            else:
                self._local_member_role = 'UNKNOWN'
        return self._local_member_role

    def get_member_stats(self):
        """Get member statistics"""
        if self._member_stats is None:
            self._member_stats = {}

            stats = self.execute('''
                                 SELECT m.MEMBER_HOST,
                                        m.MEMBER_ID,
                                        COALESCE(s.COUNT_TRANSACTIONS_IN_QUEUE, 0)                as COUNT_TRANSACTIONS_IN_QUEUE,
                                        COALESCE(s.COUNT_TRANSACTIONS_CHECKED, 0)                 as COUNT_TRANSACTIONS_CHECKED,
                                        COALESCE(s.COUNT_CONFLICTS_DETECTED, 0)                   as COUNT_CONFLICTS_DETECTED,
                                        COALESCE(s.COUNT_TRANSACTIONS_REMOTE_IN_APPLIER_QUEUE, 0) as COUNT_TRANSACTIONS_REMOTE_IN_APPLIER_QUEUE,
                                        COALESCE(s.COUNT_TRANSACTIONS_REMOTE_APPLIED, 0)          as COUNT_TRANSACTIONS_REMOTE_APPLIED,
                                        COALESCE(s.COUNT_TRANSACTIONS_LOCAL_PROPOSED, 0)          as COUNT_TRANSACTIONS_LOCAL_PROPOSED,
                                        COALESCE(s.COUNT_TRANSACTIONS_LOCAL_ROLLBACK, 0)          as COUNT_TRANSACTIONS_LOCAL_ROLLBACK
                                 FROM performance_schema.replication_group_members m
                                          LEFT JOIN performance_schema.replication_group_member_stats s
                                                    ON s.MEMBER_ID = m.MEMBER_ID
                                 ''')

            for stat in stats:
                self._member_stats[stat['member_host']] = stat
        return self._member_stats

    def get_secondary_replication_lag(self):
        """Get replication lag for secondary nodes only"""
        if self._replication_lag is None:
            self._replication_lag = {}
            local_role = self.get_local_member_role()

            if local_role == 'SECONDARY':
                # For secondaries, calculate actual replication lag
                applier_data = self.execute('''
                                            SELECT PROCESSING_TRANSACTION IS NOT NULL as is_processing,
                                                   TIMESTAMPDIFF(SECOND, GREATEST(
                                                                                 PROCESSING_TRANSACTION_ORIGINAL_COMMIT_TIMESTAMP,
                                                                                 LAST_PROCESSED_TRANSACTION_ORIGINAL_COMMIT_TIMESTAMP
                                                                         ),
                                                                         NOW()
                                                   )                                  as lag_seconds
                                            FROM performance_schema.replication_applier_status_by_coordinator
                                            WHERE CHANNEL_NAME = 'group_replication_applier'
                                              AND (PROCESSING_TRANSACTION_ORIGINAL_COMMIT_TIMESTAMP > '1970-01-01'
                                                OR LAST_PROCESSED_TRANSACTION_ORIGINAL_COMMIT_TIMESTAMP > '1970-01-01')
                                            ''')

                if applier_data:
                    status = applier_data[0]
                    is_processing = status.get('is_processing', False)
                    lag_seconds = status.get('lag_seconds', 0) or 0

                    # Check if there's queue activity to determine if lag is meaningful
                    stats = self.get_member_stats()
                    current_host = self.execute('SELECT @@hostname as hostname')
                    if current_host:
                        hostname = current_host[0]['hostname']
                        host_stats = stats.get(hostname, {})

                        queue_size = host_stats.get('count_transactions_in_queue', 0) or 0
                        applier_queue = host_stats.get('count_transactions_remote_in_applier_queue', 0) or 0

                        if is_processing or queue_size > 0 or applier_queue > 0:
                            # There's active replication - report lag
                            if lag_seconds > 0:
                                self._replication_lag[hostname] = lag_seconds
                        elif lag_seconds < 60:  # Only report very recent lag for idle secondaries
                            self._replication_lag[hostname] = lag_seconds

            # Primary nodes don't have replication lag

        return self._replication_lag

    def has_replication_errors(self):
        """Check if there are any replication errors"""
        errors = self.execute('''
                              SELECT LAST_ERROR_NUMBER
                              FROM performance_schema.replication_applier_status_by_coordinator
                              WHERE CHANNEL_NAME = 'group_replication_applier'
                                AND LAST_ERROR_NUMBER > 0
                              ''')

        worker_errors = self.execute('''
                                     SELECT LAST_ERROR_NUMBER
                                     FROM performance_schema.replication_applier_status_by_worker
                                     WHERE CHANNEL_NAME = 'group_replication_applier'
                                       AND LAST_ERROR_NUMBER > 0
                                     ''')

        return len(errors) > 0 or len(worker_errors) > 0

    def get_cluster_info(self):
        if self._cluster_info is None:
            try:
                result = self.execute('''
                                      SELECT cluster_name,
                                             primary_mode,
                                             description
                                      FROM mysql_innodb_cluster_metadata.clusters LIMIT 1
                                      ''')
                if result:
                    self._cluster_info = result[0]
                else:
                    self._cluster_info = {}
            except:
                self._cluster_info = {}
        return self._cluster_info

    def get_cluster_name(self):
        info = self.get_cluster_info()
        return info.get('cluster_name', 'unknown')

    def count_members_by_state(self, state):
        return sum(1 for m in self.get_members()
                   if m['member_state'] == state.upper())

    def count_members_by_role(self, role):
        return sum(1 for m in self.get_members()
                   if m['member_role'] == role.upper())

    def get_total_members(self):
        return len(self.get_members())

    def has_quorum(self):
        online = self.count_members_by_state('ONLINE')
        total = self.get_total_members()
        return online > total / 2 if total > 0 else False

    def get_max_secondary_lag_seconds(self):
        """Get maximum replication lag in seconds (secondaries only)"""
        lag_data = self.get_secondary_replication_lag()
        if not lag_data:
            return 0
        return max(lag_data.values())

    def get_lagging_secondaries(self, threshold_seconds):
        """Get secondary members with lag exceeding threshold"""
        lag_data = self.get_secondary_replication_lag()
        lagging = {}
        for host, lag in lag_data.items():
            if lag > threshold_seconds:
                lagging[host] = lag
        return lagging

    def get_max_transaction_queue_size(self):
        """Get maximum transaction queue size"""
        stats = self.get_member_stats()
        max_queue = 0
        for host, stat in stats.items():
            queue_size = stat.get('count_transactions_in_queue', 0) or 0
            applier_queue = stat.get('count_transactions_remote_in_applier_queue', 0) or 0
            total_queue = queue_size + applier_queue
            if total_queue > max_queue:
                max_queue = total_queue
        return max_queue

    def get_members_with_large_transaction_queue(self, threshold):
        """Get members with transaction queue exceeding threshold"""
        stats = self.get_member_stats()
        large_queue_members = {}
        for host, stat in stats.items():
            queue_size = stat.get('count_transactions_in_queue', 0) or 0
            applier_queue = stat.get('count_transactions_remote_in_applier_queue', 0) or 0
            total_queue = queue_size + applier_queue
            if total_queue > threshold:
                large_queue_members[host] = total_queue
        return large_queue_members


class ClusterCheck:
    def __init__(self, db):
        self.db = db

    def get_problems(self, filters):
        problems = []
        for filtr in filters:
            problem = self.check_filter(filtr)
            if problem:
                problems.append(problem)
        return problems

    def check_filter(self, filtr):
        # Check "no" conditions
        if filtr.no:
            if filtr.no_what in ['primary', 'writer']:
                if self.db.count_members_by_role('PRIMARY') == 0:
                    return 'No primary member available'
            elif filtr.no_what == 'quorum':
                if not self.db.has_quorum():
                    online = self.db.count_members_by_state('ONLINE')
                    total = self.db.get_total_members()
                    return f'No quorum ({online}/{total} online)'
            return None

        # Check for replication errors
        if filtr.errors:
            if self.db.has_replication_errors():
                return 'Replication errors detected'

        # Check lag conditions (only applies to secondaries)
        if filtr.lag:
            local_role = self.db.get_local_member_role()
            if local_role == 'SECONDARY':
                lagging = self.db.get_lagging_secondaries(filtr.lag_seconds)
                if lagging:
                    max_lag = max(lagging.values())
                    return f'Replication lag: {max_lag}s'
            # For primary, lag check is not applicable

        # Check transaction queue conditions (PRIMARY only)
        if filtr.transaction_queue or filtr.queue:
            local_role = self.db.get_local_member_role()
            if local_role == 'PRIMARY':
                large_queue = self.db.get_members_with_large_transaction_queue(filtr.queue_size)
                if large_queue:
                    max_queue = max(large_queue.values())
                    return f'Transaction queue too large: {max_queue} transactions'
            # Skip transaction queue check for secondaries

        # Check member state conditions
        if filtr.state == 'offline':
            offline = (self.db.get_total_members() -
                       self.db.count_members_by_state('ONLINE'))
            threshold = self._get_threshold(filtr)
            if offline >= threshold:
                return f'{offline} members offline'

        elif filtr.state == 'recovering':
            recovering = self.db.count_members_by_state('RECOVERING')
            threshold = self._get_threshold(filtr)
            if recovering >= threshold:
                return f'{recovering} members recovering'

        elif filtr.state == 'error':
            error = self.db.count_members_by_state('ERROR')
            threshold = self._get_threshold(filtr)
            if error >= threshold:
                return f'{error} members in error state'

        elif filtr.state == 'unreachable':
            unreachable = self.db.count_members_by_state('UNREACHABLE')
            threshold = self._get_threshold(filtr)
            if unreachable >= threshold:
                return f'{unreachable} members unreachable'

        return None

    def _get_threshold(self, filtr):
        if filtr.percent:
            total = self.db.get_total_members()
            return (filtr.count * total) / 100.0
        return filtr.count

    def get_status_summary(self):
        """Generate a brief status summary"""
        total = self.db.get_total_members()
        online = self.db.count_members_by_state('ONLINE')
        primary = self.db.count_members_by_role('PRIMARY')
        max_transaction_queue = self.db.get_max_transaction_queue_size()
        local_role = self.db.get_local_member_role()

        # Clear role indication with 'self: role' format
        role_str = f", self: {local_role.lower()}"

        # Only show lag for secondaries
        lag_str = ""
        if local_role == 'SECONDARY':
            max_lag = self.db.get_max_secondary_lag_seconds()
            if max_lag > 0:
                lag_str = f", lag {max_lag}s"

        transaction_queue_str = f", transaction_queue {max_transaction_queue}" if max_transaction_queue > 0 else ""
        return f'{online}/{total} online, {primary} primary{role_str}{lag_str}{transaction_queue_str}'

    def get_perfdata(self):
        """Generate Nagios performance data"""
        total = self.db.get_total_members()
        online = self.db.count_members_by_state('ONLINE')
        primary = self.db.count_members_by_role('PRIMARY')
        recovering = self.db.count_members_by_state('RECOVERING')
        max_lag = self.db.get_max_secondary_lag_seconds()
        max_transaction_queue = self.db.get_max_transaction_queue_size()

        perfdata = [
            f'members_total={total}',
            f'members_online={online}',
            f'members_primary={primary}',
            f'members_recovering={recovering}',
            f'max_lag_seconds={max_lag}',
            f'max_transaction_queue_size={max_transaction_queue}',
        ]

        return ' '.join(perfdata)


if __name__ == '__main__':
    main()
