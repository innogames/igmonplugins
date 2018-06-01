#!/usr/bin/env python
#
# InnoGames Monitoring Plugins - check_swapping.py
#
# Check the swap usage
#
# This script checks the swap usage on the regarding host.
# It raises a warning if a reasonable threshold is reached.
# It raises a critical if the critical limit exceeded.
#
# Copyright (c) 2018, InnoGames GmbH
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

from argparse import ArgumentParser
import psutil


def parse_args():
    """Get argument parser -> ArgumentParser"""

    parser = ArgumentParser()
    parser.add_argument('--warning', default=80.0, type=float)
    parser.add_argument('--critical', default=90.0, type=float)

    return parser.parse_args()


def main():
    """The main program"""
    args = parse_args()

    swap_usage = get_swap_usage()

    if swap_usage >= args.critical:
        print('CRITICAL: {}% of swap is used'.format(swap_usage))
        exit(2)
    elif swap_usage >= args.warning:
        print('WARNING: {}% of swap is used'.format(swap_usage))
        exit(1)

    print('OK')
    exit(0)


def get_swap_usage():
    """Get swap usage

    Get the swap usage of the regarding host in percent of the configured
    swap file/partition.

    :return: float
    """

    percent = psutil.swap_memory().percent

    return percent


if __name__ == '__main__':
    main()
