#!/usr/bin/env python
#
# InnoGames Monitoring Plugins - atlassian_expiring_licenses.py
#
# This is a Nagios script which checks, if the authentication to a specific
# url is possible or not. Supported authentication checks are: anonymous,
# basic, oauth, header (e.g. token) and form authentication. Two Factor
# Authentication is supported too by passing your TOTP Secret Key with the
# parameter `totp`. Every single occurrence of `{totp}` in the header and input
# values will be replaced with the actual generated TOTP value. However right
# now it will just works with one single request.
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
# For OAuth authentication, lines 209-210 todo:
# pycrypto, pip install pycrypto
# requests_oauthlib, pip install requests requests_oauthlib
#
# For Two Factor Authentication, line 115 todo:
# pyotp, pip install pyotp
#

from argparse import ArgumentParser, RawTextHelpFormatter

import requests
from requests.auth import HTTPBasicAuth


def parse_args():
    parser = ArgumentParser(formatter_class=RawTextHelpFormatter)
    parser.add_argument('url',
                        help='The base url of the application you want to '
                             'check (e.g. https://sub.example.com)')
    parser.add_argument('-m', '--method', default='get',
                        help='The http method to use e.g. get, post, etc.')
    parser.add_argument('-a', '--auth',
                        choices=('basic', 'oauth', 'header', 'form'),
                        help='The auth method to use, you can choose between '
                             'basic, oauth, header and form authentication. '
                             'If nothing is passed it will try an anonymous '
                             'request.')
    # Basic Auth
    # Form Auth
    # Header Auth
    # OAuth
    parser.add_argument('--inputs', nargs='*',
                        help='The inputs for the authentication. '
                             'Have to be an even amount of parameters.''''
* Basic:
    username
    password
* OAuth:
    consumer-key
    consumer-secret (optional)
    private-key
    passphrase (optional)
* Form/Header
    several different key value pairs''')
    # More Headers
    parser.add_argument('--headers', nargs='*',
                        help='The headers which shall be applied besides of '
                             'the authentication inputs.')
    # Two Factor Authentication
    parser.add_argument('--totp',
                        help='The secret key for the '
                             'Two-Factor-Authentication.')
    # Formats
    parser.add_argument('--format',
                        help='The format which will be used if the request '
                             'was successful. the response as `response` and '
                             'all arguments as `args` will be passed in.')
    parser.add_argument('--format-fail',
                        help='The format which will be used if the request '
                             'was not successful due to authentication '
                             'failure. The response as `response` and all '
                             'arguments as `args` will be passed in.')
    parser.add_argument('--format-error',
                        help='The format which will be used if the request '
                             'was not successful due to some other errors. '
                             'All arguments as `args` and the raised error as '
                             '`error` will be passed in.')
    return parser.parse_args()


def main():
    args = parse_args()

    totp = ''
    if args.totp:
        totp = get_new_totp(args.totp)

    try:
        inputs = collect_pair_values(args.inputs)
    except ValueError:
        print("The parameter 'inputs' needs an even amount of elements")
        raise SystemExit(3)

    inputs = insert_totp_token(inputs, totp)

    try:
        auth = parse_auth_argument(args.auth, inputs)
    except ValueError as e:
        print(e)
        raise SystemExit(3)

    try:
        headers = collect_pair_values(args.headers)
    except ValueError:
        print("The parameter 'headers' needs an even amount of elements")
        raise SystemExit(3)

    headers = insert_totp_token(headers, totp)

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
        raise SystemExit(2)

    if response.ok:
        print(format_success.format(response=response, args=args))
        raise SystemExit(0)

    print(format_fail.format(response=response, args=args))
    raise SystemExit(2)


def parse_auth_argument(auth_type, inputs):
    auth = None

    if not auth_type:
        auth = None
    elif auth_type == 'basic':
        if not (inputs['username'] and inputs['password']):
            raise ValueError("For basic authentication, the values for "
                             "'username' and 'password' are needed "
                             "in the inputs parameter")
        auth = HTTPBasicAuth(inputs['username'], inputs['password'])

    elif auth_type == 'header':
        if not inputs:
            raise ValueError("For header authentication the 'inputs' "
                             "parameter is needed")
        auth = HTTPHeaderAuth(inputs)

    elif auth_type == 'oauth':
        if not (inputs['consumer_key'] and inputs['args.private_key']):
            raise ValueError("For oauth authentication, the values "
                             "'consumer-key' and 'private-key' are needed "
                             "in the inputs parameter")
        auth = create_oauth1(
            inputs['consumer_key'], inputs['args.consumer_secret'],
            inputs['private_key'], inputs['passphrase']
        )

    elif auth_type == 'form':
        auth = HTTPFormAuth(inputs)

    return auth


def create_oauth1(consumer_key, consumer_secret, private_key, passphrase):
    from Crypto.PublicKey import RSA
    from requests_oauthlib import OAuth1
    with open(private_key, 'rb') as fd:
        rsa_key = RSA.importKey(fd.read(), passphrase)

    return OAuth1(client_key=consumer_key, client_secret=consumer_secret,
                  signature_method='RSA-SHA1', rsa_key=rsa_key)


def get_new_totp(totp):
    import pyotp
    return pyotp.TOTP(totp).now()


def insert_totp_token(values, totp):
    return {key: value.format(totp=totp) for key, value in values}


def collect_pair_values(values):
    if not values:
        return {}

    if len(values) % 2 != 0:
        raise ValueError("An even amount of elements are needed.")

    return zip(values[0::2], values[1::2])


class HTTPHeaderAuth(requests.auth.AuthBase):
    """Attaches HTTP Header Authentication to the given Request object."""

    def __init__(self, headers):
        super(requests.auth.AuthBase, self).__init__()
        self.headers = headers

    def __eq__(self, other):
        return self.headers == getattr(other, 'headers')

    def __ne__(self, other):
        return not self.__eq__(other)

    def __call__(self, request):
        """
        :param requests.models.PreparedRequest request:
        """
        if not self.headers:
            return request

        # for name, value in self.headers.items():
        #     request.headers[name] = value
        request.headers.update(self.headers)

        return request


class HTTPFormAuth(requests.auth.AuthBase):
    """Attaches HTTP Token Authentication to the given Request object."""

    def __init__(self, inputs):
        """
        :param dict inputs:
        """
        super(requests.auth.AuthBase, self).__init__()
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
    main()
