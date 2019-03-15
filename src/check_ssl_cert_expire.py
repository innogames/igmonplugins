#!/usr/bin/env python
"""InnoGames Monitoring Plugins - Expiring SSL Certificates Check

Copyright (c) 2019 InnoGames GmbH
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

from builtins import str
from OpenSSL import crypto
from argparse import ArgumentParser, FileType
from datetime import datetime, timedelta
from dateutil.tz import tzutc
from dateutil.parser import parse
from sys import exit
import ssl
import ipaddress


def parse_args():
    parser = ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        'pemfile',
        type=FileType('rb'),
        help='The file to be checked pem encoded cert certificate',
        nargs='?'
    )
    group.add_argument(
        '--pemfile',
        dest='pemfile_n',
        type=FileType('rb'),
        help='The file to be checked pem encoded cert certificate',
    )
    group.add_argument(
        '--remote',
        dest='remote',
        action='store',
        help='Query a remote host rather than a local file',
    )
    parser.add_argument(
        '--warning',
        type=interval,
        default='30 days',
        help='Warning threshold for certificate to expire (default: 30 days)',
    )
    parser.add_argument(
        '--critical',
        type=interval,
        default='1 days',
        help='Critical threshold for certificate to expire (default: 1 days)',
    )
    parser.add_argument(
        '--name',
        dest='names',
        action='append',
        type=str,
        help='Check if the certificate is valid for a given names' +
                'if --remote is used only up to 1 name is supported'
    )
    parser.add_argument(
        '--port',
        dest='port',
        action='store',
        default=443,
        help='Provide a port to connect to to --remote'
    )

    return parser.parse_args()


def main():
    args = parse_args()

    # Workaround needed to keep compatibility with positional and
    # named arguments
    if args.pemfile_n:
        args.pemfile = args.pemfile_n

    if args.pemfile:
        cert = crypto.load_certificate(
                crypto.FILETYPE_PEM, args.pemfile.read())
    elif args.remote:
        hostname = args.remote
        if args.names:
            hostname = args.names[0]
        conn = ssl.create_connection((args.remote, args.port))
        context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        sock = context.wrap_socket(conn, server_hostname=hostname)
        cert = crypto.load_certificate(
                crypto.FILETYPE_PEM,
                ssl.DER_cert_to_PEM_cert(sock.getpeercert(True)))

    not_after = parse(cert.get_notAfter().decode('utf-8'))
    remaining = not_after - datetime.now(tzutc())
    exit_code = 0
    output = ''

    if args.names:
        missing_domain = verify_domains(cert, args.names)
        if missing_domain:
            output += '{} not found; '.format(missing_domain)
            exit_code = 2

    output += 'Certificate expires at: {}'.format(not_after)
    if remaining < args.critical:
        exit_code = 2
    elif remaining < args.warning:
        exit_code = 1

    if exit_code == 0:
        print('OK: ' + output)
    elif exit_code == 1:
        print('WARNING: ' + output)
    elif exit_code == 2:
        print('CRITICAL: ' + output)
    exit(exit_code)


def interval(arg):
    index = next(
        index
        for index, char in enumerate(arg)
        if not char.isdigit()
    )
    number = int(arg[:index].strip())
    unit = arg[index:].strip()

    return timedelta(**{unit: number})


def verify_domains(cert, names):
    cert_domains = {get_issued_to(cert)}
    for alt_domain in decode_san(get_extension_value(cert, b'subjectAltName')):
        cert_domains.add(alt_domain)

    cert_domains = set(map(expand_ip, cert_domains))

    names = set(map(expand_ip, names))

    for domain in names:
        if domain in cert_domains:
            continue
        if '.' in domain:
            wildcard = '*.' + domain.split('.', 1)[1]
            if wildcard in cert_domains:
                continue

        return domain


def get_issued_to(cert):
    for components in cert.get_subject().get_components():
        if components[0] == b'CN':
            return components[1].decode()


def get_extension_value(cert, short_name):
    for ext_num in range(cert.get_extension_count()):
        if cert.get_extension(ext_num).get_short_name() == short_name:
            return str(cert.get_extension(ext_num))


def decode_san(san_string):
    if not san_string:
        return

    for item in san_string.split(','):
        key, value = item.split(':', 1)
        key = key.strip().lower()
        if key == 'dns' or key == 'ip address':
            yield value.strip()


def expand_ip(name):
    try:
        eip = ipaddress.ip_address(name).compressed
        return eip
    except ValueError as e:
        return name


if __name__ == '__main__':
    main()
