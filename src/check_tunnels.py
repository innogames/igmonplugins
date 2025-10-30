#!/usr/bin/env python3
#
# InnoGames Monitoring Plugins - Tunnels Check
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
import platform
import re
import socket
import subprocess
import typing

from argparse import ArgumentParser
from enum import IntEnum
from ipaddress import IPv4Address, IPv6Address, IPv6Interface, IPv4Interface
from subprocess import check_output, STDOUT, CalledProcessError

# nsca uses End of Transmission Block between records
NSCA_RECORD_SEPARATOR = chr(23)

IFCONFIG_RE = re.compile(
    r"^("
    # gif_aw1_af1: flags=1008051<UP,POINTOPOINT,RUNNING,MULTICAST,LOWER_UP> metric 0 mtu 1418
    "(?P<ifname>[a-z0-9_]+): flags=[0-9a-f]+<(?P<flags>[A-Z_,]+)>|"
    "\tinet ("
    # inet 192.0.2.1 --> 192.0.2.2 netmask 0xffffffff
    "(?P<ipv4_local>[0-9.]+) --> (?P<ipv4_peer>[0-9.]+)|"
    # inet 192.0.2.1 netmask 0xfffffffc
    "(?P<ipv4_address>[0-9.]+) netmask (?P<ipv4_netmask>0x[0-9a-f]+)"
    ")|"
    "\tinet6 ("
    # inet6 2001:db8::1 --> 2001:db8::2 prefixlen 128
    "(?P<ipv6_local>[0-9a-f:.]+) --> (?P<ipv6_peer>[0-9a-f:.]+)|"
    # inet6 2001:db8::2 prefixlen 126
    "(?P<ipv6_address>[0-9a-f:.]+) prefixlen (?P<ipv6_prefixlen>[0-9]+)"
    ")"
    ")"
)

FPING_RE = re.compile(
    # 192.0.2.1                           : xmt/rcv/%loss = 3/3/0%, min/avg/max = 8.31/8.71/9.49
    # 169.254.21.169                      : xmt/rcv/%loss = 10/0/100%
    r"(?P<ip_address>[0-9a-f.:]+)\s+: "
    "xmt/rcv/%loss = [0-9]+/[0-9]+/(?P<percent_loss>[0-9]+)%(,\s+)?"
    "(min/avg/max = [0-9.]+/(?P<avg_ping>[0-9.]+)/[0-9.]+)?"
)


