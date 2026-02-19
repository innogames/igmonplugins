#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Jenkins Remoting Process Check

This script checks whether a Jenkins remoting agent process is running
on the host.  It looks for a java process with the specified jar file
(e.g. remoting.jar on macOS or slave.jar on Debian) in its command line.

Copyright (c) 2026 InnoGames GmbH
"""

import sys
from argparse import ArgumentParser
from subprocess import Popen, PIPE


def parse_args():
    parser = ArgumentParser(
        description="Check if Jenkins remoting agent process is running",
    )
    parser.add_argument(
        "--jar",
        default="remoting.jar",
        help="Jar filename to match (e.g. remoting.jar, slave.jar)",
    )
    parser.add_argument(
        "--critical",
        action="store_true",
        help="Exit CRITICAL instead of WARNING when process is not found",
    )
    return parser.parse_args()


def main(args):
    ps = Popen(("ps", "-A", "-o", "pid=", "-o", "command="), stdout=PIPE)

    with ps.stdout as fd:
        for line in fd:
            parts = line.decode("utf8").strip().split(None, 1)
            if len(parts) < 2:
                continue
            pid, command = parts
            if "java" in command and "-jar" in command and args.jar in command:
                print(f"OK - Jenkins remoting process running (PID: {pid})")
                sys.exit(0)

    if args.critical:
        print("CRITICAL - Jenkins remoting process not running")
        sys.exit(2)
    else:
        print("WARNING - Jenkins remoting process not running")
        sys.exit(1)


if __name__ == "__main__":
    main(parse_args())
