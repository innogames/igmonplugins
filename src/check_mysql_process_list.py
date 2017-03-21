#!/usr/bin/env python
import sys
import MySQLdb
import argparse
import re

#TODO: add verbose input for timestamps (1H, 30S, ...)
#----- add for select columns (Sleep)

#exitcodes
class Exit_Codes:
    ok = 0
    warning = 1
    critical = 2

#init parser
parser = argparse.ArgumentParser(description='Parameters for checking mysql processlist')
parser.add_argument("-w","--warning",type=str,nargs="+",help="Number of occasions with number seconds before a warning is given -- default:'1 of 90'", default="1 of 90")
parser.add_argument("-c","--critical",type=str,nargs="+",help="Number of occasions with number seconds before situation is critical -- default:'1 of 120'", default="1 of 120")
args = parser.parse_args()

def get_list(count):
    try :
        db = MySQLdb.connect(host="localhost", user="user", passwd="pass")
        cur = db.cursor()
        sql = ("(select count(*) from information_schema.processlist where time >= {});").format(count)
        cur.execute(sql)
        return cur.fetchall()
    finally:
        db.close()

def is_active(count,current):
    count = int(count)
    current = int(current)
    if current >= count:
        return True
    return False


def main():
    global args
    for crit_condition in args.critical:
        match_array_crit = re.match("^([0-9]*) of ([0-9]*)$", crit_condition)
        rows = get_list(match_array_crit.group(2))
        counts =rows [0][0]
        if is_active(match_array_crit.group(1),counts) == True:
            sys.exit(Exit_Codes.critical)
            #quit script once one critical situation is detected
            quit()

    for warn_condition in args.warning:
        match_array_warning = re.match("^([0-9]*) of ([0-9]*)$", warn_condition)
        rows = get_list(match_array_warning.group(2))
        counts = rows[0][0]
        if is_active(match_array_warning.group(1),counts) == True:
            sys.exit(Exit_Codes.warning)
            #quit script once one warnable situation is detected
            quit()


    sys.exit(Exit_Codes.ok)

if __name__ == '__main__':
    main()
