#!/usr/bin/env python
import sys
import MySQLdb
import argparse

#exitcodes
errorreport = {"ok":0,"warning":1,"critical":3}

def getRows():
    db = MySQLdb.connect(host="localhost", user="dsTeamNLsql4", passwd="iegohC3eeDah")
    cur = db.cursor()
    sql = "(select count(*) as stat from information_schema.processlist where time >= %s AND time < %s) union all (select count(*) as crit_stat from information_schema.processlist where time >= %s);" % (
    results.warning, results.critical, results.critical)
    cur.execute(sql)
    rows = cur.fetchall()
    db.close()
    return rows

#init parser
parser = argparse.ArgumentParser(description='Parameters for checking mysql processlist')
parser.add_argument("-w","--warning",dest="warning",nargs="?",type=int,help="Number of seconds before a warning is given -- default:90", default=90,action='store')
parser.add_argument("-c","--critical",dest="critical",nargs="?",type=int,help="Number of seconds before situation is critical -- default:120", default=120,action='store')
parser.add_argument("-x","--countw",dest="countw",nargs="?",type=int,help="Number of situations before throwing warning -- default:1", default=1,action='store')
parser.add_argument("-y","--countc",dest="countc",nargs="?",type=int,help="Number of situations before throwing critical message -- default:1", default=1,action='store')
parser.add_argument("-z","--countwarn",dest="countwarn",nargs="?",type=int,help="Number of (warning) situations before warnings are considered as critical -- default:1", default=1,action='store')

results = parser.parse_args()


rows = getRows()
#script logic
warnings =  rows[0][0];
criticals =  rows[1][0];

if criticals >= results.countc or warnings >= results.countwarn:
    sys.exit(errorreport["critical"])
elif warnings >=results.countw:
    sys.exit(errorreport["warning"])
else :
    sys.exit(errorreport["ok"])