#!/usr/bin/env python3
#
# InnoGames Monitoring Plugins - Vault Status Check
#
# Copyright © 2025 InnoGames GmbH
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
import argparse
import socket
import sys

import requests


class ExitCodes():
    OK = 0
    WARNING = 1
    CRITICAL = 2
    UNKNOWN = 3


def parse_args():
    parser = argparse.ArgumentParser(
        description='Check the status of a Vault server.'
    )
    parser.add_argument(
        '--host',
        type=str,
        default=socket.getfqdn(),
        help='Vault server host (default: hostname of the machine)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=8200,
        help='Vault server port (default: 8200)'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=5,
        help='Request timeout in seconds (default: 5)'
    )
    return parser.parse_args()


def check_vault_status(host: str, port: int, timeout: int) -> tuple[str, int]:
    url = f'https://{host}:{port}/v1/sys/health'
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code == 200:
            return 'OK: Vault is initialized and unsealed', ExitCodes.OK
        elif response.status_code == 429:
            return 'OK: Vault is unsealed and in standby mode', ExitCodes.OK
        elif response.status_code == 472:
            return ('WARNING: Vault is in Disaster Recovery mode',
                    ExitCodes.WARNING)
        elif response.status_code == 501:
            return 'CRITICAL: Vault is not initialized', ExitCodes.CRITICAL
        elif response.status_code == 503:
            return 'CRITICAL: Vault is sealed', ExitCodes.CRITICAL
        else:
            return (f'Unexpected status code: {response.status_code}',
                    ExitCodes.UNKNOWN)
    except requests.exceptions.SSLError as e:
        return f'SSL-Error when connecting to Vault: {e}', ExitCodes.CRITICAL
    except requests.exceptions.Timeout as e:
        return f'Timeout when connecting to Vault: {e}', ExitCodes.CRITICAL
    except requests.exceptions.RequestException as e:
        return f'Error when connecting to Vault: {e}', ExitCodes.CRITICAL


def main():
    args = parse_args()
    message, exit_code = check_vault_status(args.host, args.port, args.timeout)
    print(message)
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
