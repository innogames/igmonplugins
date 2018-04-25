#!/usr/bin/env python
#
# InnoGames Monitoring Plugins - check_mysql_slave
#
# Copyright (c) 2016, InnoGames GmbH
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

import os, MySQLdb as mdb
import optparse

parser = optparse.OptionParser()
parser.add_option('-n', '--name', help='Name of slave to check (for multi-source replication)', action='store')
parser.add_option('-u', '--user', help='Name of user for mysql connection', action='store')
parser.add_option('-p', '--password', help='Password of user for mysql connection', action='store')
(opts, args) = parser.parse_args()

CONFIG="/etc/mysql/my.cnf"
ERR={'CRITICAL':2, 'WARNING':1, 'OK':0}

def get_server_status():
    if opts.user:
        db = mdb.connect(user=opts.user, passwd=opts.password, read_default_file=CONFIG)
    else:
        db = mdb.connect(read_default_file=CONFIG)
    cur = db.cursor(mdb.cursors.DictCursor)
    if opts.name:
        cur.execute("SHOW SLAVE '" + opts.name + "' STATUS")
    else:
        cur.execute("SHOW SLAVE STATUS")
    res = cur.fetchall()
    cur.close()
    db.close()
    return res[0]

def check_server():
    try:
        s = get_server_status()
    except Exception as e:
        return ['CRITICAL', str(e.args)]

    msg = "SLAVE IO Running: " + s['Slave_IO_Running'] + ", SLAVE SQL Running: " + s['Slave_SQL_Running']
    if s['Slave_IO_Running'] != "Yes" or s['Slave_SQL_Running'] != "Yes":
        return['CRITICAL', msg]
    else:
        return['OK', msg]

status = check_server()
print ": ".join(status)
exit(ERR[status[0]])
