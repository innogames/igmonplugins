#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Postgres waiting changes check

This script checks if there are any changes waiting for postgresql restart to
be activated. It queries pg_settings which has a special value for this.

Copyright (c) 2022 InnoGames GmbH
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

from sys import exit


def main():
    """Main entrypoint for script"""

    pending = _get_configs_pending_restarts()

    if pending:
        print(
            'WARNING - Waiting for restart for following configs: {}'
            .format(', '.join(pending))
        )
        exit(1)
    else:
        print('OK - Not waiting restart for any changes')
        exit(0)


def _get_configs_pending_restarts():
    """Get PG config values which are waiting for a restart

    :return: list
    """

    query = "select name from pg_settings where pending_restart = 't';"

    output = subprocess.check_output(
        'psql postgres -tAc "{}"'.format(query), shell=True)

    return(output.decode().splitlines())


if __name__ == '__main__':
    main()
