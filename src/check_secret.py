#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - check_secret

Check if service was restarted after timestamp in secret_timestamp file.

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

from argparse import ArgumentParser, Namespace
from datetime import datetime, timedelta
from subprocess import check_output
from sys import exit


def parse_args() -> Namespace:
    parser = ArgumentParser(__doc__)
    parser.add_argument("-s", dest="service_name", type=str, required=True)
    parser.add_argument("-w", dest="warning_days", type=int, required=True)
    parser.add_argument("-c", dest="critical_days", type=int, required=True)
    parser.add_argument("-p", dest="timestamp_file_path", type=str, required=True)
    return parser.parse_args()


def get_service_restart_time(service_name: str) -> datetime:
    """
    Gets restart time of service via systemctl.

    Args:
        service_name: Systemd Service name

    Returns: Datetime.
    """
    date_s = (
        check_output(
            [
                "/bin/systemctl",
                "show",
                f"{service_name}.service",
                "-p",
                "ExecMainStartTimestamp",
                "--value",
            ]
        )
        .decode("utf-8")
        .rstrip("\n")
    )
    return datetime.strptime(date_s, "%a %Y-%m-%d %H:%M:%S %Z")


def get_secret_file_time(timestamp_path: str) -> datetime:
    """
    Gets rotation time from secret rotation file.
    File design: File contains current rotation number and iso date.
    Example: 34 2022-10-26\n

    Args:
        timestamp_path: Location of file containing timestamp

    Returns: Datetime.
    """
    with open(timestamp_path, "r") as f:
        date_line = f.readline().split(" ")[1].rstrip("\n")
    return datetime.fromisoformat(date_line)


def get_time_delta(service_time: datetime,
                   secret_rotation_time: datetime) -> timedelta:
    """
    Calculates delta between service restart time and secret rotation time.

    Args:
        service_time: Time when service was restarted
        secret_rotation_time: Time when secrets were rotated

    Returns: Timedelta of two inputs
    """
    return secret_rotation_time - service_time


def main():
    args = parse_args()
    delta = get_time_delta(
        get_service_restart_time(args.service_name),
        get_secret_file_time(args.timestamp_file_path),
    )
    if delta.days > args.critical_days:
        print(
            f"CRITICAL - {args.service_name} does not run with newest set of"
            " secrets"
        )
        exit(2)
    elif delta.days > args.warning_days:
        print(
            f"WARNING - {args.service_name} does not run with newest set of"
            " secrets"
        )
        exit(1)
    else:
        print(
            f"OK - {args.service_name} is running with a current set of secrets"
            " parameters."
        )
        exit(0)


if __name__ == "__main__":
    main()
