#!/usr/bin/env python
#
# InnoGames Monitoring Plugins - gitlab_protected_branch
#
# This is a Nagios script which checks, if there are any projects with
# unprotected branches (mostly master branches). The branches must be
# strictly protected, means that developers must not be allowed to push or
# merge into the branch. The script uses the GitLab Enterprise Server Rest Api
# and it is possible to use Basic or token based authentication.
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
from requests.utils import quote


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
                             'format the project and branch json object will '
                             'be passed')
    parser.add_argument('--group',
                        help='the group with all the projects to monitor')
    parser.add_argument('--project',
                        help='either a full path to one specific project '
                             'or a search criteria to find projects '
                             'which shall be monitored')
    parser.add_argument('--branch',
                        help='the branch which should be protected, '
                             'default is the default branch of the project')
    parser.add_argument(
        '--api-version',
        help=('The api version in form of "v3".  If not specified the script '
              'tries to fetch current api version through the gitlab version '
              'endpoint.  Right now it will try from api version 4 down to 3.')
    )
    return parser.parse_args()


def main(args):
    base_url = args.base_url

    auth = parse_auth_argument(args)

    api = args.api_version
    if not api:
        api = fetch_api_version(base_url, auth=auth)

    if not api:
        print('Api version could not be found.')
        exit(3)

    if args.group:
        projects = fetch_group_projects(base_url, args.group, args.project,
                                        auth=auth)
    elif (args.project and
          # if args.project represents an int or is like 'group/project'
          ('/' in args.project or str(int(args.project)) == args.project)):
        projects = [fetch_project(base_url, args.project, auth=auth)]
    else:
        projects = fetch_projects(base_url, args.project, auth=auth)

    if not projects:
        print('No projects found')
        exit(3)

    if not args.branch:
        projects = [
            project for project in projects
            if project['default_branch'] is not None
        ]

    # create array of requests for all the branches
    branch_requests = []
    for project in projects:
        branch = args.branch or project['default_branch']
        if not branch:
            continue
        branch_requests.append(get_branch_request(
            base_url, project['id'], branch, auth=auth))

    # map the branch responses with their project
    branches = zip(
        projects,
        (
            branch.json() if branch and branch.status_code == 200
            else None
            for branch in grequests.map(branch_requests, size=2)
        )
    )

    # collect all unprotected branches
    unprotected_branches = [
        (project, branch) for project, branch in branches
        if branch and
        (
            not branch['protected'] or
            branch['developers_can_merge'] or
            branch['developers_can_push']
        )
    ]

    if not unprotected_branches:
        print('OK: No projects with unprotected branches found.')
        exit(0)

    format_string = (args.format if args.format else
                     '\n{project[path_with_namespace]}: {project[web_url]}')

    string = ''.join(format_string.format(project=project, branch=branch)
                     for project, branch in unprotected_branches)
    print('WARNING: {amount} projects with unprotected branches found: {0}'
          .format(string, amount=len(unprotected_branches)))
    exit(1)


class HTTPTokenAuth(AuthBase):
    """Attaches HTTP Token Authentication to the given Request object."""

    def __init__(self, token_name, token):
        self.token_name = token_name
        self.token = token

    def __eq__(self, other):
        return (self.token_name == getattr(other, 'token_name') and
                self.token == getattr(other, 'token'))

    def __ne__(self, other):
        return not self.__eq__(other)

    def __call__(self, request):
        request.headers[self.token_name] = self.token
        return request


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


def fetch_api_version(base_url, auth=None):
    versions = ('v3', 'v4')
    for version in reversed(versions):
        endpoint = '/api/{api}/version'.format(api=version)
        response = do_request('head', base_url, endpoint, auth=auth)

        if response.ok:
            return version

    return None


def fetch_project(base_url, project, auth=None):
    """
        :return: project
        :rtype: dict
    """
    if not project:
        return None
    project = quote(str(project), '')
    endpoint = ('/api/v3/projects/{project}'
                .format(project=project))
    response = do_request('get', base_url, endpoint, auth=auth)
    if response.status_code != 200:
        return None

    response = json.loads(response.text)
    return response


def fetch_projects(base_url, search=None, auth=None):
    """
        :return: projects
        :rtype: list of dict
    """
    endpoint = '/api/v3/projects'
    params = {}
    if search:
        params['search'] = search
    response = do_request('get', base_url, endpoint, params=params, auth=auth)
    if response.status_code != 200:
        return None

    response = json.loads(response.text)
    return response


def fetch_group_projects(base_url, group, project=None, auth=None):
    """
        :return: projects
        :rtype: list of dict
    """
    if not group:
        return None
    group = quote(str(group), '')
    endpoint = ('/api/v3/groups/{group}/projects'
                .format(group=group))
    params = {}
    if project:
        params['search'] = project
    response = do_request('get', base_url, endpoint, params=params, auth=auth)
    if response.status_code != 200:
        return None

    response = json.loads(response.text)
    return response


def get_branch_request(base_url, project, branch, auth=None):
    if not project or not branch:
        return None
    project = quote(str(project), '')
    branch = quote(str(branch), '')
    endpoint = ('/api/v3/projects/{project}/repository/branches/{branch}'
                .format(project=project, branch=branch))
    return get_request('get', base_url, endpoint, auth=auth)


def get_request(method, base_url, endpoint, params={}, auth=None):
    return grequests.request(method, base_url + endpoint, params=params,
                             auth=auth)


def do_request(method, base_url, endpoint, params={}, auth=None):
    return requests.request(method, base_url + endpoint, params=params,
                            auth=auth)


if __name__ == '__main__':
    main(parse_args())
