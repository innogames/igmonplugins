#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Expiring X509 CRL Check

Copyright (c) 2023 InnoGames GmbH
"""
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the 'Software'), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED 'AS IS', WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

from argparse import ArgumentParser, FileType
from datetime import datetime, timedelta
from sys import exit

from cryptography import x509


def parse_args():
    parser = ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        'pemfile',
        type=FileType('rb'),
        help='The file to be checked pem encoded cert certificate',
        nargs='?'
    )
    parser.add_argument(
        '--warning',
        type=interval,
        default='30 days',
        help='Warning threshold for certificate to expire (default: 30 days)',
    )
    parser.add_argument(
        '--critical',
        type=interval,
        default='1 days',
        help='Critical threshold for certificate to expire (default: 1 days)',
    )

    return parser.parse_args()


def main():
    args = parse_args()

    if args.pemfile:
        crl = x509.load_pem_x509_crl(args.pemfile.read())

    not_after = crl.next_update
    remaining = not_after - datetime.now()
    exit_code = 0

    output = 'CRL expires at: {}'.format(not_after)
    if remaining < args.critical:
        exit_code = 2
    elif remaining < args.warning:
        exit_code = 1

    if exit_code == 0:
        print('OK: ' + output)
    elif exit_code == 1:
        print('WARNING: ' + output)
    elif exit_code == 2:
        print('CRITICAL: ' + output)
    exit(exit_code)


def interval(arg):
    index = next(
        index
        for index, char in enumerate(arg)
        if not char.isdigit()
    )
    number = int(arg[:index].strip())
    unit = arg[index:].strip()

    return timedelta(**{unit: number})


if __name__ == '__main__':
    main()
