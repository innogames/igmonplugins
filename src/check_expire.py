#!/usr/bin/env python3

import datetime
import dateutil.parser
import argparse
import sys
import OpenSSL
from dateutil.tz import tzutc

parser = argparse.ArgumentParser()
parser.add_argument('-f', '--file', dest='pemfile', required=True,
                    help='the file to be checked pem encoded x509 certificate')
parser.add_argument('-a', '--not-valid-after', dest='not_valid_after',
                    required=True,
                    help='set the validity condition to check if the cert will'
                    ' expire within the time given, supports now, now-Xd (days'
                    '), now-Xh (hours)')
parser.add_argument('-n', '--name', dest='names', action='append',
                    help='check if the certificate is valid for a given name, '
                    'can be used multiple times')
args = parser.parse_args()


def exit(code=3, reason=''):
    if code == 0:
        print(reason)
        print("OK")
    elif code == 1:
        print(reason)
        print("Fail")
    elif code == 2:
        print(reason)
        print("Fail")
    else:
        print(reason)
    sys.exit(code)


def check_time(args):
    now = datetime.datetime.now(tzutc())

    if args.not_valid_after:
        if args.not_valid_after == 'now':
            delta = datetime.timedelta(hours=0)
        elif (args.not_valid_after.startswith('now') and
                args.not_valid_after.endswith('h')):
            h = int(args.not_valid_after.split('-', 1)[1].rstrip('h'))
            delta = datetime.timedelta(hours=h)
        elif (args.not_valid_after.startswith('now') and
                args.not_valid_after.endswith('d')):
            d = int(args.not_valid_after.split('-', 1)[1].rstrip('d'))
            delta = datetime.timedelta(days=d)
        else:
            exit(3, 'Unknwon Error')
    else:
        exit(3, 'Unknwon Error')

    if not_after > now + delta:
        return(0, "Certificate expires at: {}".format(not_after))
    elif not_after < now:
        return(2, "Certificate expired at: {}".format(not_after))
    else:
        return(1, "Certificate expires at: {}".format(not_after))


def verify_domains(args, cert_domains):
    for domain in args.names:
        if domain.find('.') != -1:
            wildcard = str('*.' + domain.split('.', 1)[1])
        else:
            wildcard = []
        if not domain in cert_domains and not wildcard in cert_domains:
            return(2, "{} not found".format(domain))

    return(0, "All domains Found")


def get_issued_to(x509):
    for i in x509.get_subject().get_components():
        if i[0] == b'CN':
            return([i[1].decode()])
    return(False)


def get_extension_value(x509, short_name):
    ext_num = 0
    while ext_num < x509.get_extension_count():
        if x509.get_extension(ext_num).get_short_name() == short_name:
            return(x509.get_extension(ext_num).__str__())
        ext_num += 1
    return(False)


def decode_san(san_string):
    alternate_names = []
    if san_string:
        for i in san_string.split(','):
            if i.split(':', 1)[0].strip() == 'DNS':
                alternate_names.append(i.split(':', 1)[1])
    return(alternate_names)


with open(args.pemfile, 'rb') as f:
    pem_data = f.read()
    x509 = OpenSSL.crypto.load_certificate(
        OpenSSL.crypto.FILETYPE_PEM, pem_data)
    not_after = dateutil.parser.parse(x509.get_notAfter().decode("utf-8"))

time_error_code, time_reason = check_time(args)
domain_error_code = 0
domain_reason = ''

if args.names:
    issued_to = get_issued_to(x509)
    alternate_names = decode_san(get_extension_value(x509, b'subjectAltName'))
    domain_error_code, domain_reason = verify_domains(
        args, issued_to + alternate_names)

exit(max([time_error_code, domain_error_code]),
     '\n'.join([time_reason, domain_reason]))
