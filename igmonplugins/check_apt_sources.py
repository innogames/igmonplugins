#!/usr/bin/env python
"""InnoGames Monitoring Plugins - APT Sources Lists Check

This is a Nagios script which checks if any sources.lists entry does not
match the protocol, hostname and domain.  It will exit with 1 (warning),
if sources entry does not match regular expression.  Should be used to ensure
sources.lists are not manipulated.

Copyright (c) 2016 InnoGames GmbH
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
import os.path
import sys
import re
from aptsources.sourceslist import SourcesList


def parse_args():
    parser = ArgumentParser(prog='check_apt_sources.py')
    parser.add_argument(
        '-p',
        action='append',
        dest='allowed_protocols',
        default=[],
        help='allowed protocols like ftp http https',
    )
    parser.add_argument(
        '-d',
        action='append',
        dest='allowed_domains',
        default=[],
        help='allowed domains or hostnames to gather packages from'
    )

    return vars(parser.parse_args())


def check_debianos():
    if not os.path.isfile('/etc/debian_version'):
        print("OK: This isn't a debian system")
        sys.exit(0)


def main(allowed_protocols, allowed_domains):
    check_debianos()
    sourceslist = SourcesList()
    external = ''
    protocols = '|'.join(allowed_protocols)
    domains = '|'.join(allowed_domains)

    sources = set(
        e.uri for e in sourceslist if e.uri and not str(e).startswith('#')
    )
    regex = re.compile(r'^({0})://([^:]+:[^@]+@)?({1})(/)?'.format(
        protocols, domains
    ))
    for source in sources:
        if not regex.match(source):
            external += '{}, '.format(source)
    if external:
        print('WARNING: external sources found: {0}'.format(external))
        sys.exit(1)

    print('OK: no external repos found')


if __name__ == '__main__':
    main(**parse_args())
