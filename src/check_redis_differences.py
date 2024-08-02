#!/usr/bin/env python3
#
# InnoGames Monitoring Plugins - Redis difference check
#
# This script checks for differences between a Redis configuration file and a
# running Redis instance. It compares the configurations based on key-value
# pairs and reports any discrepancies found.
#
# Copyright (c) 2024 InnoGames GmbH
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
import re
import sys
from typing import Union

import redis

# Nagios exit codes
OK = 0
WARNING = 1
CRITICAL = 2
UNKNOWN = 3


def parse_redis_config(file_path: str) -> dict[str, Union[str, list[str]]]:
    """
    Parses a Redis configuration file and returns a dictionary of key-value pairs.
    """
    config = {}
    # Some config values are multi-line, needs special treatment
    multi_line_keys = ['save', 'client-output-buffer-limit']
    current_key = None

    try:
        with open(file_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    parts = line.split(maxsplit=1)
                    if len(parts) == 2:
                        key, value = parts
                        if key in multi_line_keys:
                            if key not in config:
                                config[key] = []
                            config[key].append(value)
                        else:
                            config[key] = value.strip('"')
                    elif current_key in multi_line_keys:
                        config[current_key].append(line)
                    current_key = parts[0] if parts else None
        return config
    except (FileNotFoundError, PermissionError, IOError, OSError) as error:
        # Maybe permission error? But let's catch more broadly
        print(f'UNKNOWN - Error: {error}')
        sys.exit(UNKNOWN)


def normalize_value(value: Union[str, list[str]]) -> str:
    """
    Joins list values into a single string and converts to lowercase.
    """
    if isinstance(value, list):
        return ' '.join(value)
    return value.lower()


def parse_memory_size(size_str: str) -> Union[int, str]:
    """
    Parses a memory size string and returns the size in bytes or the original string.
    """
    size_str = size_str.upper()
    if size_str.isdigit():
        return int(size_str)

    multipliers = {
        'B': 1,
        'KB': 1024,
        'MB': 1024 ** 2,
        'GB': 1024 ** 3,
    }

    match = re.match(r'^(\d+(?:\.\d+)?)\s*([KMGB]B?)?$', size_str)
    if match:
        number, unit = match.groups()
        return int(float(number) * multipliers.get(unit, 1))

    return size_str  # Return as-is if not a recognizable memory size


def compare_memory_values(file_value: str, running_value: str) -> int:
    """Compares memory values from file and running configurations."""
    file_parsed = parse_memory_size(file_value)
    running_parsed = parse_memory_size(running_value)

    # If both are integers, compare them directly
    if isinstance(file_parsed, int) and isinstance(running_parsed, int):
        return OK if file_parsed == running_parsed else CRITICAL
    # If only one of them is an integer, return UNKNOWN (bug?)
    if isinstance(file_parsed, int) or isinstance(running_parsed, int):
        return UNKNOWN
    # They are strings, compare them case-insensitively
    if file_parsed.lower() == running_parsed.lower():
        return OK
    # When here, means they are different
    return CRITICAL


def is_client_output_buffer_limit_equal(
    file_value: list[str], running_value: str
) -> bool:
    """Compares client output buffer limit configurations."""
    file_parts = ' '.join(file_value).split()
    running_parts = running_value.split()

    # Quick fail
    if len(file_parts) != len(running_parts):
        return False

    for i in range(len(file_parts)):
        if i == 0 or file_parts[i] == '0':  # Skip class names and zero values
            if file_parts[i].lower() != running_parts[i].lower():
                return False
        else:
            if compare_memory_values(file_parts[i], running_parts[i]) != OK:
                return False

    return True


def compare_configs(
    file_config: dict, running_config: dict
) -> tuple[int, list[str]]:
    """Compares file and running Redis configurations."""
    differences = []
    exit_code = OK
    for key, file_value in file_config.items():
        if key in running_config:
            running_value = running_config[key]

            if key in ['auto-aof-rewrite-min-size', 'maxmemory']:
                result = compare_memory_values(file_value, running_value)
                if result != OK:
                    differences.append(
                        f'{key}: Config file: {file_value}, Running: {running_value}'
                    )
                    exit_code = max(exit_code, result)
            elif key == 'client-output-buffer-limit':
                if not is_client_output_buffer_limit_equal(
                    file_value, running_value
                ):
                    differences.append(
                        f"{key}: Config file: {' '.join(file_value)}, Running: {running_value}"
                    )
                    exit_code = CRITICAL
            elif normalize_value(file_value) != normalize_value(running_value):
                differences.append(
                    f'{key}: Config file: {file_value}, Running: {running_value}'
                )
                exit_code = CRITICAL

    return exit_code, differences


def main():
    parser = argparse.ArgumentParser(
        description='Check Redis configuration differences.'
    )
    parser.add_argument(
        'config_file', help='Path to the Redis configuration file'
    )
    parser.add_argument(
        '--host', default='localhost', help='Redis host (default: localhost)'
    )
    parser.add_argument(
        '--port', type=int, default=6379, help='Redis port (default: 6379)'
    )
    parser.add_argument('--password', help='Redis password')

    args = parser.parse_args()

    try:
        file_config = parse_redis_config(args.config_file)
        redis_client = redis.Redis(
            host=args.host, port=args.port, password=args.password
        )
        running_config = redis_client.config_get()

        exit_code, differences = compare_configs(file_config, running_config)

        if differences:
            print(
                'CRITICAL - Differences found between config file and running instance:'
            )
            for diff in differences:
                print(diff)
        else:
            print(
                'OK - Redis is running with the declared configuration in the file.'
            )

        sys.exit(exit_code)

    except Exception as e:
        print(f'UNKNOWN - Error: {e}')
        sys.exit(UNKNOWN)


if __name__ == '__main__':
    main()
