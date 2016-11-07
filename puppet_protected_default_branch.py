#!/usr/bin/env python
#
# InnoGames Monitoring Plugins - puppet_protected_default_branch
#
# This is a Nagios script which checks, if there are any puppet projects with
# unprotected default branches (mostly master branches). The branches must be
# strictly protected, means that no developer must not be allowed to push or
# merge into the branch. The script uses the GitLab Server Rest Api and it is
# possible to use Basic or token based authentication.
# The script will exit with:
#  - 0 (OK) if there are no projects with unprotected default branches
#  - 1 (WARNING) if there are projects with unprotected default branches
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

import grequests as grequests
import requests
from requests.auth import HTTPBasicAuth, AuthBase


def parse_args():
    parser = ArgumentParser()
    parser.add_argument('--base-url',
                        help='the base url of the application you want to '
                             'check (e.g. https://sub.example.com)')
    parser.add_argument('--auth', choices=('basic', 'token'),
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
    parser.add_argument('--token',
                        help='the private/access token with which the script '
                             'can authenticate as the user behind the token')
    parser.add_argument('--format',
                        help='the format of the final print out. for the '
                             'format the repository object will be passed')
    parser.add_argument('--branch', default='master',
                        help='the branch which should be protected')
    parser.add_argument('--protect', action='store_true',
                        help='if found unprotected master branches should be '
                             'automatically be protected')
    return parser.parse_args()


def main(args):
    base_url = args.base_url

    auth = parse_auth_argument(args)

    projects = fetch_projects(base_url, 'puppet', auth=auth)
    puppet_projects = [
        project for project in projects
        if project['namespace']['name'] == 'puppet'
        ]

    if not puppet_projects:
        print('No puppet projects found')
        exit(3)

    master_branches = zip(
        puppet_projects,
        grequests.map((get_branch_request(base_url, project['id'],
                                          project['default_branch'], auth=auth)
                       for project in puppet_projects
                       if project['default_branch'] is not None),
                      size=2)
    )

    unprotected_masters = [
        (project, branch.json()) for project, branch in master_branches
        if branch.status_code != 200 or
        (
            not branch.json()['protected'] or
            branch.json()['developers_can_merge'] or
            branch.json()['developers_can_push']
        )
        ]

    if not unprotected_masters:
        print('OK: No projects with default branches found.')
        exit(0)

    if args.format:
        format_string = args.format
    else:
        format_string = '{project[path_with_namespace]}: {project[web_url]}\n'

    string = ''.join(format_string.format(project=project, branch=branch)
                     for project, branch in unprotected_masters)
    print('WARNING: '
          '{amount} projects with unprotected default branches found\n{0}'
          .format(string, amount=len(unprotected_masters)))
    exit(1)


class HTTPTokenAuth(AuthBase):
    """Attaches HTTP Token Authentication to the given Request object."""

    def __init__(self, token_name, token):
        self.token_name = token_name
        self.token = token

    def __eq__(self, other):
        return all([
            self.token_name == getattr(other, 'token_name', None),
            self.token == getattr(other, 'token', None)
        ])

    def __ne__(self, other):
        return not self == other

    def __call__(self, r):
        r.headers[self.token_name] = self.token
        return r


def parse_auth_argument(args):
    auth = args.auth
    if auth == 'basic':
        if not (args.username and args.password):
            print("For basic authentication, 'username' and 'password' "
                  "parameter are needed")
            exit(3)
        auth = HTTPBasicAuth(args.username, args.password)
    elif auth == 'token':
        if not args.token:
            print("For token authentication, 'token' parameter is needed")
            exit(3)
        auth = HTTPTokenAuth('PRIVATE-TOKEN', args.token)

    return auth


def fetch_projects(base_url, search=None, auth=None):
    """
        :return: repositories
        :rtype: list of dict
    """
    endpoint = '/api/v3/projects/all'
    params = {}
    if search:
        params['search'] = search
    response = do_request('get', base_url, endpoint, params=params,
                          auth=auth)
    response = json.loads(response.text)
    for project in response:
        yield project


def get_branch_request(base_url, project, branch='master', auth=None):
    endpoint = ('/api/v3/projects/{project}/repository/branches/{branch}'
                .format(project=project, branch=branch))
    return get_request('get', base_url, endpoint, params={}, auth=auth)


def get_request(method, base_url, endpoint, params={}, auth=None):
    return grequests.request(method, base_url + endpoint, params=params,
                             auth=auth)


def do_request(method, base_url, endpoint, params={}, auth=None):
    return requests.request(method, base_url + endpoint, params=params,
                            auth=auth)


if __name__ == '__main__':
    main(parse_args())
