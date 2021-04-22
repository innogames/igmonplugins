#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - MySQL Configuration Check

This scripts checks the differences between the given MySQL configuration
files and running MySQL server using the "pg-config-diff" executable
from the Percona Toolkit.  TODO: Reimplement this without using the executable

Copyright (c) 2020 InnoGames GmbH
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

from argparse import ArgumentParser, RawTextHelpFormatter
from subprocess import Popen, PIPE


def parse_args():
    parser = ArgumentParser(
        formatter_class=RawTextHelpFormatter, description=__doc__
    )
    parser.add_argument(
        '--exe',
        default='/usr/bin/pt-config-diff',
        help='"pt-config-diff" executable (default: %(default)s)',
    )
    parser.add_argument(
        '--host',
        default='localhost',
        help='Target MySQL server (default: %(default)s)',
    )
    parser.add_argument(
        '--user',
        help='MySQL user (default: %(default)s)'
    )
    parser.add_argument(
        '--passwd',
        help='MySQL password (default: %(default)s)'
    )
    parser.add_argument(
        '--ignore_vars',
        default='wsrep_sst_auth',
        help='Varaibles that don\'t get checked (default: %(default)s)'
    )
    parser.add_argument('conf_files', nargs='+')

    return parser.parse_args()


def main():
    args = parse_args()
    conn_str = ','.join(
        k[0] + '=' + v
        for k, v in vars(args).items()
        if k in ['host', 'user', 'passwd'] and v
    )
    command = [
        args.exe,
        '--ignore-variables={}'.format(args.ignore_vars),
        '--report-width=140',
        conn_str,
    ]

    # Start the check processes in parallel
    check_procs = []
    for conf_file in args.conf_files:
        with open(conf_file) as conf_fd:
            for line in conf_fd:
                if line.strip() == '[mysqld]':
                    break
            else:
                continue
        proc = Popen(command + [conf_file], stdout=PIPE)
        check_procs.append(proc)

    # Wait for all check processes to finish
    exit_code = max(p.wait() for p in check_procs)
    if exit_code == 0:
        print('OK: pt-config-diff found no difference')
    else:
        print('WARNING: pt-config-diff failed:')
        for proc in check_procs:
            stdout = proc.stdout.read()
            if stdout:
                print(stdout.decode())
    exit(exit_code)


if __name__ == '__main__':
    main()
