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

import ipaddress
import re
import sys

from argparse import ArgumentParser
from subprocess import check_output, STDOUT

IFCONFIG_RE = re.compile(
    r'^('
# gif_aw1_af1: flags=1008051<UP,POINTOPOINT,RUNNING,MULTICAST,LOWER_UP> metric 0 mtu 1418
        '(?P<ifname>[a-z0-9_]+): flags=[0-9a-f]+<(?P<flags>[A-Z_,]+)>|'
        '\tinet ('
# inet 192.0.2.1 --> 192.0.2.2 netmask 0xffffffff
            '(?P<ipv4_local>[0-9.]+) --> (?P<ipv4_peer>[0-9.]+)|'
# inet 192.0.2.1 netmask 0xfffffffc
            '(?P<ipv4_address>[0-9.]+) netmask (?P<ipv4_netmask>0x[0-9a-f]+)'
        ')|'
        '\tinet6 ('
# inet6 2001:db8::1 --> 2001:db8::2 prefixlen 128
            '(?P<ipv6_local>[0-9a-f:.]+) --> (?P<ipv6_peer>[0-9a-f:.]+)|'
# inet6 2001:db8::2 prefixlen 126
            '(?P<ipv6_address>[0-9a-f:.]+) prefixlen (?P<ipv6_netmask>[0-9]+)'
        ')'
    ')'
)

FPING_RE = re.compile(
# 192.0.2.1                           : xmt/rcv/%loss = 3/3/0%, min/avg/max = 8.31/8.71/9.49
    r'(?P<ip_address>[0-9a-f.:]+)\s+: '
    'xmt/rcv/%loss = [0-9]+/[0-9]+/(?P<percent_loss>[0-9]+)%, '
    'min/avg/max = [0-9.]+/(?P<avg_ping>[0-9.]+)/[0-9.]+'
)


class ExitCodes:
    ok = 0
    warning = 1
    critical = 2
    unknown = 3


def parse_args():
    parser = ArgumentParser()
    parser.add_argument('--warning-latency', type=int, default=200,
        help='Warning threshold for latency in ms')
    parser.add_argument('--critical-latency', type=int, default=300,
        help='Critical threshold for latency in ms')
    parser.add_argument('--warning-loss', type=int, default=20,
        help='Warning threshold for packet loss in percent')
    parser.add_argument('--critical-loss', type=int, default=50,
        help='Critical threshold for packet loss in percent')
    parser.add_argument('--count', type=int, default=10,
        help='Count of pings to send')
    return parser.parse_args()


def main():
    args = parse_args()
    ifaces_raw = get_interfaces()
    ifaces = parse_interfaces(ifaces_raw)
    result = measure_latency(ifaces, args.count)

    worst_latency = 0
    worst_latency_iface = None
    worst_loss = 0
    worst_loss_iface = None

    output_lines = []

    for ifname, ifdata in result.items():
        output_lines.append(
            f'{ifname}: {ifdata["avg_ping"]}ms latency, '
            f'{ifdata["percent_loss"]}% loss'
        )

        if ifdata['avg_ping'] > worst_latency:
            worst_latency = ifdata['avg_ping']
            worst_latency_iface = ifname

        if ifdata['percent_loss'] > worst_loss:
            worst_loss = ifdata['percent_loss']
            worst_loss_iface = ifname

    output_lines.insert(0,
        f'Worst tunnels: {worst_latency_iface} {worst_latency}ms latency, '
        f'{worst_loss_iface} {worst_loss}% loss'
    )

    exit_code = ExitCodes.ok

    if worst_latency >= args.warning_latency:
        exit_code = ExitCodes.warning
    if worst_loss >= args.warning_loss:
        exit_code = ExitCodes.warning
    if worst_latency >= args.critical_latency:
        exit_code = ExitCodes.critical
    if worst_loss >= args.critical_loss:
        exit_code = ExitCodes.critical

    print('\n'.join(output_lines))
    sys.exit(exit_code)


def get_interfaces():
    ret = {}
    ifname_last = ''
    for line in check_output(
            ['/sbin/ifconfig'],
            universal_newlines=True,
    ).splitlines():
        r = IFCONFIG_RE.match(line)

        if r is None:
            continue

        ifname_new = r.group('ifname')
        if ifname_new:
            ret[ifname_new] = {
                'flags': r.group('flags').split(',')
            }
            ifname_last = ifname_new
            continue

        if not ifname_last:
            continue

        for ip_k in (
            'ipv4_local', 'ipv4_peer',
            'ipv6_local', 'ipv6_peer',
            'ipv4_address', 'ipv4_netmask',
            'ipv6_address', 'ipv6_netmask',
        ):
            if r.group(ip_k):
                ret[ifname_last][ip_k] = r.group(ip_k)

    return ret


def parse_interfaces(ifaces_raw):
    ret = {}
    for ifname, ifparams in ifaces_raw.items():
        if 'POINTOPOINT' in ifparams['flags']:
            ret[ifname] = parse_p2p_iface(ifparams)
        elif ifname.startswith('wg_'):
            ret[ifname] = parse_subnet_iface(ifparams)

    return ret


def parse_p2p_iface(ifparams):
    ipv6 = ifparams.get('ipv6_peer')
    if ipv6:
        return ipv6
    ipv4 = ifparams.get('ipv4_peer')
    if ipv4:
        return ipv4
    return None


def parse_subnet_iface(ifparams):
    ip = None

    if ifparams.get("ipv6_address"):
        try:
            ipv6 = ipaddress.IPv6Interface(
                ifparams.get("ipv6_address") +
                '/' +
                ifparams.get("ipv6_netmask")
            )
        except (ipaddress.AddressValueError, ipaddress.NetmaskValueError):
            pass
        else:
            if ipv6.network.prefixlen >= 120:
                ip = ipv6

    elif ifparams.get("ipv4_address"):
        try:
            # Convert 0xfffffffc to integer, then to IPv4 address,
            # then to string.  Maybe it's time we stop using human-readible
            # programs like ifconfig to feed data into computer programs.
            ipv4 = ipaddress.IPv4Interface(
                ifparams.get("ipv4_address") + '/' + str(
                ipaddress.IPv4Address(int(ifparams.get("ipv4_netmask"), 16)))
            )
        except (ipaddress.AddressValueError, ipaddress.NetmaskValueError):
            pass
        else:
            if ipv4.network.prefixlen >= 24:
                ip = ipv4

    if not ip:
        return None

    ip1 = ip.network.network_address + 1
    ip2 = ip.network.network_address + 2

    if ip.ip == ip1:
        return str(ip2)
    elif ip.ip == ip2:
        return str(ip1)

    return None


def measure_latency(ifaces, count):
    ret = {}

    # fping will print results per IP address
    ip_addresses = {}
    for k, v in ifaces.items():
        ip_addresses[v] = k

    for line in check_output(
        ['/usr/bin/fping', '-q', '-c', str(count)] + list(ip_addresses.keys()),
        universal_newlines=True,
        stderr=STDOUT,
    ).splitlines():
        r = FPING_RE.match(line)

        ret[ip_addresses[r.group('ip_address')]] = {
            'percent_loss': float(r.group('percent_loss')),
            'avg_ping': float(r.group('avg_ping')),
        }

    return ret


if __name__ == '__main__':
    main()
