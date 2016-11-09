#!/usr/bin/env python

import sys
from argparse import ArgumentParser

import MySQLdb

parser = ArgumentParser(
    description='Check a MySQL server for enough free auto_increment values')
parser.add_argument('-u', '--user', dest='user', required=True,
                    help='User with grants to connect to mysql system table')
parser.add_argument('-p', '--password', dest='password',
                    help='Password for user above')
parser.add_argument('-d', '--database', dest='database',
                    default='information_schema',
                    help='Database with system info')
parser.add_argument('-H', '--host', dest='host', default='localhost',
                    help='Mysql host to check')
parser.add_argument('-w', '--warning', type=int, default=80,
                    help='Warning when percentage of used auto_increments '
                         'is higher than this number')
parser.add_argument('-c', '--critical', type=int, default=90,
                    help='Critical when percentage of used auto_increments '
                         'is higher than this number')
parser.add_argument('-s', '--signed', dest='CHECK_SIGNED', action='store_true',
                    default=False,
                    help='Warn when we have signed auto_increments')
args = parser.parse_args()

if args.user and args.password:
    try:
        db = MySQLdb.connect(host=args.host, db=args.database,
                             user=args.user, passwd=args.password)
    except:
        print('Can not connect to host "{}" to mysql database "{}" with '
              'username "{}" and password "{}"'.format
              (args.host, args.database, args.user, args.password))
        sys.exit(3)
else:
    try:
        db = MySQLdb.connect(host=args.host, user=args.user, db=args.database)
    except:
        print('Can not connect to host "{}" to mysql database "{}" with '
              'username "{}" without password'.format
              (args.host, args.database, args.user))
        sys.exit(3)

cur = db.cursor()
cur.execute('select `TABLE_SCHEMA`, `TABLE_NAME`, `COLUMN_NAME`, `DATA_TYPE`, '
            '`COLUMN_TYPE` '
            'from `COLUMNS` '
            'where `extra` like "%auto_increment%"')

OK = []
WARNING = []
CRITICAL = []
WPCT = args.warning
CPCT = args.critical
CHECK_SIGNED = args.CHECK_SIGNED

for row in cur.fetchall():
    if row[4].find('unsigned') == -1 and CHECK_SIGNED:
        WARNING.append(
            'WARNING: Signed auto_increment found: {0}.{1} => {2}'.format(
                row[0], row[1], row[2]))
        if row[3] == 'tinyint':
            MAX = 127
        elif row[3] == 'smallint':
            MAX = 32767
        elif row[3] == 'mediumint':
            MAX = 8388607
        elif row[3] == 'int':
            MAX = 2147483647
        elif row[3] == 'bigint':
            MAX = 9223372036854775807
    else:
        if row[3] == 'tinyint':
            MAX = 255
        elif row[3] == 'smallint':
            MAX = 65535
        elif row[3] == 'mediumint':
            MAX = 16777215
        elif row[3] == 'int':
            MAX = 4294967295
        elif row[3] == 'bigint':
            MAX = 18446744073709551615

    cur.execute('SELECT `AUTO_INCREMENT` '
                'FROM `TABLES` '
                'WHERE `TABLE_SCHEMA`="{0}" '
                'and TABLE_NAME="{1}"'
                .format(row[0], row[1]))
    ACT = int(cur.fetchone()[0])
    USED = float(ACT) / float(MAX) * 100
    if USED >= CPCT:
        CRITICAL.append('CRITICAL: {0}.{1} Max: {2} - Used: {3} => {4}% used'
                        .format(row[0], row[1], MAX, ACT, round(USED, 1)))
    elif USED >= WPCT:
        WARNING.append('WARNING: {0}.{1} Max: {2} - Used: {3} => {4}% used'
                       .format(row[0], row[1], MAX, ACT, round(USED, 1)))

if len(CRITICAL) > 0:
    EXIT = 2
elif len(WARNING) > 0:
    EXIT = 1
else:
    EXIT = 0
    OK.append('OK - no extensive auto_increments found')

for line in CRITICAL:
    print(line)
for line in WARNING:
    print(line)
for line in OK:
    print(line)
sys.exit(EXIT)
