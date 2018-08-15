#!/usr/bin/env python
"""InnoGames Monitoring Plugins - Cisco Router Health Check

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

from argparse import ArgumentParser
import pexpect
import sys


# Nagios plugin exit codes
class ExitCodes:
    ok = 0
    warning = 1
    critical = 2
    unknown = 3


class CiscoCmdline:
    prompt = '[a-z0-9\-\.]+>'
    invalid = '% Invalid.*'
    incomplete = '% Incomplete command.*'


def main():
    args = parse_args()

    try:
        conn = login(args.host, args.user, args.password)
    except Exception as e:
        print(e)
        return ExitCodes.unknown

    status = command(conn, 'show environment')[0]
    performance_data = command(conn, 'show environment all')

    conn.sendline()
    conn.expect(CiscoCmdline.prompt)
    conn.sendline('exit')
    conn.expect('.*closed by remote host|Connection to.*closed', timeout=5)

    if status == 'All measured values are normal':
        local_exit = ExitCodes.ok

        # If one of the powersupplies is down, give a warning
        for line in performance_data:
            if 'AC Power Supply. Unit is off.' in line:
                status += (
                    ', but power redundancy is lost!'
                    ' Please check powersupplies'
                )
                local_exit = ExitCodes.warning
    else:
        local_exit = ExitCodes.critical

    # report status to nagios and set proper exit code
    print('{} | {}'.format(status, '\n'.join(performance_data)))
    return local_exit


def parse_args():
    parser = ArgumentParser()

    parser.add_argument('-H', dest='host', help='host', required=True)
    parser.add_argument('-u', dest='user', help='user', required=True)
    parser.add_argument('-p', dest='password', help='password', required=True)

    return parser.parse_args()


def login(host, user, password):
    conn = pexpect.spawn(
        'ssh -oKexAlgorithms=+diffie-hellman-group1-sha1 {}@{}'.format(user, host),
        timeout=5
    )

    try:
        conn.expect('[Pp]assword:')

    except pexpect.EOF as e:
        raise pexpect.EOF(
            'Connection closed while waiting for password prompt. '
            'SSH message:\n' + conn.before
        )

    except pexpect.TIMEOUT as e:
        raise pexpect.TIMEOUT(
            'Connection timed out while waiting for password prompt! '
            'SSH message:\n' + conn.before
        )

    else:
        conn.sendline(password)

        index2 = conn.expect([
              CiscoCmdline.prompt,
              '[Pp]assword:',
            ])

        if index2 == 0:
            # Do some magic so any commands called later won't demand
            # pressing space or enter.
            conn.sendline('terminal length 0')
            conn.expect(CiscoCmdline.prompt)
            return conn

        elif index2 == 1:
            raise pexpect.EOF(
                'Device refused login, probably wrong password. Giving up!'
            )


def command(conn, cmd):
    conn.sendline(cmd)
    i = conn.expect(CiscoCmdline.prompt)
    out = conn.before.splitlines()[1:]
    if i == 0:
        return out
    else:
        conn.sendline()


if __name__ == "__main__":
    sys.exit(main())
