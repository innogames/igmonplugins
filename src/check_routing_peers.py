#!/usr/bin/env python3

"""InnoGames Monitoring Plugins - Check routing protocols

This is a Nagios passive script for checking BIRD protocols and FRR BGP sessions.

Copyright © 2025 InnoGames GmbH
"""
import enum
import json
import os
import platform
import socket
import subprocess
import sys
import typing

from argparse import ArgumentParser
from subprocess import check_output, STDOUT

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

# nsca uses End of Transmission Block between records
NSCA_RECORD_SEPARATOR = chr(23)


def parse_args():
    parser = ArgumentParser(
        description="Check if given routing peers are up and established"
    )
    parser.add_argument("path", help="Path to the birdc/birdc6/vtysh binary")
    parser.add_argument(
        "-H",
        "--nsca-host",
        action="append",
        dest="nsca_hosts",
        metavar="HOST",
        help="Send results to given NSCA host, can be specified multiple times",
    )
    parser.add_argument(
        "peers",
        nargs="*",
        help="BIRD protocols or FRR peers to check (optional if ROUTING_PEERS env var is set)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Get peers from command line or environment variable
    peers = args.peers
    if not peers:
        env_peers = os.environ.get("ROUTING_PEERS")
        if env_peers:
            peers = env_peers.split()
        else:
            print(
                "ERROR: No peers specified. Provide peers as command line arguments or set ROUTING_PEERS environment variable.",
                file=sys.stderr,
            )
            sys.exit(1)

    hostname = socket.gethostname()

    text_results = []
    nsca_results = []

    states = {}
    rps = []
    if args.path.endswith("birdc") or args.path.endswith("birdc6"):
        rps = RoutingProtocol.from_birdc(args.path)
    elif args.path.endswith("vtysh"):
        rps = RoutingProtocol.from_vtysh(args.path)

    for rp in rps:
        states[rp.name] = rp.state

    for peer in peers:
        state = states.get(peer)
        if state:
            sv = state.value
            text_results.append(f"{peer}: {sv['nagios'].name} {sv['description']}")
            nsca_results.append(
                f"{hostname}\trouting_{peer}\t{sv['nagios']}\t{sv['description']}"
            )
        else:
            text_results.append(
                f"{peer}: {NagiosCodes.UNKNOWN.name} Protocol not found"
            )
            nsca_results.append(
                f"{hostname}\trouting_{peer}\t{NagiosCodes.UNKNOWN.value}\tProtocol not found"
            )

    print("\n".join(text_results))

    if args.nsca_hosts:
        nsca_data = NSCA_RECORD_SEPARATOR.join(nsca_results)
        if platform.system() == "FreeBSD":
            nsca_command = [
                "/usr/local/sbin/send_nsca",
                "-c",
                "/usr/local/etc/nagios/send_nsca.cfg",
            ]
        else:
            nsca_command = ["/usr/sbin/send_nsca", "-c", "/etc/send_nsca.cfg"]

        for nsca_host in args.nsca_hosts:
            try:
                subprocess.run(
                    nsca_command + ["-H", nsca_host],
                    input=nsca_data,
                    text=True,
                    check=True,
                    capture_output=True,
                )
            except subprocess.CalledProcessError as e:
                print(f"Failed to send to NSCA host {nsca_host}: {e}")


class RoutingProtocol:
    name: str
    state: "ProtocolStates"

    def __init__(self, name: str):
        self.name = name

    @classmethod
    def from_birdc(cls, path: str) -> typing.Iterable["RoutingProtocol"]:
        # Don't try to deal with errors. This script is run from a cron job and submits
        # a passive result to Nagios. If it fails for any reason we will get a Nagios
        # unknown state.
        output = check_output([path, "show", "protocols"], stderr=STDOUT)

        # Matching protocol lines from BIRD:
        # BIRD 1.6.3 ready.
        # name     proto    table    state  since       info
        # direct1  Direct   master   up     2020-02-27
        # b_af     BGP      master   up     2020-02-28  Established
        # b_lb     BGP      master   start  18:43:46    Active        Socket: conn
        # b_home   BGP      master   down   2020-02-29
        # We are extracting the protocol name, state, date/time since last
        # change and the additional information about the state of the session.
        lines = output.decode().splitlines()
        for line in lines[2:]:
            yield BirdRoutingProtocol(line)

    @classmethod
    def from_vtysh(
        cls,
        path,
    ) -> typing.Iterable["RoutingProtocol"]:
        for command in (
            "show ip bgp ipv4 neighbor json",
            "show ip bgp ipv6 neighbor json",
        ):
            output = check_output([path, "-c", command], stderr=STDOUT)
            for data in json.loads(output.decode()).values():
                yield FrrBGPRoutingProtocol(data)


class BirdRoutingProtocol(RoutingProtocol):
    _fields: typing.List[str]
    _info: str
    _table: str
    _since: str
    _type: str

    def __init__(self, line: str):
        # Ensure that we always have 7 elements in the line, as the tokenization
        # of protocols that are disabled yields only 6 elements.
        fields = [x.strip() for x in line.split(None, 6)]
        fields += [None] * (7 - len(fields))

        self._type = fields[1]
        self._table = fields[2]
        self._state = fields[3]

        # BIRD has a few date formats. One is ISO short dates another is ISO long
        # dates. When using ISO short, BIRD will output HH:MM:SS in the since field
        # for times smaller than 24 hours and then switch to 2020-01-01 after.
        # For ISO long it will always output 2020-08-31 20:40:51.
        # With the if below, we can differentiate between the two date formats as
        # when using ISO short, we end up with the protocol info in field 5
        # instead of the time.
        # The protocol info is empty sometimes, hence the check for fields[5] being
        # not null.
        if fields[5] and ":" in fields[5]:
            self._since = "{} {}".format(fields[4], fields[5])
            self._info = fields[6]
        else:
            self._since = fields[4]
            self._info = fields[5]

        super().__init__(fields[0])

    @property
    def state(self) -> "ProtocolStates":
        if self._type == "BGP":
            return self.check_bgp_protocol()
        elif self._type == "OSPF":
            return self.check_ospf_protocol()
        elif self._type == "RPKI":
            return self.check_rpki_protocol()
        # else self.type in {"Device", "Direct", "Kernel", "Pipe", "Static"}:
        return self.check_other_protocol()

    def check_bgp_protocol(self) -> "ProtocolStates":
        def is_bgp_up(protocol: "BirdRoutingProtocol") -> bool:
            is_established = self._info == "Established"
            is_up = self._state == "up"
            return is_up and is_established

        def is_bgp_disabled(protocol: "BirdRoutingProtocol") -> bool:
            state_down = self._state == "down"
            return state_down

        if is_bgp_up(self):
            return ProtocolStates.up
        elif is_bgp_disabled(self):
            return ProtocolStates.disabled
        else:
            return ProtocolStates.down

    def check_ospf_protocol(self) -> "ProtocolStates":
        def is_ospf_up(protocol: "BirdRoutingProtocol") -> bool:
            is_up = self._state == "up"
            is_running = self._info == "Running"
            return is_up and is_running

        def is_ospf_disabled(protocol: "BirdRoutingProtocol") -> bool:
            is_down = self._state == "down"
            return is_down

        if is_ospf_up(self):
            return ProtocolStates.up
        elif is_ospf_disabled(self):
            return ProtocolStates.disabled
        else:
            return ProtocolStates.down

    def check_rpki_protocol(self) -> "ProtocolStates":
        def is_rpki_up(protocol: "BirdRoutingProtocol") -> bool:
            is_up = self._state == "up"
            is_running = self._info in ["Established", "Sync-Running", "Sync-Start"]
            return is_up and is_running

        def is_rpki_disabled(protocol: "BirdRoutingProtocol") -> bool:
            is_down = self._state == "down"
            return is_down

        if is_rpki_up(self):
            return ProtocolStates.up
        elif is_rpki_disabled(self):
            return ProtocolStates.disabled
        else:
            return ProtocolStates.down

    def check_other_protocol(self) -> "ProtocolStates":
        if self._state == "up":
            return ProtocolStates.up
        elif self._state == "down":
            return ProtocolStates.disabled
        else:
            return ProtocolStates.down


class FrrBGPRoutingProtocol(RoutingProtocol):
    _bgp_state: str
    _admin_shut_down: bool

    def __init__(self, data):
        super().__init__(data["nbrDesc"])
        self._bgp_state = data["bgpState"]
        self._admin_shut_down = data.get("adminShutDown")  # It's optional in json

    @property
    def state(self) -> "ProtocolStates":
        if self._bgp_state == "Established":
            return ProtocolStates.up
        if self._bgp_state == "Idle" and self._admin_shut_down:
            return ProtocolStates.disabled
        return ProtocolStates.unknown


class NagiosCodes(enum.IntEnum):
    OK = 0
    WARNING = 1
    CRITICAL = 2
    UNKNOWN = 3


class ProtocolStates(enum.Enum):
    up = {"nagios": NagiosCodes.OK, "description": "Protocol is up"}
    disabled = {"nagios": NagiosCodes.WARNING, "description": "Protocol is disabled"}
    down = {"nagios": NagiosCodes.CRITICAL, "description": "Protocol is down"}
    unknown = {"nagios": NagiosCodes.UNKNOWN, "description": "Protocol not found"}


if __name__ == "__main__":
    main()
