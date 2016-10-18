#!/usr/bin/env python
#
# InnoGames Monitoring Plugins - bitbucket_private_repository.py
#
# This is a Nagios script which checks, if there are any private repositories
# in a Bitbucket system which are not forks. The script uses the Bitbucket
# Server Rest Api and it is possible to use Basic or two-legged OAuth
# authentication.
# The script will exit with:
#  - 0 (OK) if there are no private (none fork) repositories
#  - 1 (WARNING) if there are private (none fork) repositories
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
# For OAuth authentication, lines 150-151
# pycrypto, pip install pycrypto
# requests_oauthlib, pip install requests requests_oauthlib
#

from __future__ import print_function

import json
from argparse import ArgumentParser

import requests
from requests.auth import HTTPBasicAuth


def parse_args():
    parser = ArgumentParser()
    parser.add_argument('--base-url', dest='base_url',
                        help='the base url of the application you want to '
                             'check (e.g. https://sub.example.com)')
    parser.add_argument('--auth', dest='auth', choices=['basic', 'oauth'],
                        help=('authentication mode to use. basic uses '
                              'username and password. oauth uses private key '
                              '(with/out passphrase) and consumer key. '
                              'without --auth script will try an anonymous '
                              'access.')
                        )
    parser.add_argument('--username', dest='username',
                        help='the username for basic authentication')
    parser.add_argument('--password', dest='password',
                        help='the password for basic authentication')
    parser.add_argument('--consumer-key', dest='consumer_key',
                        help="consumer key for oauth authentication")
    parser.add_argument('--consumer_secret', dest='consumer_secret',
                        help="consumer secret for oauth authentication")
    parser.add_argument('--private-key', dest='private_key',
                        help="private key for oauth")
    parser.add_argument('--passphrase', dest='passphrase',
                        help="possible passphrase for the private key")
    parser.add_argument('--format', dest='format',
                        help=("the format of the final print out. for the "
                              "format the repository object will be passed"))
    parser.add_argument('--delete', dest='delete', action="store_true",
                        help="if found repositories should be deleted")
    return parser.parse_args()


def main(args):
    base_url = args.base_url

    auth = parse_auth_argument(args)

    repositories = fetch_repositories(base_url, auth)
    private_repos = []
    for repository in repositories:
        if 'origin' in repository:
            continue

        if not repository['project']['type'] == 'PERSONAL':
            continue

        private_repos.append(repository)
        # print(json.dumps(repository))

    if not private_repos:
        # no private repos were found
        print('OK: No private repositories found.')
        exit(0)

    if args.format:
        format_string = args.format
    else:
        format_string = ('{repo[project][owner][name]}: {repo[name]} '
                         '({repo[links][self][0][href]})\n')
    string = ''
    for repository in private_repos:
        string += format_string.format(repo=repository)
    # private repos were found
    print('WARNING: {amount} private repositories found:\n{0}'
          .format(string, amount=len(private_repos)))
    exit(2)


def parse_auth_argument(args):
    auth = args.auth
    if auth == 'basic':
        if not (args.username and args.password):
            print(('For basic authentication, \'username\' and \'password\' '
                   'parameter are needed'))
            exit(3)
        auth = HTTPBasicAuth(args.username, args.password)
    elif auth == 'oauth':
        if not (args.consumer_key and args.private_key):
            print(('For oauth authentication, \'consumer-key\' '
                   'and \'private-key\' parameter are needed'))
            exit(3)
        auth = get_oauth1session(args.consumer_key, args.consumer_secret,
                                 args.private_key, args.passphrase)

    return auth


def fetch_repositories(base_url, auth=None):
    """
        :return: repositories
        :rtype: list of dict
    """
    endpoint = '/rest/api/1.0/repos'
    limit = 1000
    start = 0
    params = {'limit': limit, 'start': start}
    repositories = []
    last_page = False
    while not last_page:
        response = do_request('get', base_url, endpoint, params=params,
                              auth=auth)
        response = json.loads(response.text)
        repositories.extend(response['values'])
        params['start'] += limit
        last_page = response['isLastPage']
    return repositories


def do_request(method, base_url, endpoint, params={}, auth=None):
    return requests.request(method, base_url + endpoint, auth=auth,
                            params=params)


def get_oauth1session(consumer_key, consumer_secret, private_key,
                      passphrase):
    from Crypto.PublicKey import RSA
    from requests_oauthlib import OAuth1
    f = open(private_key, 'r')
    rsa_key = RSA.importKey(f.read(), passphrase)

    return OAuth1(client_key=consumer_key, client_secret=consumer_secret,
                  signature_method='RSA-SHA1', rsa_key=rsa_key)


if __name__ == "__main__":
    main(parse_args())
