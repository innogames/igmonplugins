#!/usr/bin/env python3
#
# Nagios API reachability check
#
# This is a Nagios check if the APIs needed by the servers
# are reachable and returning proper statuses.
# It checks only HTTPS.
# Default accepted HTTP codes: 1xx, 2xx, 3xx
#
# Returns
#
# * Critical when at least one URL is unreachable or returns
# an unexpected status code
#
# Copyright (c) 2019 InnoGames GmbH
#

from argparse import ArgumentParser
from urllib3 import PoolManager
from urllib3.exceptions import (
    HTTPError,
    MaxRetryError,
    NewConnectionError,
    TimeoutError,
)


class ExitCodes:
    ok = 0
    warning = 1
    critical = 2
    unknown = 3


def parse_args():
    parser = ArgumentParser()
    parser.add_argument(
        'url_list',
        metavar='URL',
        type=str,
        nargs='+'
    )
    parser.add_argument(
        '--code',
        dest='codes_list',
        type=int,
        action='append',
        default=None
    )
    parser.add_argument(
        '--http_method',
        dest='http_method',
        type=str,
        default='HEAD'
    )
    parser.add_argument(
        '--allow-redirects',
        dest='allow_redirects',
        action='store_true',
    )

    return parser.parse_args()


def build_plugin_output(unreachable_urls):
    if len(unreachable_urls) == 0:
        output = 'All URLs are OK.'
        exit_code = ExitCodes.ok
    else:
        output_list = (['{url} - {error}'.format(**domain)
                        for domain in unreachable_urls])
        output = '{} URLs with problem. {}'.format(
            len(output_list),
            '; '.join(output_list),
        )
        exit_code = ExitCodes.critical
    return exit_code, output


def print_nagios_message(code, output):
    if code == ExitCodes.ok:
        state_text = 'OK'
    elif code == ExitCodes.warning:
        state_text = 'WARNING'
    elif code == ExitCodes.critical:
        state_text = 'CRITICAL'
    else:
        state_text = 'UNKNOWN'
    print('{} - {}'.format(state_text, output))


def check_urls(
    url_list: list,
    codes_list: list,
    http_method: str,
    allow_redirects: bool,
):
    unreachable_urls = []
    manager = PoolManager()
    for url in url_list:
        try:
            request = manager.request(
                method=http_method,
                url=url,
                timeout=5,
                retries=2,
                redirect=allow_redirects,
            )
            code = request.status
            if codes_list is None:
                accepted_codes = ['1', '2', '3']
                code = str(request.status)[0]
            else:
                accepted_codes = codes_list

            if code not in accepted_codes:
                unreachable_urls.append({
                    'url': url,
                    'error': 'Status code not acceptable: {}'.format(
                        request.status,
                    )
                })
        except (
            HTTPError,
            MaxRetryError,
            NewConnectionError,
            TimeoutError
        ) as e:
            unreachable_urls.append({'url': url, 'error': str(e)})

    return unreachable_urls


def main():
    args = parse_args()
    unreachable_urls = check_urls(
        url_list=args.url_list,
        codes_list=args.codes_list,
        http_method=args.http_method,
        allow_redirects=args.allow_redirects,
        )
    exit_code, message = build_plugin_output(unreachable_urls)

    print_nagios_message(exit_code, message)
    exit(exit_code)


if __name__ == '__main__':
    main()
