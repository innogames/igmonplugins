#!/usr/bin/env python
"""
InnoGames Monitoring Plugins - MySQL Replication Delay Check

Copyright (c) 2016 InnoGames GmbH
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

from mysql.connector import connect
import optparse


parser = optparse.OptionParser()
parser.add_option('-w', '--warning', help='Warning limit of seconds behind master', dest='WARN_SEC_BEHIND_MASTER', action='store', type='int', default=60)
parser.add_option('-c', '--critical', help='Critical limit of seconds behind master', dest='CRIT_SEC_BEHIND_MASTER', action='store', type='int', default=120)
parser.add_option('-n', '--name', help='Name of slave to check (for multi-source replication)', action='store')
parser.add_option('-u', '--user', help='Name of user for mysql connection', action='store')
parser.add_option('-p', '--password', help='Password of user for mysql connection', action='store')
parser.add_option('--unix-socket', default='/var/run/mysqld/mysqld.sock')
(opts, args) = parser.parse_args()

ERR={'CRITICAL':2, 'WARNING':1, 'OK':0}

def get_server_status():
    if opts.user:
        db = connect(user=opts.user, passwd=opts.password, unix_socket=opts.unix_socket)
    else:
        db = connect(unix_socket=opts.unix_socket)
    cur = db.cursor()
    if opts.name:
        cur.execute("SHOW SLAVE '" + opts.name + "' STATUS")
    else:
        cur.execute("SHOW SLAVE STATUS")
    res = [dict(zip(cur.column_names, r)) for r in cur.fetchall()]
    cur.close()
    db.close()
    return res[0]

def check_server():
    try:
        s = get_server_status()
    except Exception as e:
        return ['CRITICAL', str(e.args)]
    msg = "SLAVE IO Running: " + s['Slave_IO_Running'] + ", SLAVE SQL Running: " + s['Slave_SQL_Running'] + ", " + str(s['Seconds_Behind_Master']) + " secs behind Master"
    if s['Slave_IO_Running'] != "Yes" or s['Slave_SQL_Running'] != "Yes" or s['Seconds_Behind_Master'] > opts.CRIT_SEC_BEHIND_MASTER:
        return['CRITICAL', msg]
    if s['Seconds_Behind_Master'] > opts.WARN_SEC_BEHIND_MASTER:
        return['WARNING', msg]
    return['OK', msg]

status = check_server()
print(": ".join(status))
exit(ERR[status[0]])
