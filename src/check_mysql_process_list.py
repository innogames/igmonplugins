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
parser.add_argument("-w", "--warning", type=str,nargs="+", help="Number of occasions with number seconds before a warning is given -- default:'1 of 90'", default="1 of 90")
parser.add_argument("-c", "--critical", type=str,nargs="+", help="Number of occasions with number seconds before situation is critical -- default:'1 of 120'", default="1 of 120")
parser.add_argument("-u", "--user", type=str)
parser.add_argument("-p", "--passw", type=str)

def parse_args():
    return parser.parse_args()

def get_processlist():
    args = parse_args()
    query = "select TIME,COMMAND,STATE from information_schema.processlist order by TIME DESC"
    try :
        db = MySQLdb.connect(host="localhost", user=args.user, passwd=args.passw)
        cur = db.cursor()
        cur.execute(query)
        return cur.fetchall()
    finally:
        db.close()

def handle_rows(rows):
    args = parse_args()
    reg_pattern = "^([0-9]*).*?([0-9]*)$"

    for crit_condition in args.critical:
        match_array_crit = re.match(reg_pattern, crit_condition)
        counts_needed = match_array_crit.group(1)
        count = 0
        for row in rows:
            time = row[0]
            if time >= match_array_crit.group(2):
                count = count + 1
                if count >= counts_needed:
                    sys.exit(ExitCodes.critical)
            else:
                break

    for warn_condition in args.warning:
        match_array_warn = re.match(reg_pattern, warn_condition)
        counts_needed = match_array_warn.group(1)
        count = 0
        for row in rows:
            time = row[0]
            if time >= match_array_warn.group(2):
                count = count + 1
                if count >= counts_needed:
                    sys.exit(ExitCodes.warning)
            else:
                break

    sys.exit(ExitCodes.ok)


def main():
    rows = get_processlist()
    handle_rows(rows)

if __name__ == '__main__':
    main()




