#!/usr/bin/env python

# InnoGames Monitoring Plugins - check_ssl_expiry.py
#
# This is a script that checks for ssl certificatexpiration in the next 30 days
# for all ssl certificate files in a given directory.
# The script will exit with:
#  - 0 (OK) if no certificate in the checked directory will expire in the next
#           30 days
#
#  - 1 (Warning) if a script in the checked directory will expire in the next
#                30 days
# Copyright (c) 2016, InnoGames GmbH
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

import sys
import os
import time
import datetime
import fnmatch
from argparse import ArgumentParser
from OpenSSL import crypto


def parse_args():
    parser = ArgumentParser()
    parser.add_argument('--cert-dir', dest='cert_dir',
                        help='The folder containing the certificates to check')
    parser.add_argument('--warning-days', dest='warning_days', default=30,
                        help='Days before expiry of a cert that a warning is '
                        'triggered. Will be thirty if left unspecified')
    parser.add_argument('--crit-days', dest='crit_days', default=7,
                        help='Days before expiry of a cert that a warning is '
                        'triggered. Will be thirty if left unspecified')
    return parser.parse_args()


def main(args):
    warn_cns = ''
    crit_cns = ''
    days_to_seconds = 86400
    check_time = int(time.time() + int(args.warning_days) * days_to_seconds)
    cert_dir = args.cert_dir
    certs = os.listdir(cert_dir)
    wanted_extensions = ['pem', 'crt', 'ca-bundle']

    for certfile in certs:
        st_cert = open(os.path.join(cert_dir, certfile), 'r').read()
        crypto_object = crypto
        extension = certfile.rsplit('.', 1)[-1]
        if extension not in wanted_extensions:
            continue

        certobject = crypto_object.load_certificate(crypto_object.FILETYPE_PEM,
                                                    st_cert)
        timestring = certobject.get_notAfter().rstrip('Z')
        expiry_date = datetime.datetime.strptime(timestring, '%Y%m%d%H%M%S')
        expiry_date_unix = int(expiry_date.strftime("%s"))

        # Skip already expired certificates
        if expiry_date_unix <= int(time.time()):
            continue

        if check_time < crit_days:
            cn = str(certobject.get_subject()).split(
                        'CN')[1].rstrip('\'>').strip('=')
            crit_cns += cn + ' ({0}), '
        if check_time < expiry_date_unix:
            cn = str(certobject.get_subject()).split(
                        'CN')[1].rstrip('\'>').strip('=')
            warn_cns += cn + ' ({0}), '
            .format(time.strftime("%d.%m.%Y", time.localtime(int(
                expiry_date_unix))))

    if crit_cns:
        print "CRITICAL: the following certs will expire soon: {0} {1}"
        .format(crit_cns, warn_cns)
        sys.exit(2)

    if warn_cns:
        print "WARNING: the following certs will expire soon: {0}"
        .format(warn_cns)
        sys.exit(1)

    print "OK: Everything is fine"

if __name__ == '__main__':
    main(parse_args())
