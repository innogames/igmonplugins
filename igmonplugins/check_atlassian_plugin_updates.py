#!/usr/bin/env python
"""InnoGames Monitoring Plugins - Atlassian Plugin Updates Check

This is a Nagios script which checks, if there are any updates for plugins
for a Jira system.  The script uses the Jira Server and Atlassian
Marketplace Rest API and it is possible to use Basic or two-legged OAuth
authentication for the Jira Server.

The script will exit with:
 - 0 (OK) if there are no updates for plugins
 - 1 (WARNING) if there are updates for plugins

Copyright (c) 2016 InnoGames GmbH
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

from argparse import ArgumentParser

import grequests
import requests
from requests.auth import HTTPBasicAuth
from requests.utils import quote
# XXX: Some optional modules are imported in get_oauth1session().

ATLASSIAN_MARKETPLACE_BASE_URL = 'https://marketplace.atlassian.com'


def parse_args():
    parser = ArgumentParser()
    parser.add_argument('base_url',
                        help='the base url of the application you want to '
                             'check (e.g. https://sub.example.de)')
    parser.add_argument('--auth', choices=('basic', 'oauth'),
                        help='authentication mode to use. basic uses '
                             'username and password. oauth uses private key '
                             '(with/out passphrase) and consumer key. '
                             'without --auth script will try an anonymous '
                             'access.')
    parser.add_argument('--username',
                        help='the username for basic authentication')
    parser.add_argument('--password',
                        help='the password for basic authentication')
    parser.add_argument('--consumer-key',
                        help='consumer key for oauth authentication')
    parser.add_argument('--consumer-secret',
                        help='consumer secret for oauth authentication')
    parser.add_argument('--private-key', help='private key for oauth')
    parser.add_argument('--passphrase',
                        help='possible passphrase for the private key')
    parser.add_argument('--format',
                        help='the format of the final print out. for the '
                             'format the plugin and update object will be '
                             'passed')
    return parser.parse_args()


def main(args):
    base_url = args.base_url

    auth = parse_auth_argument(args)

    plugins = fetch_plugins(base_url, auth)
    plugins = [plugin for plugin in plugins if plugin['userInstalled']]

    # right now the script is just for jira application
    application = 'jira'
    build_number = fetch_server_info(base_url, auth)['buildNumber']

    marketplace_requests = [
        get_fetch_plugin_versions_request(
            ATLASSIAN_MARKETPLACE_BASE_URL, plugin['key'],
            {'afterVersion': plugin['version'], 'application': application,
             'applicationBuild': build_number}
        )
        for plugin in plugins
    ]
    responses = zip(plugins, grequests.map(marketplace_requests))

    updates = [
        (plugin, response.json())
        for plugin, response in responses
        if response and response.status_code == 200 and
        response.json()['_embedded']['versions']
    ]

    if not updates:
        print('OK: No updates for plugins found')
        exit(0)

    format_string = (args.format if args.format else
                     '\n[{plugin[name]}]: '
                     '{plugin[version]} --> '
                     '{update[_embedded][versions][0][name]}')

    string = ''.join(format_string.format(plugin=plugin, update=update)
                     for plugin, update in updates)
    print('WARNING: {amount} updates for plugins found: {0}'
          .format(string, amount=len(updates)))
    exit(1)


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


def fetch_server_info(base_url, auth=None):
    """
        :return: server info
        :rtype: dict
    """
    endpoint = '/rest/api/2/serverInfo'
    response = do_request('get', base_url, endpoint, auth=auth)
    return response.json()


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


def get_fetch_plugins_request(base_url, auth=None):
    endpoint = '/rest/plugins/1.0/'
    return grequests.get(base_url + endpoint, auth=auth)


def fetch_plugin_versions(base_url, plugin_key, params={}):
    if not plugin_key:
        return
    plugin_key = quote(str(plugin_key), '')
    endpoint = ('/rest/2/addons/{plugin_key}/versions'
                .format(plugin_key=plugin_key))
    response = do_request('get', base_url, endpoint, params)
    if not response.ok:
        return

    return response.json()['_embedded']['versions']


def get_fetch_plugin_versions_request(base_url, plugin_key, params={}):
    if not plugin_key:
        return
    plugin_key = quote(str(plugin_key), '')
    endpoint = ('/rest/2/addons/{plugin_key}/versions'
                .format(plugin_key=plugin_key))
    return grequests.get(base_url + endpoint, params=params)


def do_request(method, base_url, endpoint, params={}, auth=None):
    return requests.request(method, base_url + endpoint, auth=auth,
                            params=params)


def get_oauth1session(consumer_key, consumer_secret, private_key, passphrase):
    from Crypto.PublicKey import RSA
    from requests_oauthlib import OAuth1
    with open(private_key, 'r') as fd:
        rsa_key = RSA.importKey(fd.read(), passphrase)

    return OAuth1(client_key=consumer_key, client_secret=consumer_secret,
                  signature_method='RSA-SHA1', rsa_key=rsa_key)


if __name__ == '__main__':
    main(parse_args())
