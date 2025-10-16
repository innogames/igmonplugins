#!/usr/bin/env python3

"""InnoGames Monitoring Plugins - Check network links on Linux, Cumulus and FreeBSD

Copyright (c) 2025 InnoGames GmbH
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

import json
import platform
import socket
import subprocess

from argparse import ArgumentParser
from datetime import datetime
from enum import Enum
from os import path

# nsca uses End of Transmission Block between records
NSCA_RECORD_SEPARATOR = chr(23)


def parse_args():
    ret = ArgumentParser()
    ret.add_argument(
        "--warning",
        type=int,
        help="Warning threshold for errors per second",
        default=0,
    )
    ret.add_argument(
        "--critical",
        type=int,
        help="Critical threshold for errors per second",
        default=0,
    )
    ret.add_argument(
        "--devd",
        action="store_true",
        help="Increment carrier_down_count in saved state, for use with FreeBSD devd",
    )
    ret.add_argument(
        "-H",
        "--nsca-host",
        action="append",
        dest="nsca_hosts",
        metavar="HOST",
        help="Send results to given NSCA host, can be specified multiple times",
    )
    ret.add_argument(
        "interfaces",
        nargs="+",
        help="Interfaces to check",
    )
    return ret.parse_args()


def main():
    args = parse_args()

    if args.devd:
        for interface in args.interfaces:
            devd_increase_carrier_down(interface)
        return

    hostname = socket.gethostname()

    text_results = []
    nsca_results = []

    for interface in args.interfaces:
        try:
            cur_state = InterfaceState.from_system(interface)
            try:
                prev_state = InterfaceState.from_json(interface)
            except FileNotFoundError:
                prev_state = cur_state

            nagios, result = cur_state.get_nagios_state(
                prev_state, args.warning, args.critical
            )
        except InterfaceStateException as e:
            nagios = NagiosCodes.UNKNOWN
            result = f"Failed to read interface data: {e}"

        text_results.append(f"{interface}: {nagios.name} {result}")
        nsca_results.append(
            f"{hostname}\tinterface_{interface}\t{nagios.value}\t{result}"
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


def devd_increase_carrier_down(interface: str):
    """Increment carrier_down_count in saved state file for FreeBSD devd"""
    try:
        state = InterfaceState.from_json(interface)
        state.prev_carrier_down_count = state.carrier_down_count
    except FileNotFoundError:
        state = InterfaceState(interface)

    state.carrier_down_count += 1
    state.to_json()


class InterfaceStats:
    """Statistics for network interface errors"""

    def __init__(self):
        self.rx_errors = 0  # Errors below + any other
        self.rx_length_errors = 0  # Number of packets dropped due to invalid length.
        self.rx_crc_errors = 0  # Number of packets received with a CRC error.
        self.rx_frame_errors = 0  # Receiver frame alignment errors.
        self.tx_errors = 0  # Errors below + any other
        self.tx_aborted_errors = 0  # Errors below
        self.tx_carrier_errors = 0  # Number of frame transmission errors due to loss of carrier during transmission
        self.tx_fifo_errors = 0  # Number of frame transmission errors due to device FIFO underrun / underflow.
        self.tx_heartbeat_errors = (
            0  # Number of Heartbeat / SQE Test errors for old half-duplex Ethernet.
        )
        self.tx_window_errors = (
            0  # Number of frame transmission errors due to late collisions
        )


class InterfaceState:
    """Class to represent the current state of a network interface"""

    def __init__(self, interface):
        self.interface = interface
        self.carrier = 0
        self.carrier_down_count = 0
        self.prev_carrier_down_count = 0  # Only used on FreeBSD
        self.stats = InterfaceStats()
        self.timestamp = datetime.now()

    @classmethod
    def from_system(cls, interface: str):
        """Create InterfaceState by reading from the system"""
        state = cls(interface)

        if platform.system() == "Linux":
            state._read_linux(interface)
        elif platform.system() == "FreeBSD":
            state._read_freebsd(interface)
        else:
            raise RuntimeError(f"Unsupported operating system: {platform.system()}")

        return state

    @classmethod
    def from_json(cls, interface: str):
        """Load a previous state from a JSON file"""
        with open(f"/tmp/check_interfaces_{interface}.json", "r") as prev_file:

            state = cls(interface)
            state.stats = InterfaceStats()

            prev_data = json.load(prev_file)
            for key, value in prev_data.items():
                if key == "timestamp":
                    state.timestamp = datetime.strptime(value, "%Y-%m-%d %H:%M:%S.%f")
                elif key in vars(state.stats):
                    setattr(state.stats, key, value)
                else:
                    setattr(state, key, value)

            return state

    def _read_linux(self, interface: str):
        """Read interface data from Linux sysfs"""
        if not path.isdir(f"/sys/class/net/{interface}"):
            raise InterfaceStateException("Interface does not exist")

        for param in ("carrier", "carrier_down_count"):
            with open(f"/sys/class/net/{interface}/{param}", "r") as interface_file:
                for line in interface_file:
                    setattr(self, param, int(line))

        # Check for errors related to the l1 network link.
        # Skip errors related to things like buffers, interrupts and such.
        for param in vars(self.stats):
            with open(
                f"/sys/class/net/{interface}/statistics/{param}", "r"
            ) as interface_file:
                for line in interface_file:
                    setattr(self.stats, param, int(line))

        # On Linux rx_errors and tx_errors contain detailed errors and any other errors
        self.stats.rx_errors = (
            self.stats.rx_errors
            - self.stats.rx_length_errors
            - self.stats.rx_crc_errors
            - self.stats.rx_frame_errors
        )

        self.stats.tx_errors = (
            self.stats.tx_errors
            - self.stats.tx_carrier_errors
            - self.stats.tx_fifo_errors
            - self.stats.tx_heartbeat_errors
            - self.stats.tx_window_errors
        )

    def _read_freebsd(self, interface: str):
        """Read interface data from FreeBSD"""
        try:
            result = subprocess.run(
                ["ifconfig", interface], capture_output=True, text=True, check=True
            )

            if "status: active" in result.stdout:
                self.carrier = 1
            elif "status: no carrier" in result.stdout:
                self.carrier = 0

        except subprocess.CalledProcessError:
            raise InterfaceStateException("Interface does not exist")

        # Get network statistics using netstat with libxo JSON output
        result = subprocess.run(
            ["netstat", "--libxo=json", "-I", interface, "-b"],
            capture_output=True,
            text=True,
            check=True,
        )
        netstat_data = json.loads(result.stdout)

        stats_found = False
        if "statistics" in netstat_data and "interface" in netstat_data["statistics"]:
            for iface in netstat_data["statistics"]["interface"]:
                if iface.get("name") == interface:
                    self.stats.rx_errors = iface["received-errors"]
                    self.stats.tx_errors = iface["send-errors"]
                    stats_found = True
                    break

        if not stats_found:
            raise InterfaceStateException(
                f"No statistics for this interface in netstat"
            )

        # FreeBSD doesn't provide the same granular error breakdown as Linux
        # The detailed counters remain at their default 0 values from InterfaceStats.__init__
        # There is also no carrier_down_count, this will be increased by running this
        # script from devd.

    def to_json(self):
        """Save the current state to a JSON file"""
        state_dict = {
            "carrier": self.carrier,
            "carrier_down_count": self.carrier_down_count,
            "prev_carrier_down_count": self.prev_carrier_down_count,
            "timestamp": str(self.timestamp),
        }
        # Add all stats attributes
        for attr in vars(self.stats):
            state_dict[attr] = getattr(self.stats, attr)

        with open(f"/tmp/check_interfaces_{self.interface}.json", "w") as state_file:
            json.dump(state_dict, state_file)

    def get_nagios_state(self, prev_state, warning: int, critical: int):
        """Calculate Nagios state by comparing this state with previous state"""

        ret = NagiosCodes.OK, "Link is up"

        if platform.system() == "FreeBSD":
            # On FreeBSD carrier_down_count is not provided by the OS. We must compare
            # values loaded from json. Those were increased by devd hook.
            prev_carrier_down_count = prev_state.prev_carrier_down_count
            cur_carrier_down_count = prev_state.carrier_down_count
        else:
            # On Linux we compare the value loaded from json with the current one
            # read from system.
            prev_carrier_down_count = prev_state.carrier_down_count
            cur_carrier_down_count = self.carrier_down_count

        if cur_carrier_down_count > prev_carrier_down_count:
            ret = NagiosCodes.CRITICAL, "Link has flapped"

        if self.carrier != 1:
            ret = NagiosCodes.CRITICAL, "Link is down"

        if prev_state.timestamp:
            delta_t = (self.timestamp - prev_state.timestamp).total_seconds()
            if delta_t > 0:  # Can't analyze counters for the 1st run
                for error_counter in vars(self.stats):
                    per_second = (
                        getattr(self.stats, error_counter)
                        - getattr(prev_state.stats, error_counter)
                    ) / delta_t
                    if warning and per_second > warning:
                        ret = (
                            NagiosCodes.WARNING,
                            f"Error counter {error_counter} {per_second}/s is above threshold!",
                        )
                    if critical and per_second > critical:
                        ret = (
                            NagiosCodes.CRITICAL,
                            f"Error counter {error_counter} {per_second}/s is above threshold!",
                        )

        self.carrier_down_count = cur_carrier_down_count
        self.prev_carrier_down_count = cur_carrier_down_count
        self.to_json()

        return ret


class NagiosCodes(Enum):
    OK = 0
    WARNING = 1
    CRITICAL = 2
    UNKNOWN = 3


class InterfaceStateException(Exception):
    pass


if __name__ == "__main__":
    main()
