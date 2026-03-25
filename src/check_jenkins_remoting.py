#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Jenkins Remoting Process Check

This script checks whether a Jenkins remoting agent process is running
on the host.  It looks for a java process with the specified jar file
(e.g. remoting.jar on macOS or slave.jar on Debian) in its command line.

Copyright (c) 2026 InnoGames GmbH
"""

import platform
import sys
from argparse import ArgumentParser
from subprocess import PIPE, Popen


def parse_args():
    parser = ArgumentParser(
        description='Check if Jenkins remoting agent process is running',
    )
    parser.add_argument(
        '--jar',
        nargs='+',
        default=['remoting', 'slave.jar'],
        help='Jar name substrings to match (default: remoting slave.jar)',
    )
    parser.add_argument(
        '--critical',
        action='store_true',
        help='Exit CRITICAL instead of WARNING when process is not found',
    )
    return parser.parse_args()


def check_process(jars):
    """Check for Jenkins remoting via ps output."""
    ps = Popen(('ps', '-A', '-o', 'pid=', '-o', 'command='), stdout=PIPE)

    with ps.stdout as fd:
        for line in fd:
            parts = line.decode('utf8').strip().split(None, 1)
            if len(parts) < 2:
                continue
            pid, command = parts
            if 'java' in command and '-jar' in command:
                if any(jar in command for jar in jars):
                    return pid
    return None


def check_launchd(jars):
    """Check for Jenkins remoting via launchctl on macOS."""
    launchctl = Popen(
        ('launchctl', 'list'),
        stdout=PIPE,
        stderr=PIPE,
    )
    with launchctl.stdout as fd:
        for line in fd:
            parts = line.decode('utf8').strip().split('\t')
            if len(parts) < 3:
                continue
            pid, status, label = parts
            if 'jenkins' in label.lower() and pid != '-':
                # Verify the service is actually running the expected jar
                # by inspecting its arguments via launchctl print
                print_proc = Popen(
                    ('launchctl', 'print', f'system/{label}'),
                    stdout=PIPE,
                    stderr=PIPE,
                )
                stdout, _ = print_proc.communicate()
                output = stdout.decode('utf8', errors='replace')
                if any(jar in output for jar in jars):
                    return pid
    return None


def main(args):
    pid = check_process(args.jar)

    # On macOS, also check launchd services if process check fails
    if pid is None and platform.system() == 'Darwin':
        pid = check_launchd(args.jar)

    if pid is not None:
        print(f'OK - Jenkins remoting process running (PID: {pid})')
        sys.exit(0)

    if args.critical:
        print('CRITICAL - Jenkins remoting process not running')
        sys.exit(2)
    else:
        print('WARNING - Jenkins remoting process not running')
        sys.exit(1)


if __name__ == '__main__':
    main(parse_args())
