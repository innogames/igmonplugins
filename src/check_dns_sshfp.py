#!/usr/bin/env python
"""InnoGames Monitoring Plugins - check_dns_sshfp.py

This check queries and compares SSHFP records from the DNS with the keys
on the server it is running.

Copyright (c) 2017, InnoGames GmbH
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

from socket import getfqdn
from subprocess import check_output
from sys import exit

from dns.exception import DNSException
from dns.rdata import from_text as dns_from_text
from dns.rdataclass import IN
from dns.rdatatype import SSHFP
from dns.resolver import query as dns_query


def main():

    # If we don't append the trailing dot, the query would try the DNS search
    # path.
    fqdn = getfqdn() + '.'

    try:
        result = dns_query(fqdn, SSHFP)
    except DNSException:
        print('WARNING got no host key fingerprint')
        exit(1)

    # Map the host keys in a dictionary using the algorithm and the fingerprint
    # type as the identifier for fast lookup while comparing them with the keys
    # from the DNS.
    output = check_output(['ssh-keygen', '-r', fqdn], universal_newlines=True)
    host_keys = {(r.algorithm, r.fp_type): r for r in (
        dns_from_text(IN, SSHFP, l.split(None, 3)[3])
        for l in output.splitlines()
    )}

    for record in result.rrset:
        record_id = (record.algorithm, record.fp_type)
        if record_id not in host_keys:
            print('WARNING host key for fingerprint does not exist')
            exit(1)
        if record.fingerprint != host_keys[record_id].fingerprint:
            print('WARNING host key fingerprint is inconsistent')
            exit(1)

    print('OK')
    exit(0)


if __name__ == '__main__':
    main()
