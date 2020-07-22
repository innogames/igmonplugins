#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Puppetd Check

Copyright (c) 2020 InnoGames GmbH
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
import os
import platform
import time
import datetime


DEFAULT_WARNING_THRESHOLD = 8000
DEFAULT_CRITICAL_THRESHOLD = 0


class ExitCodes:
    ok = 0
    warning = 1
    critical = 2
    unknown = 3


class CheckException(Exception):
    """Raised to exit with a valid nagios state"""
    pass


def get_args():
    parser = ArgumentParser(
        description=(
            'Check if the time of the last puppetrun is '
            'longer ago than -w (warning) or -c (critical)'
        )
    )
    parser.add_argument(
        '-w',
        dest='warning',
        type=int,
        default=DEFAULT_WARNING_THRESHOLD,
        required=False,
        help=(
            "Warning threshold in seconds. "
            "Default is {}. "
            "0 = disable warning."
            .format(DEFAULT_WARNING_THRESHOLD)
        )
    )
    parser.add_argument(
        '-c',
        dest='critical',
        type=int,
        default=DEFAULT_CRITICAL_THRESHOLD,
        required=False,
        help=(
            "Critical threshold in seconds. "
            "Default is {}. "
            "0 = disable critical."
            .format(DEFAULT_CRITICAL_THRESHOLD)
        )
    )
    parser.add_argument(
        '-v', dest='verbose', action='store_true', required=False,
        help="Enable verbose output"
    )

    args = parser.parse_args()

    if args.critical > 0 and args.warning >= args.critical:
        err = (
            "Warning threshold (%d) higher or equals "
            "critical threshold (%d)"
        ) % (args.warning, args.critical)
        raise CheckException(ExitCodes.warning, err)

    return args


def print_nagios_message(code, reason):
    if code == ExitCodes.ok:
        state_text = 'OK'
    elif code == ExitCodes.warning:
        state_text = 'WARNING'
    elif code == ExitCodes.critical:
        state_text = 'CRITICAL'
    else:
        state_text = 'UNKNOWN'
    print("{0} - {1}".format(state_text, reason))


def print_debug(args, text):
    if args.verbose:
        print(text)


def print_overview(args, last_run, now, age_sec):
    d_last_r = datetime.datetime.utcfromtimestamp(last_run)
    d_now = datetime.datetime.utcfromtimestamp(now)
    print_debug(args, "Last run: {0} ({1} UTC)".format(last_run, d_last_r))
    print_debug(args, "Now:      {0} ({1} UTC)".format(now, d_now))
    print_debug(args, "Diff:     {0}".format(age_sec))
    print_debug(args, "Warning:  {0}".format(args.warning))
    print_debug(args, "Critical: {0}".format(args.critical))
    print_debug(args, "")


def get_filenames():
    puppet_disabled_file = '/var/lib/nagios3/.nopuppetd'
    if platform.system() == 'Linux':
        return puppet_disabled_file, '/var/tmp/puppet_lastupdate'
    elif platform.system() == 'FreeBSD':
        return puppet_disabled_file, '/var/puppet/lastupdate'

    raise CheckException(
        ExitCodes.unknown,
        "{0} is not supported".format(platform.system())
    )


def check(args, puppet_disabled_file, puppet_state_file):
    print_debug(args, "Open file {0}".format(puppet_state_file))
    try:
        with open(puppet_state_file, 'r') as fd:
            content = fd.read()
            last_run = int(content.replace("\n", ''))
    except IOError:
        err = 'cannot read statefile %s' % (puppet_state_file)
        return ExitCodes.critical, err
    except ValueError:
        err = "statefile %s is corrupt" % (puppet_state_file)
        return ExitCodes.critical, err

    now = int(time.time())
    age_sec = now - last_run
    print_overview(args, last_run, now, age_sec)
    output_sec = "{0} seconds".format(age_sec)
    if args.critical > 0 and age_sec >= args.critical:
        return ExitCodes.critical, output_sec
    if args.warning > 0 and age_sec >= args.warning:
        return ExitCodes.warning, output_sec

    return ExitCodes.ok, output_sec


def main():
    try:
        args = get_args()
        puppet_disabled_file, puppet_state_file = get_filenames()

        print_debug(
            args,
            "Testing if file {0} exists".format(puppet_disabled_file)
        )
        if os.path.exists(puppet_disabled_file):
            code, reason = ExitCodes.ok, 'Check skipped'
        else:
            code, reason = check(args, puppet_disabled_file, puppet_state_file)
    except CheckException as e:
        code, reason = e.args[0], e.args[1]

    print_nagios_message(code, reason)
    exit(code)


if __name__ == '__main__':
    main()
