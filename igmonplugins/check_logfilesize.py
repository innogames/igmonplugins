#!/usr/bin/env python
"""InnoGames Monitoring Plugins - Log File Size Check

This scripts checks the size of the directory by traveling files inside
and logging how many of them are passing the user-defined limits.

Copyright (c) 2018 InnoGames GmbH
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

import os
import sys
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
