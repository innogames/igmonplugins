#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Atlassian License Seats Check

This is a Nagios script which checks, if there are enough license seats
left for the given Atlassian system.  The script uses a custom rest
endpoint made for and with the ScriptRunner plugin.

The script will exit with:
 - 0 (OK) if there are enough license seats left
 - 1 (WARNING) if the warning threshold of remaining license seats is reached
 - 2 (CRITICAL) if the critical threshold of remaining license seats is reached

Copyright (c) 2022 InnoGames GmbH
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
import sys
from argparse import ArgumentParser
from dataclasses import dataclass
from typing import NoReturn, Dict, Optional

import requests
from requests.auth import HTTPBasicAuth


# XXX: Some optional modules are imported in get_oauth1session().

def parse_args():
    parser = ArgumentParser()
    parser.add_argument(
        'base_url',
        help='the base url of the application you want to '
             'check (e.g. https://sub.example.de)'
    )
    parser.add_argument(
        '--auth', choices=('basic', 'oauth'),
        help='authentication mode to use. basic uses '
             'username and password. oauth uses private key '
             '(with/out passphrase) and consumer key. '
             'without --auth script will try an anonymous '
             'access.'
    )
    parser.add_argument(
        '--username',
        help='the username for basic authentication'
    )
    parser.add_argument(
        '--password',
        help='the password for basic authentication'
    )
    parser.add_argument(
        '--consumer-key',
        help='consumer key for oauth authentication'
    )
    parser.add_argument(
        '--consumer-secret',
        help='consumer secret for oauth authentication'
    )
    parser.add_argument('--private-key', help='private key for oauth')
    parser.add_argument(
        '--passphrase',
        help='possible passphrase for the private key'
    )
    parser.add_argument('--warn-perc-threshold', type=float)
    parser.add_argument('--crit-perc-threshold', type=float)
    return parser.parse_args()


def main(args) -> 'ExitCode':
    base_url = args.base_url

    try:
        auth = parse_auth_argument(args)
    except ValueError as e:
        return ExitCode(3, str(e))

    data = fetch_license_user_counts(base_url, auth)
    user_count, max_users = data['userCount'], data['maxUsers']
    perc = user_count / max_users * 100

    checks = {
        'critical': (args.crit_perc_threshold, 2),
        'warning': (args.warn_perc_threshold, 1),
    }

    for check, check_args in checks.items():
        threshold, exit_code = check_args
        if not threshold:
            continue
        total_threshold = max_users * threshold / 100
        if perc >= threshold:
            return ExitCode(
                exit_code, f'{user_count} of {max_users} seats are given.',
                f'Which is above the {check} threshold of {threshold:g}% '
                f'resp. {total_threshold:g} of max seats.'
            )

    return ExitCode(0, f'{user_count} of {max_users} seats are given.')


def parse_auth_argument(args):
    auth = args.auth
    if auth == 'basic':
        if not (args.username and args.password):
            raise ValueError(
                "For basic authentication, 'username' and 'password' "
                "parameter are needed"
            )
        auth = HTTPBasicAuth(args.username, args.password)
    elif auth == 'oauth':
        if not (args.consumer_key and args.private_key):
            raise ValueError(
                "For oauth authentication, 'consumer-key' "
                "and 'private-key' parameter are needed"
            )
        auth = get_oauth1session(
            args.consumer_key, args.consumer_secret,
            args.private_key, args.passphrase
        )

    return auth


def fetch_license_user_counts(base_url, auth=None) -> Dict:
    """
    Fetches the license and user count information from the atlassian system.

    Args:
        base_url (str): The base url for the atlassian system. E.g. https://jira.example.com
        auth: The authentication object passed directly to requests module to make a request.

    Returns:
        Dict: The json response as dict object.
              Example response:
                  {"maxUsers":500,"userCount":365,"remainingSeats":135}
    """
    endpoint = '/rest/scriptrunner/latest/custom/getLicenseSeatCount'

    response = do_request('get', base_url, endpoint, auth=auth)
    response.raise_for_status()

    return response.json()


def do_request(method, base_url, endpoint, params=None, auth=None):
    if params is None:
        params = {}

    return requests.request(
        method, base_url + endpoint, auth=auth,
        params=params
    )


def get_oauth1session(consumer_key, consumer_secret, private_key, passphrase):
    from Crypto.PublicKey import RSA
    from requests_oauthlib import OAuth1
    with open(private_key, 'r') as fd:
        rsa_key = RSA.importKey(fd.read(), passphrase)

    return OAuth1(
        client_key=consumer_key, client_secret=consumer_secret,
        signature_method='RSA-SHA1', rsa_key=rsa_key
    )


@dataclass
class ExitCode:
    code: int
    summary: str
    description: Optional[str] = None

    def print(self) -> None:
        print(self._get_code_prefix() + self.summary)
        if self.description:
            print()
            print(self.description)

    def _get_code_prefix(self):
        code_prefixes = {
            0: 'OK: ',
            1: 'WARNING: ',
            2: 'CRITICAL: ',
            3: 'UNKNOWN: ',
        }
        return code_prefixes[self.code]

    def exit(self) -> NoReturn:
        sys.exit(self.code)

    def print_and_exit(self) -> NoReturn:
        self.print()
        self.exit()


if __name__ == '__main__':
    main(parse_args()).print_and_exit()
