#!/usr/bin/env python
"""InnoGames Monitoring Plugins - HTTPS Domains Check

Copyright (c) 2017 InnoGames GmbH
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

import ssl
import sys
from argparse import ArgumentParser, RawTextHelpFormatter
from datetime import datetime, timedelta
from dateutil.parser import parse
from dateutil.tz import tzutc
from OpenSSL import crypto

# Amount of days remaining before warning and critical states
warn = 30
crit = 2

def parse_args():
    parser = ArgumentParser(
        description='Check domains',
        formatter_class=RawTextHelpFormatter
    )

    parser.add_argument(
        '-s', dest='hostname', required=True,
        help='hostname'
    )
    parser.add_argument(
        '-i', dest='ip', required=True,
        help='ip of host'
    )
    parser.add_argument(
        '-d', dest='domains', required=True,
        help='domains of host'
    )

    return parser.parse_args()

def get_domains(domains):
    domains = domains.split(',')
    if len(domains) == 1 and 'None' in domains:
        domains = []
    return domains


def fetch_cert_info(domain, ip):
    domain = domain.replace('*', 'www', 1)
    conn = ssl.create_connection((ip, 443))
    context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
    with context.wrap_socket(conn, server_hostname=domain) as sock:
        cert = crypto.load_certificate(
            crypto.FILETYPE_PEM,
            ssl.DER_cert_to_PEM_cert(sock.getpeercert(True))
        )
    common_name = cert.get_subject().commonName
    not_after = parse(cert.get_notAfter().decode('utf-8'))
    remaining = not_after - datetime.now(tzutc())

    data = {'remaining': remaining, 'common_name': common_name,
            'domain': domain, 'not_after': not_after}
    return data


def get_check_result(domains, ip):
    output = []
    expirations = []

    for domain in domains:
        expirations.append(fetch_cert_info(domain, ip))

    # Certificates that are closer to the expiration date are shown first
    expirations.sort(key=lambda x: x['remaining'])

    if expirations[0]['remaining'] <= timedelta(days=crit):
        state = 2
        if expirations[0]['remaining'] < timedelta(0):
            output.append(
                'CRITICAL - There are certificates expired for {} days'.format(
                    -expirations[0]['remaining'].days))
        else:
            output.append(
                'CRITICAL - There are certificates expiring in {} days'.format(
                    expirations[0]['remaining'].days))
    elif expirations[0]['remaining'] <= timedelta(days=warn):
        state = 1
        output.append(
            'WARNING - There are certificates expiring in {} days'.format(
                expirations[0]['remaining'].days))
    else:
        state = 0
        output.append('OK - Next certificate expiration is in {} days'.format(
            expirations[0]['remaining'].days))

    for expiration in expirations:
        output.append(
            'Certificate {} for domain {} will expire in {} days ({})'.format(
                expiration['common_name'], expiration['domain'],
                expiration['remaining'].days,
                expiration['not_after'].strftime("%Y-%m-%d")))

    return (state, '\n'.join(output))


def return_result(state, message):
    print(message)
    sys.exit(state)


def main():
    args = parse_args()
    domains = get_domains(args.domains)

    if not (domains and domains != ['$_HOSTDOMAINS$']):
        return_result(3, 'UNKNOWN - No domain found for host: {}, ip: {}'
                      .format(args.hostname, args.ip))
    state, output = get_check_result(domains, args.ip)
    return_result(state, output)


if __name__ == '__main__':
    main()
