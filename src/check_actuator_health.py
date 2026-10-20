#!/usr/bin/env python3
#
# InnoGames Monitoring Plugins - Actuator Health Check
#
# This script is used to check the health of a Spring Boot application
# using the actuator endpoint.
#
# Copyright © 2026 InnoGames GmbH
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
import sys

import requests


class ExitCodes:
    OK = 0
    WARNING = 1
    CRITICAL = 2
    UNKNOWN = 3


parser = argparse.ArgumentParser()
parser.add_argument(
    '-p', '--port', help='Backend port', type=int, required=True
)
parser.add_argument(
    '--path',
    help='http path for the health check. must include leading slash',
    default='/actuator/health',
)

args = parser.parse_args()
url = f'http://localhost:{args.port}{args.path}'

try:
    response = requests.get(url, timeout=8)
    health_status = response.json()
except requests.exceptions.ConnectionError:
    print(f'ConnectionError while reading {url}')
    sys.exit(ExitCodes.UNKNOWN)
except requests.exceptions.ReadTimeout:
    print(f'ReadTimeout while reading {url}')
    sys.exit(ExitCodes.UNKNOWN)
except Exception as e:
    print(f'Unknown Exception while reading {url} : {e}')
    sys.exit(ExitCodes.UNKNOWN)

try:
    overall_status = health_status['status']
except (KeyError, TypeError):
    print(f'Unexpected response body from {url} : {health_status}')
    sys.exit(ExitCodes.UNKNOWN)

message = f'Health status: {overall_status}: '
details = ''
exit_code = (
    ExitCodes.OK if overall_status.lower() == 'up' else ExitCodes.CRITICAL
)

component_health = ExitCodes.OK
if 'components' in health_status:
    for component, status in health_status['components'].items():
        component_status = status['status']
        message += f'({component}={component_status}) '
        if component_status.lower() == 'critical':
            component_health = ExitCodes.CRITICAL
        if (
            component_status.lower() == 'degraded'
            and component_health == ExitCodes.OK
        ):
            component_health = ExitCodes.WARNING
        # Status strings (UP/DOWN/...) aren't numeric, so this is always
        # a plain presence marker, not a real perfdata value.
        details += f'{component}={component_status} '

        if 'details' in status:
            for detail, value in status['details'].items():
                try:
                    int(value)
                    details += f"'{component}:{detail}'={value} "
                except (ValueError, TypeError):
                    details += f"'{component}:{detail}->{value}'=0 "


print(f'{message}|{details}')

sys.exit(max([exit_code, component_health]))
