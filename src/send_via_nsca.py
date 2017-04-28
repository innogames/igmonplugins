#!/usr/bin/env python
#
# InnoGames Monitoring Plugins - send_via_nsca.py
#
# Helper script to run send results of a check via NSCA
#
# Copyright (c) 2017, InnoGames GmbH
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

import argparse
import socket
import subprocess


def parse_args():
    """Argument parser, usage helper

    Returns the parsed arguments in a dictionary.
    """
    parser = argparse.ArgumentParser(description='NSCA helper')
    parser.add_argument(
        '--target',
        action='append',
        help='NSCA server to send the status',
    )
    parser.add_argument(
        '--hostname',
        default=socket.gethostname(),
        help='Hostname to send the status for',
    )
    parser.add_argument(
        '--service',
        default='passive_check',
        help='Service to send the status for',
    )
    parser.add_argument(
        '--prefix',
        default='',
        help='Prefix the output',
    )
    parser.add_argument(
        'command',
        nargs='+',
        help='Command to run',
    )

    return vars(parser.parse_args())


def main(command, hostname, service, target, prefix):
    """The main program """
    process = subprocess.Popen(
        ' '.join(command), stdout=subprocess.PIPE, shell=True
    )
    output = prefix + (process.communicate()[0][:4096] or 'NO OUTPUT')
    result = '\t'.join((hostname, service, str(process.returncode), output))

    if target:
        for host in target:
            send_process = subprocess.Popen(
                ('send_nsca', '-H', host),
                stdin=subprocess.PIPE,
            )
            send_process.communicate(result)
    else:
        print(result)


if __name__ == '__main__':
    main(**parse_args())
