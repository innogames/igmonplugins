#!/usr/bin/env python
#
# InnoGames Monitoring Plugins Library
#
# Copyright (c) 2016, InnoGames GmbH
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
#

from __future__ import print_function

import sys

def exit(exit_code=None, message=''):
    """Exit procedure for the check commands"""

    if exit_code == ExitCodes.ok:
        status = 'OK'
    elif exit_code == ExitCodes.warning:
        status = 'WARNING'
    elif exit_code == ExitCodes.critical:
        status = 'CRITICAL'
    else:
        status = 'UNKNOWN'
        exit_code = 3

        # People tend to interpret UNKNOWN status in different ways.
        # We are including a default message to avoid confusion.  When
        # there are specific problems, errors, the message should be
        # set.
        if not message:
            message = 'Nothing could be checked'

    print(status, message)
    sys.exit(exit_code)

class ExitCodes:
    """Enum for Nagios compatible exit codes

    We are not including a code for unknown in here.  Anything other
    than those two are considered as unknown.  It is easier to threat
    unknown as None on Python rather than giving it a number greater
    than 2, because None is less than all of those.
    """

    ok = 0
    warning = 1
    critical = 2
