#!/usr/bin/env python3
#
# InnoGames Monitoring Plugins - Check folder writeability
#
# Copyright © 2024 InnoGames GmbH
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
import os
import random
import string
import subprocess
import sys


def generate_random_word(length=10):
    return ''.join(random.choices(string.ascii_lowercase, k=length))


def is_on_different_filesystem(path):
    path = os.path.abspath(path)
    root_dev = os.stat('/').st_dev
    path_dev = os.stat(path).st_dev
    return root_dev != path_dev


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="""
Check folder writeability for Nagios.

This script writes a random word to a file in a directory and then reads it back.
The read word is compared to the original word.

It wants all options explicitly and does not assume file paths etc. since it
can be used in environments with network mounts and other special cases."""
),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        '--external-cmd', required=True, help='The command to confirm the written data.'
    )
    parser.add_argument(
        '--directory', required=True, help='Directory to test writeability in.'
    )
    parser.add_argument(
        '-f',
        '--filename',
        required=True,
        help='Custom filename for the test file',
    )
    parser.add_argument(
        '-w', '--word', help='Custom word to write to the file', default=None
    )
    parser.add_argument(
        '--enforce-different-fs',
        action='store_true',
        help='Fail if the directory is on root filesystem (a.k.a. not mounted)',
        default=False,
    )
    return parser.parse_args()


def main():
    args = parse_arguments()

    if not os.path.isdir(args.directory):
        print(f'UNKNOWN - Directory "{args.directory}" does not exist')
        sys.exit(3)

    if args.enforce_different_fs:
        if not is_on_different_filesystem(args.directory):
            print(f'CRITICAL - Directory "{args.directory}" is not mounted')
            sys.exit(2)

    # Generate or use provided word and filename
    original_word = args.word if args.word else generate_random_word()
    filepath = os.path.join(args.directory, args.filename)

    try:
        # Write the word to a file
        with open(filepath, 'w') as f:
            f.write(original_word)

        result = subprocess.run(
            args.external_cmd.split(),
            capture_output=True,
            text=True,
        )
        read_word = result.stdout.strip()

        # Compare the strings
        if original_word == read_word:
            print(f'OK - Read/write successful for directory {args.directory}')
            sys.exit(0)
        else:
            print(
                f'CRITICAL - Read/write failed for directory {args.directory}. '
                f'Read: "{read_word}", expected: "{original_word}"'
            )
            sys.exit(2)

    except Exception as e:
        print(f'CRITICAL - An error occurred: {str(e)}')
        sys.exit(2)

    finally:
        # Clean up: remove the test file in any case
        try:
            os.remove(filepath)
        except:
            pass


if __name__ == '__main__':
    main()
