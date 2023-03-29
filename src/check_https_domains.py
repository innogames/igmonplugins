#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - HTTPS Domains Check

Copyright (c) 2019 InnoGames GmbH
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

import socket
import ssl
import sys
from argparse import ArgumentParser, RawTextHelpFormatter
from datetime import datetime, timedelta
from dateutil.parser import parse as parse_date
from dateutil.tz import tzutc
from OpenSSL import crypto
from string import ascii_letters
from random import choice 

# Amount of days remaining before warning and critical states
warn = 30
crit = 2

def parse_args():
    parser = ArgumentParser(
        description=(
            'This Nagios check retrieves certificates for the domains '
            'specified in the -d attribute and check for their expiration '
            'dates.\nThe check goes into critical if less than {crit} days '
            'are remaining and goes into warning if less than {warn} days '
            'are remaining.'
            .format(crit=crit, warn=warn)
        ),
        formatter_class=RawTextHelpFormatter
    )

    parser.add_argument(
        '-s', dest='hostname', required=True,
        help='Hostname of the host in Nagios. Only used for output building.'
    )
    parser.add_argument(
        '-i', dest='ip', required=True,
        help='IP of the host. The address where the certificate will be '
             'retrieved from.'
    )
    parser.add_argument(
        '-p', '--port', type=int, default=443,
        help='Port on the host where Nagios will connect to. Defaults to 443.'
    )
    parser.add_argument(
        '-t', '--timeout', type=int, default=2,
        help='Socket timeout (in seconds) for each SSL connection'
    )
    parser.add_argument(
        '-d', dest='domains', required=True,
        help='Domains to retrieve certificates for. For multiple domains, '
             'provide them as single string, comma separated.'
    )

    return parser.parse_args()


def main():
    args = parse_args()
    domains = get_domains(args.domains)

    if not domains or domains == ['$_HOSTDOMAINS$']:
        message = (
            'UNKNOWN - No domain found for host: {}, ip: {}'
            .format(args.hostname, args.ip)
        )
        print(message)
        sys.exit(3)

    try:
        state, output = get_check_result(
            domains, args.ip, args.port, args.timeout
        )
    except ConnectionRefusedError:
        output = 'CRITICAL - The host refused the connection'
        state = 1

    print(output)
    sys.exit(state)


def get_domains(domains):
    domains = domains.split(',')
    if len(domains) == 1 and 'None' in domains:
        domains = []
    return domains


def fetch_cert_info(domain, ip, port, timeout):
    rndpre = ''.join(choice(ascii_letters)  for i in range(20))
    domain = domain.replace('*', rndpre, 1)

    conn = ssl.create_connection((ip, port), timeout)
    context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
    with context.wrap_socket(conn, server_hostname=domain) as sock:
        cert = crypto.load_certificate(
            crypto.FILETYPE_PEM,
            ssl.DER_cert_to_PEM_cert(sock.getpeercert(True))
        )

    common_name = cert.get_subject().commonName
    not_after = parse_date(cert.get_notAfter().decode('utf-8'))
    remaining = not_after - datetime.now(tzutc())

    data = {
        'remaining': remaining, 'common_name': common_name,
        'domain': domain, 'not_after': not_after
    }
    return data


def get_check_result(domains, ip, port, timeout):
    output = []
    expirations = []

    for domain in domains:
        try:
            cert_info = fetch_cert_info(domain, ip, port, timeout)
            if cert_info['common_name'].startswith('*'):
                if cert_info['common_name'].split('.')[1:] != \
                        cert_info['domain'].split('.')[1:]:
                    return(2, 'Certificate {} does not match domain {}'.format(
                           cert_info['common_name'], cert_info['domain']))
            elif cert_info['domain'] != cert_info['common_name']:
                return(2, 'Certificate {} does not match domain {}'.format(
                       cert_info['common_name'], cert_info['domain']))
            expirations.append(cert_info)
        except (socket.timeout, TimeoutError):
            return (3, 'The connection to the destination host timed out')

    if not expirations:
        return (3, 'Could not obtain expiration dates')

    # Certificates that are closer to the expiration date are shown first
    expirations.sort(key=lambda x: x['remaining'])

    if expirations[0]['remaining'] <= timedelta(days=crit):
        state = 2
        if expirations[0]['remaining'] < timedelta(0):
            output.append(
                'CRITICAL - There are certificates expired for {} days'
                .format(-expirations[0]['remaining'].days)
            )
        else:
            output.append(
                'CRITICAL - There are certificates expiring in {} days'
                .format(expirations[0]['remaining'].days)
            )
    elif expirations[0]['remaining'] <= timedelta(days=warn):
        state = 1
        output.append(
            'WARNING - There are certificates expiring in {} days'
            .format(expirations[0]['remaining'].days)
        )
    else:
        state = 0
        output.append(
            'OK - Next certificate expiration is in {} days'
            .format(expirations[0]['remaining'].days)
        )

    for expiration in expirations:
        output.append(
            'Certificate {} for domain {} will expire in {} days ({})'
            .format(
                expiration['common_name'], expiration['domain'],
                expiration['remaining'].days,
                expiration['not_after'].strftime("%Y-%m-%d")
            )
        )

    return (state, '\n'.join(output))


if __name__ == '__main__':
    main()
