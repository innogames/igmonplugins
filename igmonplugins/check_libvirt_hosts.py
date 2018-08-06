#!/usr/bin/env python
"""InnoGames Monitoring Plugins - Libvirt Hosts Check

Copyright (c) 2017 InnoGames GmbH
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

from sys import exit

from libvirt import openReadOnly, libvirtError


def main():
    try:
        conn = openReadOnly(None)
    except libvirtError as error:
        print('WARNING: could not connect to libvirt: ' + str(error))
        exit(1)

    inactive_domains = [d for d in conn.listAllDomains() if not d.isActive()]
    if inactive_domains:
        print('WARNING: ' + ', '.join(
            '{} is defined but not running'.format(d.name())
            for d in inactive_domains
        ))
        exit(1)

    print('OK: all defined domains are running')
    exit(0)


if __name__ == '__main__':
    main()
