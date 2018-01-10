#!/usr/bin/env python
#
# InnoGames Monitoring Plugins - atlassian_expiring_licenses.py
#
# This is a Nagios script which checks, if there are any plugin licenses
# which will expire soon. The script uses the Jira Server Rest Api and it is
# possible to use Basic or two-legged OAuth authentication.
# The script will exit with:
#  - 0 (OK)         if there are no soon expiring licenses
#  - 1 (WARNING)    if there are soon expiring licenses but _before_ a optional
#                   given time
#  - 2 (CRITICAL)   if there are soon expiring licenses _after_ that optional
#                   given time
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
# For OAuth authentication, lines 213-214
# pycrypto, pip install pycrypto
# requests_oauthlib, pip install requests requests_oauthlib
#

from __future__ import print_function

from argparse import ArgumentParser
from datetime import datetime, timedelta

import grequests
import requests
from requests.auth import HTTPBasicAuth
from requests.utils import quote


def parse_args():
    parser = ArgumentParser()
    parser.add_argument('base_url',
                        help='the base url of the application you want to '
                             'check (e.g. https://sub.example.com)')
    parser.add_argument('--auth', choices=('basic', 'oauth'),
                        help='authentication mode to use. basic uses '
                             'username and password. oauth uses private key '
                             '(with/out passphrase) and consumer key. '
                             'without --auth script will try an anonymous '
                             'access.'
                        )
    parser.add_argument('--username',
                        help='the username for basic authentication')
    parser.add_argument('--password',
                        help='the password for basic authentication')
    parser.add_argument('--consumer-key',
                        help='consumer key for oauth authentication')
    parser.add_argument('--consumer-secret',
                        help='consumer secret for oauth authentication')
    parser.add_argument('--private-key',
                        help='private key for oauth')
    parser.add_argument('--passphrase',
                        help='possible passphrase for the private key')
    parser.add_argument('--days', type=int, default=60,
                        help='amount of days before the license will be shown')
    parser.add_argument('--days-critical', type=int, default=14,
                        help='amount of days before the license will be shown '
                             'as critical')
    parser.add_argument('--format',
                        help='the format of the final print out. for the '
                             'format the plugin, response and expiry_delta '
                             'object will be passed')
    return parser.parse_args()


def main(args):
    base_url = args.base_url

    auth = parse_auth_argument(args)

    now = datetime.now()
    deadline = now + timedelta(args.days)
    deadline_critical = now + timedelta(args.days_critical)
    plugins = fetch_plugins(base_url, auth)
    plugins = [plugin for plugin in plugins if plugin['usesLicensing']]
    responses = zip(
        plugins,
        grequests.map(
            get_fetch_plugin_license_request(
                base_url, plugin['key'] + '-key', auth=auth)
            for plugin in plugins)
    )

    expires = []
    for plugin, response in responses:
        if not response:
            continue

        json = response.json()
        if 'maintenanceExpiryDate' not in json:
            continue

        expire_time = datetime.utcfromtimestamp(
            json['maintenanceExpiryDate'] / 1000
        )
        if not expire_time < deadline:
            continue

        expires.append((plugin, json))

    if not expires:
        print('OK: No license will expire soon')
        exit(0)

    # Sort the update list based on their expire date and name
    expires = sorted(expires,
                     key=lambda item: item[0]['name'])
    expires = sorted(expires,
                     key=lambda item: item[1]['maintenanceExpiryDate'])

    format_string = (args.format if args.format else
                     '\n[{plugin[name]}]: {time_left} left')

    exit_code = 1
    status = 'WARNING'

    string = ''
    for plugin, response in expires:
        expiry_date = datetime.utcfromtimestamp(
            response['maintenanceExpiryDate'] / 1000)

        # Check if check will be critical or "just" warning
        if exit_code == 1 and expiry_date < deadline_critical:
            status = 'CRITICAL'
            exit_code = 2

        delta = expiry_date - now
        string += format_string.format(
            plugin=plugin, response=response,
            time_left='{} days'.format(delta.days))

    header = ('{status}: {amount} soon expiring licenses found'
              .format(status=status, amount=len(expires)))
    print('{header}: {content}'.format(header=header, content=string))
    exit(exit_code)


def parse_auth_argument(args):
    auth = args.auth
    if auth == 'basic':
        if not (args.username and args.password):
            print("For basic authentication, 'username' and 'password' "
                  "parameter are needed")
            exit(3)
        auth = HTTPBasicAuth(args.username, args.password)
    elif auth == 'oauth':
        if not (args.consumer_key and args.private_key):
            print("For oauth authentication, 'consumer-key' "
                  "and 'private-key' parameter are needed")
            exit(3)
        auth = get_oauth1session(args.consumer_key, args.consumer_secret,
                                 args.private_key, args.passphrase)

    return auth


def fetch_plugins(base_url, auth=None):
    """
        :return: plugins
        :rtype: list of dict
    """
    endpoint = '/rest/plugins/1.0/'
    response = do_request('get', base_url, endpoint, auth=auth)
    if not response.ok:
        return

    return response.json()['plugins']


def fetch_plugin_license(base_url, plugin_key, auth=None):
    if not plugin_key:
        return None
    plugin_key = quote(str(plugin_key), '')
    endpoint = ('/rest/plugins/1.0/{plugin_key}/license'
                .format(plugin_key=plugin_key))
    response = do_request('get', base_url, endpoint, auth=auth)
    if not response.ok:
        return

    return response.json()


def get_fetch_plugin_license_request(base_url, plugin_key, auth=None):
    if not plugin_key:
        return None
    plugin_key = quote(str(plugin_key), '')
    endpoint = ('/rest/plugins/1.0/{plugin_key}/license'
                .format(plugin_key=plugin_key))
    return grequests.get(base_url + endpoint, auth=auth)


def do_request(method, base_url, endpoint, params={}, auth=None):
    return requests.request(method, base_url + endpoint, params=params,
                            auth=auth)


def get_oauth1session(consumer_key, consumer_secret, private_key, passphrase):
    from Crypto.PublicKey import RSA
    from requests_oauthlib import OAuth1
    with open(private_key, 'r') as fd:
        rsa_key = RSA.importKey(fd.read(), passphrase)

    return OAuth1(client_key=consumer_key, client_secret=consumer_secret,
                  signature_method='RSA-SHA1', rsa_key=rsa_key)


if __name__ == '__main__':
    main(parse_args())
