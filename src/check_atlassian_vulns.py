#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Atlassian Vulnerable Version Checker

It is expected to use this check with a newer version
than the currently running one.
Recommended patch version +1.

Reason: Atlassian is not always listing all vulnerabilities
which affect the supplied version, however the future version
can be queried for implemented fixes.

Copyright (c) 2024 InnoGames GmbH
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
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OFi MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
import argparse
import sys

import requests


def parse_args() -> argparse.Namespace:
    """
    Parse the arguments passed to the script.

    :return:
    """
    parser = argparse.ArgumentParser(description='Parse product and version.')
    parser.add_argument('--product', required=True, type=str,
                        help='Product name.')
    parser.add_argument('--version', required=True, type=str,
                        help='Product version.')
    return parser.parse_args()


def get_vulnerabilities(product: str, version: str) -> str:
    """
    Fetch vulnerabilities from Atlassian Security API.

    :param product: Atlassian Product String
    :param version:
    :return:
    """
    base_url = 'https://api.atlassian.com/vuln-transparency/v1/products'
    url = f'{base_url}?products={product}&version={version}'
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            print('Atlassian API gave unexpected response')
            sys.exit(3)
    except requests.exceptions.Timeout:
        print('Atlassian API request timed out')
        sys.exit(3)


def parse_vulnerabilities(vulnerabilities: str, product: str, version: str) \
        -> None:
    """
    Parse the vulns fetched from Atlassian Security API by known schema.

    :param vulnerabilities: Atlassian API response
    :param product: Atlassian Product string
    :param version:
    """
    version_vulns = []
    if not vulnerabilities['products']:
        print('No new patch version available')
        sys.exit(0)
    for vulnerability in vulnerabilities['products'][product]['versions'][
            version]:
        version_vulns.append(next(iter(vulnerability)))
    if version_vulns:
        print(
            f'Newer version {version} of {product} '
            f'has the fixes for the following CVEs: {version_vulns}')
        sys.exit(1)
    else:
        print('No newer version with fixes detected')
        sys.exit(0)


def main():
    args = parse_args()
    product = args.product
    version = args.version
    parse_vulnerabilities(get_vulnerabilities(product, version), product,
                          version)


if __name__ == '__main__':
    main()

