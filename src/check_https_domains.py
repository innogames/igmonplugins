#!/usr/bin/env python
#
# InnoGames Monitoring Plugins - check_https_domains.py
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


import sys
import subprocess
import shlex
from argparse import ArgumentParser, RawTextHelpFormatter

parser = ArgumentParser(description='Check domains',
                        formatter_class=RawTextHelpFormatter)
parser.add_argument('-s', action="store", dest='hostname', help='hostname')
parser.add_argument('-i', action="store", dest='ip', help='ip of host')
parser.add_argument('-d', action="store",
                    dest='domains', help='domains of host')
args = parser.parse_args()


cmd = '/usr/lib/nagios/plugins/check_http --sni -H {} -I {} -S -C 30'

# start with unknown state and notice that is has not changes
state = 3
state_changed = False


def get_domains():
    domains = args.domains.split(',')
    if len(domains) == 1 and 'None' in domains:
        domains = []
    return domains


def set_state(returncode):
    global state
    global state_changed
    if state_changed:
        if (returncode > state and state != 2) or returncode == 2:
            state = returncode
    else:
        state = returncode
        state_changed = True


def check_domains(domains, ip, hostname):
    msg = []
    if domains and domains != ['$_HOSTDOMAINS$']:
        for domain_tmp in domains:
            domain = domain_tmp.replace('*', 'www', 1)
            command = cmd.format(domain, ip)
            args = shlex.split(command)
            p = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            p.wait()
            stdout, stderr = p.communicate()
            rc = p.returncode
            set_state(rc)
            if rc != 0:
                msg.insert(0, 'Error: {}.  Command: {}'
                           .format(stdout, command))
            else:
                msg.append('{}. Domain {}'.format(stdout.rstrip('\n'), domain))
            if stderr:
                msg.insert(0, 'Error: {}.  Command: {}'
                           .format(stderr, command))

    else:
        msg.insert(0, 'No domain found for host: {}, ip: {}'
                   .format(hostname, ip))
        set_state(3)
    message = '\n'.join(msg)
    return_result(message, state)


def return_result(message, status):
    print(message.rstrip('\n'))
    sys.exit(status)


def main():
    domains = get_domains()
    check_domains(domains, args.ip, args.hostname)
    exit()


if __name__ == '__main__':
    main()
