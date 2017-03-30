#!/usr/bin/env python
import sys
import MySQLdb
import argparse
import re

#TODO: add verbose input for timestamps (1H, 30S, ...)
#----- add for select columns (Sleep)

#exitcodes
class ExitCodes:
    ok = 0
    warning = 1
    critical = 2

#init parser
parser = argparse.ArgumentParser(description='Parameters for checking mysql processlist')
parser.add_argument("-w","--warning",type=str,nargs="+",help="Number of occasions with number seconds before a warning is given -- default:'1 of 90'", default="1 of 90")
parser.add_argument("-c","--critical",type=str,nargs="+",help="Number of occasions with number seconds before situation is critical -- default:'1 of 120'", default="1 of 120")
parser.add_argument("-u","--user",type=str)
parser.add_argument("-p","--passw",type=str)

def parse_args():
    args = parser.parse_args()
    return args

def get_list(query):
    args = parse_args()
    try :
        db = MySQLdb.connect(host="localhost", user=args.user, passwd=args.passw)
        cur = db.cursor()
        cur.execute(query)
        return cur.fetchall()
    finally:
        db.close()


def build_query():
    args = parse_args()
    reg_pattern = "^([0-9]*).*?([0-9]*)$"
    base_query = "(select count(*) from information_schema.processlist where"
    critical_query = base_query
    warn_query = base_query
    i = 0
    for crit_condition in args.critical:
        match_array_crit = re.match(reg_pattern, crit_condition)
        query_or = (" time > {}").format(match_array_crit.group(2))
        critical_query += query_or
        if i != len(args.critical)-1:
            critical_query += " OR"
        i = i+1
    critical_query += ")"

    i = 0
    for warn_condition in args.warning:
        match_array_warning = re.match(reg_pattern, warn_condition)
        query_or = (" time > {}").format(match_array_warning.group(2))
        warn_query += query_or
        if i != len(args.warning)-1:
            warn_query += " OR"
        i = i+1
    warn_query += ")"

    final_query = critical_query + " UNION ALL " + warn_query + ";"
    return final_query


def main():
    query =  build_query()
    rows = get_list(query)
    count_criticals = rows[0][0]
    count_warnings = rows[1][0]
    if count_criticals != 0:
        sys.exit(ExitCodes.critical)
    elif count_warnings != 0:
        sys.exit(ExitCodes.warning)
    sys.exit(ExitCodes.ok)

if __name__ == '__main__':
    main()