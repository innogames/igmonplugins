#!/usr/bin/env python
"""InnoGames Monitoring Plugins - check_logfilesize.py

This scripts checks the size of the directory by traveling files inside
and logging how many of them are passing the user-defined limits.

Copyright (c) 2018, InnoGames GmbH
"""

import os
import sys
import subprocess
import argparse

def parse_cmd_args():

    parser = argparse.ArgumentParser(
        description='A small nagios script to check '
                    'for size of logfiles in given directory')

    parser.add_argument('-p', dest='path', help='Define the directory in which the check should run')
    parser.add_argument('-w', dest='warning', help='Define the warning threshold in MB')
    parser.add_argument('-c', dest='critical', help='Define the critical threshold in MB')
    return parser.parse_args()


def main():
    args = parse_cmd_args()
    critical_count = 0
    warning_count = 0
    files = ''

    for filename in os.listdir(args.path):
        if filename.endswith('.log'):
            current_file_size = file_size_mb(args.path + '/' + filename)
            if current_file_size > int(args.critical):
                critical_count += 1
                files += args.path + '/' + filename + ' ' + str(current_file_size) + 'MB\n'
            elif current_file_size > int(args.warning):
                warning_count += 1
                files += args.path + '/' + filename + ' ' + str(current_file_size) + 'MB\n'

    if critical_count > 0:
        print('Critical')
        print(files)
        sys.exit(2)
    elif warning_count > 0:
        print('Warning')
        print(files)
        sys.exit(1)
    else:
        print('OK')
        sys.exit(0)


def file_size_mb(filePath):
    return os.path.getsize(filePath) / (1024**2)

if __name__ == '__main__':
    main()
