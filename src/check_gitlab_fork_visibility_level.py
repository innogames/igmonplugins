#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - GitLab Fork Security Level Check

This is a Nagios script which checks, if there are any forks with a lower
visibility level than their origins. The script uses the GitLab Enterprise
Server Rest Api and it is possible to use Basic or token based authentication.
The script will exit with:
 - 0 (OK) if there are no fork projects with a lower visibility level
 - 1 (CRITICAL) if there are fork projects with a lower visibility level

Copyright (c) 2020 InnoGames GmbH
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

import math
from argparse import ArgumentParser, Namespace
from typing import Dict, List, Optional

import grequests
import requests
from requests.auth import HTTPBasicAuth, AuthBase
from requests.models import PreparedRequest

LEVEL_ORDER = {
    'public': 0,
    'internal': 1,
    'private': 2
}

PER_PAGE = 100


def parse_args():
    parser = ArgumentParser()
    parser.add_argument('base_url',
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
    parser.add_argument(
        '--api-version',
        help=('The api version in form of "v3".  If not specified the script '
              'tries to fetch current api version through the gitlab version '
              'endpoint.  Right now it will try from api version 4 down to 3.')
    )
    return parser.parse_args()


def main(args):
    # type: (Namespace) -> None
    base_url = args.base_url

    auth = parse_auth_argument(args)

    api = args.api_version
    if not api:
        api = fetch_api_version(base_url, auth=auth)

    if not api:
        print('Api version could not be found.')
        exit(3)

    fetched_projects = fetch_projects(
        base_url, api, auth=auth
    )

    def has_fork_filter(project: dict):
        if 'forks_count' not in project:
            return False

        return project['forks_count'] > 0

    projects = list(filter(has_fork_filter, fetched_projects))
    if not projects:
        print('No projects found')
        exit(3)

    project_map = {int(p['id']): p for p in projects}

    # TODO: Use this code instead of the one below after the issue in Gitlab
    #       will be fixed: https://gitlab.com/gitlab-org/gitlab-ce/issues/40090
    # critical_forks = get_critical_forks(fetched_projects, project_map)
    critical_forks = get_critical_forks(
        projects, project_map, base_url, api, auth
    )

    if not critical_forks:
        print(
            'OK: No forks with lower visibility level than their origins '
            'found.'
        )
        exit(0)

    format_string = '{project[path_with_namespace]}: {project[web_url]}'
    string = '\n'.join(
        format_string.format(project=project)
        for project in critical_forks
    )

    print(
        'CRITICAL: {amount} fork(s) found which have a lower visibility than '
        'their origins:\n{0}'
        .format(string, amount=len(critical_forks))
    )
    exit(2)


class HTTPTokenAuth(AuthBase):
    """Attaches HTTP Token Authentication to the given Request object."""

    def __init__(self, token_name, token):
        # type: (str, str) -> None
        self.token_name = token_name
        self.token = token

    def __eq__(self, other):
        return (self.token_name == getattr(other, 'token_name') and
                self.token == getattr(other, 'token'))

    def __ne__(self, other):
        return not self.__eq__(other)

    def __call__(self, request):
        # type: (PreparedRequest) -> PreparedRequest  # NOQA: 501
        request.headers[self.token_name] = self.token
        return request


def parse_auth_argument(args):
    # type: (Namespace) -> AuthBase
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


def get_critical_forks(projects, project_map, base_url, api, auth):
    # type: (List, Dict, str, str, AuthBase) -> List
    forks = []
    forks_requests = []
    for project in projects:
        if project['forks_count'] <= PER_PAGE:
            forks_requests.append(
                get_forks(base_url, api, project['id'], auth=auth)
            )
        else:
            forks.extend(
                fetch_forks(base_url, api, project['id'], auth=auth)
            )

    for response in grequests.map(forks_requests, size=20):
        forks.extend(response.json())

    mapping = []
    for fork in forks:
        project_id = fork['forked_from_project']['id']
        project = project_map[int(project_id)]
        mapping.append((fork, project))

    critical_forks = []
    for fork, project in mapping:
        project_level = LEVEL_ORDER[project['visibility']]
        fork_level = LEVEL_ORDER[fork['visibility']]
        if fork_level < project_level:
            critical_forks.append(fork)

    return critical_forks


# TODO: Use this code instead of the one below after the issue in Gitlab
#       will be fixed: https://gitlab.com/gitlab-org/gitlab-ce/issues/40090
# def get_critical_forks(projects, project_map):
#     # type: (List, Dict) -> List
#     def is_fork_filter(project: dict):
#         return 'forked_from_project' in project
#
#     forks = list(filter(is_fork_filter, projects))
#
#     mapping: Dict[int, List[Dict]] = {}
#     for fork in forks:
#         project_id = fork['forked_from_project']['id']
#         project = project_map.get(int(project_id))
#         if not project:
#             continue
#
#         if project['id'] not in mapping:
#             mapping[project['id']] = []
#
#         mapping[project['id']].append(fork)
#
#     critical_forks = []
#     for project in projects:
#         project_forks = mapping.get(project['id'], [])
#         if project['forks_count'] > len(project_forks):
#             critical_forks.append(project)
#
#     return critical_forks


def fetch_api_version(base_url, auth=None):
    # type: (str, AuthBase) -> Optional[str]
    versions = ('v3', 'v4')
    for version in reversed(versions):
        endpoint = '/api/{api}/version'.format(api=version)
        response = do_request('head', base_url, endpoint, auth=auth)

        if response.ok:
            return version

    return None


def fetch_projects(base_url, api, auth=None):
    # type: (str, str, AuthBase) -> Optional[List]
    endpoint = '/api/{api}/projects'.format(api=api)
    params = {'archived': True, 'visibility': 'private'}

    return fetch_paginatored(
        'get', base_url, endpoint, params=params, auth=auth
    )


def fetch_forks(base_url, api, project, auth=None):
    # type: (str, str, [str, int], AuthBase) -> Optional[List]
    endpoint = (
        '/api/{api}/projects/{project}/forks'
            .format(api=api, project=project)
    )

    return fetch_paginatored('get', base_url, endpoint, auth=auth)


def get_forks(base_url, api, project, auth=None):
    # type: (str, str, [str, int], AuthBase) -> grequests.AsyncRequest
    endpoint = (
        '/api/{api}/projects/{project}/forks'
            .format(api=api, project=project)
    )
    params = {'per_page': PER_PAGE}

    return get_request('get', base_url, endpoint, params=params, auth=auth)


def fetch_paginatored(method, base_url, endpoint, params=None, auth=None):
    # type: (str, str, str, dict, AuthBase) -> Optional[List]
    if params is None:
        params = {}

    params = params.copy()
    if 'per_page' not in params:
        params['per_page'] = PER_PAGE

    start = 1
    if 'page' in params:
        start = int(params['page'])

    first_params = params.copy()
    first_params['per_page'] = 1
    first_params['page'] = 1
    r = do_request(method, base_url, endpoint, first_params, auth)
    if r.status_code != 200:
        return None

    total = r.headers['X-Total']
    total = int(total) if total else 1
    total = math.ceil(total / int(params['per_page']))

    responses = []
    requests_map = []
    for page in range(start, total + 1):
        params['page'] = page
        requests_map.append(
            get_request(method, base_url, endpoint, params.copy(), auth)
        )

    responses.extend(grequests.map(requests_map))
    json_responses = []
    for response in responses:
        json_responses.extend(response.json())

    return json_responses


def get_request(method, base_url, endpoint, params=None, auth=None):
    # type: (str, str, str, dict, AuthBase) -> grequests.AsyncRequest
    if params is None:
        params = {}

    return grequests.request(
        method, base_url + endpoint, params=params, auth=auth
    )


def do_request(method, base_url, endpoint, params=None, auth=None):
    # type: (str, str, str, dict, AuthBase) -> requests.models.Response
    if params is None:
        params = {}

    return requests.request(
        method, base_url + endpoint, params=params, auth=auth
    )


if __name__ == '__main__':
    main(parse_args())
