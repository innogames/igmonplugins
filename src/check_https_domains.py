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
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import math
import socket
import ssl
import sys
from argparse import ArgumentParser, RawTextHelpFormatter
from datetime import datetime, timedelta

from dateutil.parser import parse as parse_date
from dateutil.tz import tzutc
from OpenSSL import crypto


# Amount of days remaining before warning and critical states.
warn = 30
crit = 2


def parse_args():
    parser = ArgumentParser(
        description=(
            'This Nagios check retrieves certificates for the domains '
            'specified in the -d attribute and checks their expiration '
            f'dates.\nThe check goes critical if {crit} days or fewer '
            f'remain and warning if {warn} days or fewer remain.'
        ),
        formatter_class=RawTextHelpFormatter,
    )

    parser.add_argument(
        '-s',
        dest='hostname',
        required=True,
        help='Hostname of the host in Nagios. Only used for output building.',
    )

    parser.add_argument(
        '-i',
        dest='ip',
        required=True,
        help='IP of the host. The address where the certificate will be '
             'retrieved from.',
    )

    parser.add_argument(
        '-p',
        '--port',
        type=int,
        default=443,
        help='Port on the host where Nagios will connect to. Defaults to 443.',
    )

    parser.add_argument(
        '-t',
        '--timeout',
        type=int,
        default=2,
        help='Socket timeout in seconds for each SSL connection.',
    )

    parser.add_argument(
        '-d',
        dest='domains',
        required=True,
        help='Domains to retrieve certificates for. For multiple domains, '
             'provide them as a single comma-separated string.',
    )

    return parser.parse_args()


def main():
    args = parse_args()
    domains = get_domains(args.domains)

    if not domains or domains == ['$_HOSTDOMAINS$']:
        print(
            f'No domains configured for {args.hostname} '
            f'({args.ip})'
        )
        sys.exit(3)

    try:
        state, output = get_check_result(
            domains,
            args.ip,
            args.port,
            args.timeout,
        )
    except ConnectionRefusedError:
        output = f'Connection refused ({args.ip}:{args.port})'
        state = 2

    print(output)
    sys.exit(state)


def get_domains(domains):
    domains = [
        domain.strip()
        for domain in domains.split(',')
        if domain.strip()
    ]

    if len(domains) == 1 and domains[0] == 'None':
        domains = []

    return domains


def format_remaining(remaining):
    """Return a compact, correctly rounded expiration description."""
    seconds = remaining.total_seconds()

    if seconds > 0:
        if seconds < 3600:
            return 'expires in <1h'

        if seconds < 2 * 86400:
            hours = math.ceil(seconds / 3600)
            return f'expires in {hours}h'

        days = math.ceil(seconds / 86400)
        return f'expires in {days}d'

    elapsed = abs(seconds)

    if elapsed < 3600:
        return 'expired <1h ago'

    if elapsed < 2 * 86400:
        hours = math.ceil(elapsed / 3600)
        return f'expired {hours}h ago'

    days = math.ceil(elapsed / 86400)
    return f'expired {days}d ago'


def fetch_cert_info(domain, ip, port, timeout):
    configured_domain = domain
    domain = domain.replace('*', 'www', 1)

    conn = socket.create_connection(
        (ip, port),
        timeout,
    )

    conn = socket.create_connection((ip, port), timeout)

    with context.wrap_socket(
        conn,
        server_hostname=domain,
    ) as sock:
        certificate = sock.getpeercert(binary_form=True)

    certificate = crypto.load_certificate(
        crypto.FILETYPE_ASN1,
        certificate,
    )

    common_name = certificate.get_subject().commonName
    not_after = parse_date(
        certificate.get_notAfter().decode('utf-8')
    )
    remaining = not_after - datetime.now(tzutc())

    return {
        'remaining': remaining,
        'common_name': common_name,
        'domain': configured_domain,
        'not_after': not_after,
    }


def get_check_result(domains, ip, port, timeout):
    output = []
    expirations = []

    for domain in domains:
        try:
            cert_info = fetch_cert_info(
                domain,
                ip,
                port,
                timeout,
            )
            expirations.append(cert_info)

        except socket.timeout:
            return (
                3,
                f'{domain}: timed out after {timeout}s '
                f'({ip}:{port})',
            )

    if not expirations:
        return (
            3,
            f'Could not obtain certificate expiration dates '
            f'from {ip}:{port}',
        )

    # Certificates closest to expiration are shown first.
    expirations.sort(
        key=lambda expiration: expiration['remaining']
    )

    earliest = expirations[0]

    if earliest['remaining'] <= timedelta(days=crit):
        state = 2
    elif earliest['remaining'] <= timedelta(days=warn):
        state = 1
    else:
        state = 0

    total = len(expirations)
    certificate_word = (
        'certificate'
        if total == 1
        else 'certificates'
    )

    earliest_date = earliest['not_after'].strftime('%Y-%m-%d')
    earliest_description = format_remaining(
        earliest['remaining']
    )

    # Do not print detail lines for healthy certificates.
    if state == 0:
        output.append(
            f'Checked {total} {certificate_word}; '
            f'earliest expiry: {earliest["domain"]} '
            f'{earliest_description} ({earliest_date})'
        )

        return state, '\n'.join(output)

    affected = [
        expiration
        for expiration in expirations
        if expiration['remaining'] <= timedelta(days=warn)
    ]

    affected_count = len(affected)

    if total == 1:
        summary = '1 certificate needs attention'
    elif affected_count == 1:
        summary = (
            f'1 of {total} certificates needs attention'
        )
    else:
        summary = (
            f'{affected_count} of {total} certificates '
            f'need attention'
        )

    output.append(
        f'{summary}; most urgent: '
        f'{earliest["domain"]} '
        f'{earliest_description} ({earliest_date})'
    )

    # Show details only for certificates requiring attention.
    for expiration in affected:
        expiration_date = expiration['not_after'].strftime(
            '%Y-%m-%d'
        )
        description = format_remaining(
            expiration['remaining']
        )

        output.append(
            f'{expiration["domain"]}: '
            f'{description} ({expiration_date})'
        )

    return state, '\n'.join(output)


if __name__ == '__main__':
    main()

