#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Crony Check

Copyright © 2025 InnoGames GmbH
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

import platform
from argparse import ArgumentParser
from enum import Enum
from subprocess import check_output, STDOUT
from sys import exit


def parse_args():
    parser = ArgumentParser(
        description=(
            "Check time difference between local Chrony deamon " "and its NTP peers"
        )
    )
    parser.add_argument(
        "-w",
        dest="warning",
        type=float,
        required=True,
        help="Time difference in seconds for Warning state",
    )
    parser.add_argument(
        "-c",
        dest="critical",
        type=float,
        required=True,
        help="Time difference in seconds for Critical state",
    )
    parser.add_argument(
        "-g",
        dest="good_peers",
        type=int,
        required=False,
        help="Minimal amount of synchronized peers for good state",
        default=2,
    )
    return parser.parse_args()


def main():
    args = parse_args()
    peers = get_peers()
    output_lines = []
    worst_line = None

    if not peers:
        worst_exit_code = ExitCodes.critical
        print("CRITICAL: No peers found!")
        return worst_exit_code

    synced_peers = 0
    worst_exit_code = ExitCodes.ok
    for peer_k, peer_v in peers.items():
        peer_exit_code = ExitCodes.critical
        line = f"{peer_k}: "
        if peer_v["synced"]:
            line += f"offset {peer_v['offset']:02f}s"
            if peer_v["synced"]:
                if abs(peer_v["offset"]) > args.critical:
                    peer_exit_code = ExitCodes.critical
                elif abs(peer_v["offset"]) > args.warning:
                    peer_exit_code = ExitCodes.warning
                else:
                    synced_peers += 1
                    peer_exit_code = ExitCodes.ok
        else:
            line += "not synced"
        output_lines.append(line)
        if peer_exit_code.value > worst_exit_code.value:
            worst_exit_code = peer_exit_code
            worst_line = line

    # As long as there are 2 or more synced peers we can ignore peers that
    # are unreachable or have too big offset.
    if worst_line and synced_peers < args.good_peers:
        output_lines.insert(
            0, f"{worst_exit_code.name.upper()}: Worst peer {worst_line}"
        )
        exit_code = worst_exit_code
    else:
        output_lines.insert(0, f"OK: At least {args.good_peers} peers are synced!")
        exit_code = ExitCodes.ok
    print("\n".join(output_lines))
    return exit_code


def get_peers():
    if platform.system() == "FreeBSD":
        chrony = "/usr/local/bin/chronyc"
    else:
        chrony = "/usr/bin/chronyc"

    try:
        proc = check_output(
            [chrony, "-c", "-n", "sources"],
            stderr=STDOUT,
        ).decode()
    except OSError as e:
        print(f"UNKNOWN: can't read Chrony status: {e}")
        exit(ExitCodes.unknown)

    peers = {}

    for line in proc.split("\n"):
        if line:
            line = line.split(",")
            if line[0] != "^":
                # Exclude non-servers
                continue
            synced = False
            if line[1] in ("*", "+", "-"):
                synced = True
            peers[line[2]] = {
                "offset": float(line[8]),
                "synced": synced,
            }
    return peers


# Nagios plugin exit codes
class ExitCodes(Enum):
    ok = 0
    warning = 1
    critical = 2
    unknown = 3


if __name__ == "__main__":
    exit(main().value)
