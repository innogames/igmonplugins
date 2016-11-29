#!/usr/bin/env python
#
# InnoGames Monitoring Plugins - atlassian_expiring_licenses.py
#
# This is a Nagios script which checks, if the authentication to a specific
# url is possible or not. Supported authentication checks are: basic, oauth,
# header (e.g. token) and form authentication. Two Factor Authentication is
# supported too by passing your TOTP Secret Key with the parameter `totp`.
# Every single occurrence of `<totp>` in the header and input values will be
# replaced with the actual generated TOTP value.
#
# The script will exit with:
#  - 0 (OK)         if authentication request returns a http status code
#                   without error (means not 400 or above)
#  - 2 (CRITICAL)   if authentication request fails either because of the
#                   request or the authentication
#
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
#

# Needed modules which are imported below
#
# For OAuth authentication, lines 188-189 todo:
# pycrypto, pip install pycrypto
# requests_oauthlib, pip install requests requests_oauthlib
#
# For Two Factor Authentication, line 97 todo:
# pyotp, pip install pyotp
#

from __future__ import print_function

import sys
from argparse import ArgumentParser

import requests
from requests.auth import HTTPBasicAuth


def parse_args():
    parser = ArgumentParser()
    parser.add_argument('url',
                        help='the base url of the application you want to '
                             'check (e.g. https://sub.example.com)')
    parser.add_argument('-m', '--method', default='get',
                        help='')
    parser.add_argument('-a', '--auth',
                        choices=('none', 'basic', 'oauth', 'header', 'form'),
                        default='none',
                        help='')
    # Basic
    parser.add_argument('-u', '--username',
                        help='the username for basic authentication')
    parser.add_argument('-p', '--password',
                        help='the password for basic authentication')
    # Header
    parser.add_argument('--headers', nargs='*',
                        help='the header name for the header authentication')
    # OAuth
    parser.add_argument('--consumer-key',
                        help='consumer key for oauth authentication')
    parser.add_argument('--consumer-secret',
                        help='consumer secret for oauth authentication')
    parser.add_argument('--private-key',
                        help='private key for oauth')
    parser.add_argument('--passphrase',
                        help='possible passphrase for the private key')
    # Form
    parser.add_argument('--inputs', nargs='*',
                        help='the input names for the form authentication')
    # 2FA
    parser.add_argument('--totp',
                        help='the secret key for the two factor authentication')
    # Formats
    parser.add_argument('--format',
                        help='the format which will be used if the request '
                             'was successful')
    parser.add_argument('--format-fail',
                        help='the format which will be used if the request '
                             'was not successful due to authentication failure')
    parser.add_argument('--format-error',
                        help='the format which will be used if the request '
                             'was not successful due to some other errors')
    return parser.parse_args()


def main(args):
    if args.totp:
        import pyotp
        args.totp = pyotp.TOTP(args.totp).now()

    auth = parse_auth_argument(args)

    headers = {}
    if args.headers:
        if len(args.headers) % 2 != 0:
            print("The parameter 'headers' needs an even amount of "
                  "elements")
            sys.exit(3)

        for name, value in zip(args.headers[0::2], args.headers[1::2]):
            if '<totp>' in value:
                value = value.replace('<totp>', args.totp)
            headers[name] = value

    format_success = (args.format or
                      'OK: Authentication was successful | '
                      '{response.url} ; {response.status_code}')
    format_fail = (args.format_fail or
                   'CRITICAL: Authentication failed | '
                   '{response.url} ; {response.status_code}\n'
                   '{response.text}')
    format_error = (args.format_error or
                    'CRITICAL: Authentication failed | '
                    '{args.url}\n'
                    '{error}')

    try:
        response = requests.request(args.method, args.url,
                                    headers=headers, auth=auth)
    except requests.RequestException as error:
        print(format_error.format(error=error, args=args))
        sys.exit(2)

    if response.ok:
        print(format_success.format(response=response, args=args))
        sys.exit(0)

    print(format_fail.format(response=response, args=args))
    sys.exit(2)


def parse_auth_argument(args):
    auth = args.auth
    if not auth or auth == 'none':
        return None

    if auth == 'basic':
        if not (args.username and args.password):
            print("For basic authentication, 'username' and 'password' "
                  "parameter are needed")
            sys.exit(3)
        auth = HTTPBasicAuth(args.username, args.password)
    elif auth == 'header':
        if not args.headers:
            print("For header authentication the 'headers' parameter is needed")
            sys.exit(3)

        if len(args.headers) % 2 != 0:
            print(
                "The parameter 'headers' needs an even amount of elements")
            sys.exit(3)
        auth = None
    elif auth == 'oauth':
        if not (args.consumer_key and args.private_key):
            print("For oauth authentication, 'consumer-key' "
                  "and 'private-key' parameter are needed")
            sys.exit(3)
        auth = create_oauth1(args.consumer_key, args.consumer_secret,
                             args.private_key, args.passphrase)
    elif auth == 'form':
        if not args.inputs:
            print("For form authentication, 'inputs' and 'values' "
                  "parameter are needed")
            sys.exit(3)

        if len(args.inputs) % 2 != 0:
            print("The parameter 'inputs' needs an even amount of elements")
            sys.exit(3)

        form = {}
        for name, value in zip(args.inputs[0::2], args.inputs[1::2]):
            if '<totp>' in value:
                value = value.replace('<totp>', args.totp)
            form[name] = value

        auth = HTTPFormAuth(form)

    return auth


def create_oauth1(consumer_key, consumer_secret, private_key, passphrase):
    from Crypto.PublicKey import RSA
    from requests_oauthlib import OAuth1
    with open(private_key, 'rb') as fd:
        rsa_key = RSA.importKey(fd.read(), passphrase)

    return OAuth1(client_key=consumer_key, client_secret=consumer_secret,
                  signature_method='RSA-SHA1', rsa_key=rsa_key)


class HTTPFormAuth(requests.auth.AuthBase):
    """Attaches HTTP Token Authentication to the given Request object."""

    def __init__(self, inputs):
        """
        :param dict inputs:
        """
        self.inputs = inputs

    def __eq__(self, other):
        return self.inputs == getattr(other, 'inputs')

    def __ne__(self, other):
        return not self.__eq__(other)

    def __call__(self, request):
        """
        :param requests.models.PreparedRequest request:
        """
        request.prepare_body(self.inputs, None)
        return request


if __name__ == '__main__':
    main(parse_args())
