#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Deleted files size check

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

import os
from argparse import ArgumentParser
from pathlib import Path
from shutil import disk_usage


def walklevel(path, depth=1):
    """It works just like os.walk, but you can pass it a level parameter
       that indicates how deep the recursion will go.

       If depth is 1, the current directory is listed.
       If depth is 0, nothing is returned.
       If depth is -1 (or less than 0), the full depth is walked.

       Credit:
       https://gist.github.com/TheMatt2/faf5ca760c61a267412c46bb977718fa
    """
    if depth < 0:
        for root, dirs, files in os.walk(path):
            yield root, dirs[:], files
        return

    if depth == 0:
        return

    # path.count(os.path.sep) is safe because on UNIX
    # "/" is never allowed in the name of a file or directory
    base_depth = path.rstrip(os.path.sep).count(os.path.sep)
    for root, dirs, files in os.walk(path):
        yield root, dirs[:], files
        cur_depth = root.count(os.path.sep)
        if base_depth + depth <= cur_depth:
            del dirs[:]


def get_total_deleted_size():
    """Walks into /proc/*/fd and sums filesizes of deleted objects

    :return: byte count, float
    """

    total_size = 0

    for (dirpath, _, filenames) in walklevel('/proc', depth=2):
        if dirpath.endswith('fd'):
            for link in filenames:
                real_file = os.path.realpath('{}/{}'.format(dirpath, link))
                full_link = '{}/{}'.format(dirpath, link)
                if 'deleted' in real_file:
                    total_size += Path(full_link).stat().st_size

    return float('{}.0'.format(total_size))


def get_args():
    """Initializes parser and returns arguments"""

    parser = ArgumentParser(
        description='Nagios check for backup issues on restic repositories'
    )
    parser.add_argument(
        '-p',
        '--percentage',
        type=float,
        help='Percentage of the root disk to give warning (float, default 20)'
    )
    return parser.parse_args()


def main():
    """Removed file handles check

    Reports OK if removed file handles under /proc claims more than given
    percentage of the disk (by default, 20%)
    """

    args = get_args()
    if args.percentage is None:
        args.percentage = 20

    # Get total size of the root disk
    root_disk_size = disk_usage('/').total

    # Get percentage, rounded to 2 decimals
    result = round(get_total_deleted_size() / root_disk_size * 100, 2)

    if result > args.percentage:
        print('WARNING: deleted files occupy {}% of root disk'.format(
            result
        ))
    else:
        print('OK: deleted files occupy {}% of root disk'.format(
            result
        ))


if __name__ == '__main__':
    main()
