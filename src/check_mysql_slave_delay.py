#!/usr/bin/env python3
"""
InnoGames Monitoring Plugins - MySQL Replication Delay Check

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

import json
import optparse
import time

from mysql.connector import connect

STATE_FILE = '/tmp/mysql_replication_state.json'

ERR = {'CRITICAL': 2, 'WARNING': 1, 'OK': 0}


def parse_args():
    parser = optparse.OptionParser()
    parser.add_option(
        '-w',
        '--warning',
        help='Warning limit of seconds behind master',
        dest='WARN_SEC_BEHIND_MASTER',
        action='store',
        type='int',
        default=60,
    )
    parser.add_option(
        '-c',
        '--critical',
        help='Critical limit of seconds behind master',
        dest='CRIT_SEC_BEHIND_MASTER',
        action='store',
        type='int',
        default=120,
    )
    parser.add_option(
        '-n',
        '--name',
        help='Name of slave to check (for multi-source replication)',
        action='store',
    )
    parser.add_option(
        '-u',
        '--user',
        help='Name of user for mysql connection',
        action='store',
    )
    parser.add_option(
        '-p',
        '--password',
        help='Password of user for mysql connection',
        action='store',
    )
    parser.add_option('--unix-socket', default='/var/run/mysqld/mysqld.sock')
    (opts, args) = parser.parse_args()
    return opts, args


def get_server_status(opts):
    if opts.user:
        db = connect(
            user=opts.user, passwd=opts.password, unix_socket=opts.unix_socket
        )
    else:
        db = connect(unix_socket=opts.unix_socket)
    cur = db.cursor()
    if opts.name:
        cur.execute(f"SHOW SLAVE STATUS FOR CHANNEL '{opts.name}'")
    else:
        cur.execute('SHOW SLAVE STATUS')
    res = [dict(zip(cur.column_names, r)) for r in cur.fetchall()]
    cur.close()
    db.close()
    return res[0]


def load_previous_state() -> tuple[int, float]:
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
            return state['seconds_behind'], state['check_time']
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        # If file does not exist or is corrupted, return 0
        # so we can disregard the previous state
        return 0, 0


def save_current_state(seconds_behind: int) -> None:
    state = {'seconds_behind': seconds_behind, 'check_time': time.time()}
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f)
    except Exception:
        pass  # Fail silently as this is just a helper functionality


def is_catching_up(
    current_seconds: int, previous_seconds: int, previous_time: float
) -> bool:
    """Check if the slave is actually catching up with the master"""

    if previous_time == 0:
        return False

    time_diff = time.time() - previous_time
    if time_diff == 0:
        return False

    delay_diff = current_seconds - previous_seconds

    # Calculate how fast it is catching up
    catch_up_rate = delay_diff / time_diff

    # Negative means catching up
    return catch_up_rate < 0


def check_server(opts):
    try:
        s = get_server_status(opts)
    except Exception as e:
        return ['CRITICAL', str(e.args)]

    current_behind = s['Seconds_Behind_Master']
    prev_behind, prev_time = load_previous_state()

    msg = 'SLAVE IO Running: ' + s['Slave_IO_Running']
    msg += ', SLAVE SQL Running: ' + s['Slave_SQL_Running']
    msg += ', ' + str(current_behind) + ' secs behind Master'

    # Save current state for next check
    save_current_state(current_behind)

    if s['Slave_IO_Running'] != 'Yes' or s['Slave_SQL_Running'] != 'Yes':
        return ['CRITICAL', msg]

    # Critical threshold check with catch-up logic
    if current_behind > opts.CRIT_SEC_BEHIND_MASTER:
        if is_catching_up(current_behind, prev_behind, prev_time):
            # If catching up, use doubled threshold
            if current_behind > (opts.CRIT_SEC_BEHIND_MASTER * 2):
                return ['CRITICAL', msg + ' (catching up, but extremely high)']
            return ['WARNING', msg + ' (catching up from critical)']
        return ['CRITICAL', msg]

    # Warning threshold check with catch-up logic
    if current_behind > opts.WARN_SEC_BEHIND_MASTER:
        if is_catching_up(current_behind, prev_behind, prev_time):
            # If catching up, use doubled threshold
            if current_behind > (opts.WARN_SEC_BEHIND_MASTER * 2):
                return ['WARNING', msg + ' (catching up, but still high)']
            return ['OK', msg + ' (catching up)']
        return ['WARNING', msg]

    # There could be gaps in replication. We check here, because during delays
    # this might happen. To spot a gap, we check if there is more than one
    # colon per GTID line
    for line in s['Executed_Gtid_Set'].split('\n'):
        if line.count(':') > 1:
            msg = 'Gaps in replication detected: ' + line
            return ['CRITICAL', msg]

    return ['OK', msg]


def main():
    opts, _ = parse_args()
    status = check_server(opts)
    print(': '.join(status))
    exit(ERR[status[0]])


if __name__ == '__main__':
    main()
