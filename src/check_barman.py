#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Barman Check

This is a Nagios script which checks, if the given host is currently backing
up currently on barman.

The script will exit with:
 - 0 (OK) All checks are ok, or this is a secondary node which can not be
    backed up
 - 2 (CRITICAL) Any error was detected during the backup check

Copyright (c) 2021 InnoGames GmbH
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

import sys
from subprocess import Popen, PIPE, STDOUT
from argparse import ArgumentParser


def parse_args():
    parser = ArgumentParser()
    parser.add_argument('--host',
                        help='The hostname for which to check the barman status'
                             '(e.g. "am0db1.moc.ig.local")')
    return parser.parse_args()


def main(args):
    with Popen(
        '/usr/bin/barman check --nagios {}'.format(args.host),
        shell=True,
        stderr=STDOUT,
        stdout=PIPE,
        encoding='UTF-8'
    ) as result:
        # NRPE has a 30 seconds timeout. so there is no need to wait
        # longer here
        output = result.communicate(timeout=30)[0].strip()
        return_code = result.returncode

    # Standby nodes will always throw an error. We will ignore them
    if 'cannot perform exclusive backup on a standby' in output:
        print('BARMAN OK - {} is a standby'.format(args.host))
        sys.exit(0)

    print(output)
    sys.exit(return_code)


if __name__ == '__main__':
    main(parse_args())