def parse_args():
    parser = ArgumentParser()
    parser.add_argument(
        "--warning-latency",
        type=int,
        default=200,
        help="Warning threshold for latency in ms",
    )
    parser.add_argument(
        "--critical-latency",
        type=int,
        default=300,
        help="Critical threshold for latency in ms",
    )
    parser.add_argument(
        "--warning-loss",
        type=int,
        default=20,
        help="Warning threshold for packet loss in percent",
    )
    parser.add_argument(
        "--critical-loss",
        type=int,
        default=50,
        help="Critical threshold for packet loss in percent",
    )
    parser.add_argument(
        "-H",
        "--nsca-host",
        action="append",
        dest="nsca_hosts",
        metavar="HOST",
        help="Send results to given NSCA host, can be specified multiple times",
    )
    parser.add_argument("--count", type=int, default=10, help="Count of pings to send")
    parser.add_argument(
        "interfaces",
        nargs="+",
        help="Interfaces to check",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    TunnelInterface.from_ifconfig(args.interfaces)
    latencies = TunnelInterface.measure_latency(args.count)

    hostname = socket.gethostname()

    text_results = []
    nsca_results = []

    for ifname, ifdata in latencies.items():
        nagios_ping = NagiosCodes.OK
        nagios_loss = NagiosCodes.OK

        # Since avg_ping is optional build per-interface results as arrays and then join them.
        result = []
        perfdata = []

        # Interfaces with 100% packet loss have no avg_ping.
        if ifdata["avg_ping"]:
            if ifdata["avg_ping"] >= args.warning_latency:
                nagios_ping = NagiosCodes.WARNING
            if ifdata["avg_ping"] >= args.critical_latency:
                nagios_ping = NagiosCodes.CRITICAL
            result.append(f"latency {ifdata['avg_ping']}ms")
            perfdata.append(
                f"'latency'={ifdata['avg_ping']}ms;{args.warning_latency};{args.critical_latency};;"
            )

        if ifdata["percent_loss"] >= args.warning_loss:
            nagios_loss = NagiosCodes.WARNING
        if ifdata["percent_loss"] >= args.critical_loss:
            nagios_loss = NagiosCodes.CRITICAL
        result.append(f"packet loss {ifdata['percent_loss']}%")
        perfdata.append(
            f"'packet loss'={ifdata['percent_loss']}%;{args.warning_loss};{args.critical_loss};;"
        )

        result = " ".join(result)
        perfdata = " ".join(perfdata)

        nagios: NagiosCodes = max(nagios_ping, nagios_loss)

        text_results.append(f"{ifname}: {nagios.name} {result}")
        nsca_results.append(
            f"{hostname}\ttunnel_{ifname}\t{nagios.value}\t{result}|{perfdata}"
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


class TunnelInterface:
    all_interfaces: typing.List[typing.Self] = []
    name: str
    local_address: IPv4Address | IPv6Address
    remote_address: IPv4Address | IPv6Address

    def __init__(self, name, local_address, remote_address):
        self.name = name
        self.local_address = local_address
        self.remote_address = remote_address

    def __repr__(self):
        return f"{self.name}: {self.local_address} -> {self.remote_address}"

    @classmethod
    def from_ifconfig(cls, wanted_interfaces):
        ifaces = {}
        ifname_last = ""
        for line in check_output(
            ["/sbin/ifconfig"],
            universal_newlines=True,
        ).splitlines():
            r = IFCONFIG_RE.match(line)

            if r is None:
                continue

            ifname_new = r.group("ifname")
            if ifname_new:
                ifaces[ifname_new] = {"flags": r.group("flags").split(",")}
                ifname_last = ifname_new
                continue

            if not ifname_last:
                continue

            for ip_k in (
                "ipv4_local",
                "ipv4_peer",
                "ipv6_local",
                "ipv6_peer",
                "ipv4_address",
                "ipv4_netmask",
                "ipv6_address",
                "ipv6_prefixlen",
            ):
                if r.group(ip_k):
                    ifaces[ifname_last][ip_k] = r.group(ip_k)

        for ifname, ifparams in ifaces.items():
            if ifname not in wanted_interfaces:
                continue
            local_address = None
            remote_address = None
            # Find out local and remote address of the interface in order of preference.
            # Keep only one address family for pinging, prefer IPv6.
            if "ipv6_address" in ifparams and "ipv6_prefixlen" in ifparams:
                # VLAN or routed tunnel - use IPv6
                temp = IPv6Interface(
                    f"{ifparams['ipv6_address']}/{ifparams['ipv6_prefixlen']}"
                )
                local_address = temp.ip
                if local_address == (temp.network.network_address + 1):
                    remote_address = temp.ip + 1
                elif local_address == (temp.network.network_address + 2):
                    remote_address = temp.ip - 1
                # else can't figure out peer
            elif "ipv4_address" in ifparams and "ipv4_netmask" in ifparams:
                # VLAN or routed tunnel - use IPv4
                # Convert 0xfffffffc to integer, then to IPv4 address,
                # then to string.  Maybe it's time we stop using human-readable
                # programs like ifconfig to feed data into computer programs.
                dec_mask = str(IPv4Address(int(ifparams.get("ipv4_netmask"), 16)))
                temp = IPv4Interface(f"{ifparams['ipv4_address']}/{dec_mask}")
                local_address = temp.ip
                if local_address == (temp.network.network_address + 1):
                    remote_address = temp.ip + 1
                elif local_address == (temp.network.network_address + 2):
                    remote_address = temp.ip - 1
            elif "ipv6_local" in ifparams and "ipv6_peer" in ifparams:
                local_address = IPv6Address(ifparams["ipv6_local"])
                remote_address = IPv6Address(ifparams["ipv6_peer"])
            elif "ipv4_local" in ifparams and "ipv4_peer" in ifparams:
                local_address = IPv4Address(ifparams["ipv4_local"])
                remote_address = IPv4Address(ifparams["ipv4_peer"])
            # Else silently ignore.
            # Nagios will complain for the interface not being checked.

            if local_address and remote_address:
                cls.all_interfaces.append(cls(ifname, local_address, remote_address))

        return cls.all_interfaces

    @classmethod
    def measure_latency(cls, count: int):
        ret = {}

        # fping takes remote addresses as arguments and then displays the results
        # per address. Crete a dict to translate the results back to interfaces.
        ip_addresses = {}
        for iface in cls.all_interfaces:
            ip_addresses[str(iface.remote_address)] = iface.name

        # Ensure that all probes fit in 9 seconds, even if they fail.
        # 10 seconds is nrpe execution limit.
        period = 1000
        if count * period > 9000:
            period = 9000 // count

        try:
            lines = check_output(
                ["/usr/bin/fping", "-p", str(period), "-q", "-c", str(count)]
                + list(ip_addresses.keys()),
                universal_newlines=True,
                stderr=STDOUT,
            )
        except CalledProcessError as e:
            if e.returncode == 1:
                lines = e.output
            else:
                raise

        for line in lines.splitlines():
            r = FPING_RE.match(line)
            ret_key = ip_addresses[r.group("ip_address")]
            ret[ret_key] = {
                "percent_loss": float(r.group("percent_loss")),
                "avg_ping": None,  # Interfaces with 100% packet loss have no avg_ping.
            }
            if r.groupdict().get("avg_ping"):
                ret[ret_key]["avg_ping"] = float(r.group("avg_ping"))

        return ret


class NagiosCodes(IntEnum):
    OK = 0
    WARNING = 1
    CRITICAL = 2
    UNKNOWN = 3


if __name__ == "__main__":
    main()
