#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - APT ambiguous package sources

Checks that every package has only one available source to choose from.

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
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.


import subprocess
import sys
import typing
import re

SOURCE_REGEX = re.compile(r'^\s+[0-9]+\s(\S+\s\S+\s\S+\s\S+)$')


def main() -> typing.Tuple[int, str]:
    policy_output = get_apt_cache_policy_output()
    ambiguous_sources = find_ambiguous_sources(policy_output)

    if len(ambiguous_sources) == 0:
        return 0, 'OK - No ambiguous sources found'

    return 1, get_warn_msg(ambiguous_sources)


def get_warn_msg(ambiguous_sources: typing.Dict[str, typing.List[str]]) -> str:
    pkg_names = list(sorted(ambiguous_sources.keys()))
    msg = (
        f'WARNING - Found {len(pkg_names)} packages with ambiguous sources: '
        f'{", ".join(pkg_names)}\n'
        '<table class="cellborder rowhover">'
        '<tr><th>Package</th><th>Sources</th></tr>'
    )
    for pkg_name in pkg_names:
        sources = ambiguous_sources[pkg_name]
        msg += (
            f'<tr>'
            f'<td valign=top>{pkg_name}</td>'
            f'<td>{"<br/>".join(sources)}</td>'
            f'</tr>'
        )
    msg += '</table>'

    return msg


def find_ambiguous_sources(
    policy_output: str,
) -> typing.Dict[str, typing.List[str]]:
    sources = {}
    ambiguous_sources = {}
    curr_pkg = None
    in_version_table = False
    for line in policy_output.splitlines():
        if not line.startswith(' '):
            if len(sources) > 1:
                ambiguous_sources[curr_pkg] = list(sources.keys())

            curr_pkg = line.split(':')[0]
            in_version_table = False
            sources = {}
            continue

        if in_version_table:
            match = SOURCE_REGEX.fullmatch(line)
            if match is None:
                continue

            sources[match.group(1)] = True

        if 'Version table:' in line:
            in_version_table = True

    return ambiguous_sources


def get_apt_cache_policy_output() -> str:
    policy_cmd = subprocess.run(
        ['apt-cache', 'policy', '.'],
        check=True,
        stdout=subprocess.PIPE,
    )
    return policy_cmd.stdout.decode()


if __name__ == '__main__':
    code, output = main()
    print(output)
    sys.exit(code)
