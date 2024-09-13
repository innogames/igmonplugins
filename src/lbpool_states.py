#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Load Balancing Pools' States Check

Copyright (c) 2021 InnoGames GmbH
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

import json, subprocess, re, tempfile
from argparse import ArgumentParser
from collections import defaultdict
from datetime import datetime
from os import rename, chmod

POOL_RE = re.compile(r"(pool_[\d]+)_")
STATES_RE = re.compile("States: ([\d]+)")


def args_parse():
    parser = ArgumentParser()

    parser.add_argument(
        "-H",
        dest="nsca_srv",
        action="append",
        help="Nagios servers to report the results to",
    )

    parser.add_argument(
        "-g",
        dest="hwlb_group",
        help="HWLB Group to send results to",
    )

    parser.add_argument(
        "-w",
        "--warning",
        dest="warning",
        type=int,
        default=70,
        help="Warning threshold in percentage, default 70",
    )

    parser.add_argument(
        "-c",
        "--critical",
        dest="critical",
        type=int,
        default=85,
        help="Critical threshold in percentage, default 85",
    )

    parser.add_argument(
        "--prefix",
        dest="prefix",
        type=str,
        default="network.lbpools",
        help="Graphite path prefix",
    )

    return parser.parse_args()


def main():
    args = args_parse()

    if args.hwlb_group:
        nagios_service = "lbpool_states_" + args.hwlb_group
    else:
        nagios_service = "lbpool_states"

    carp_states = get_carp_states()
    current_states = get_current_states()
    default_state_limit = get_state_limit()
    lbpools_configs = get_lbpools_config()

    lbpools_states = {}
    for lbpool_name, lbpool_params in lbpools_configs.items():

        # Skip things which are not real LB Pools
        if not (lbpool_params["protocol_port"] and lbpool_params["nodes"]):
            continue

        # Skip LB Pools with no corresponding MASTER carp
        route_network = ""
        for lbnode_params in lbpool_params["nodes"].values():
            route_network = lbnode_params["route_network"]
        if not carp_states[route_network]:
            continue

        lbpools_states[lbpool_name] = {
            "state_limit": (
                lbpool_params["state_limit"]
                if lbpool_params["state_limit"]
                else default_state_limit
            ),
            "cur_states": current_states[lbpool_params["pf_name"]],
        }

    if not args.nsca_srv:
        separator = "\n"
    else:
        separator = "\27"

    send_msg = check_states(
        lbpools_states, nagios_service, separator, args.warning, args.critical
    )

    # Send metrics to grafana via helper
    grafana_msg = send_grafsy(lbpools_states, args.prefix)

    if not args.nsca_srv:
        print(send_msg)
        print(grafana_msg)
    else:

        for monitor in args.nsca_srv:
            nsca = subprocess.Popen(
                [
                    "/usr/local/sbin/send_nsca",
                    "-H",
                    monitor,
                    "-to",
                    "20",
                    "-c",
                    "/usr/local/etc/nagios/send_nsca.cfg",
                ],
                stdin=subprocess.PIPE,
            )
            nsca.communicate(send_msg.encode())


def get_carp_states():
    ret = {}
    with open("/var/run/iglb/carp_state.json") as carp_states_file:
        carp_states = json.load(carp_states_file)
        for network_name, network_params in carp_states.items():
            ret[network_name] = carp_states[network_name]["carp_master"]

    return ret


def get_lbpools_config():
    config = "/etc/iglb/lbpools.json"

    with open(config) as jsonfile:
        return json.load(jsonfile)


def check_states(lbpools_states, nagios_service, separator, warn, crit):
    """Compare the current states of each lbpool and compute results"""

    msg = ""

    for lbpool_name, lbpool_params in lbpools_states.items():
        status = ""
        exit_code = local_exit_code = 0
        state_limit = lbpool_params["state_limit"]
        critical = state_limit * (crit * 0.01)
        warning = state_limit * (warn * 0.01)
        cur_states = lbpool_params["cur_states"]

        if cur_states >= critical:
            local_exit_code = 2
            status = f"Used states are above {crit}% of states limit | "

        elif cur_states >= warning:
            local_exit_code = 1
            status = f"Number of states are above {warn}% of states limit | "

        if exit_code < local_exit_code:
            exit_code = local_exit_code

        if exit_code == 0:
            status = f"Used states are below the thresholds | "

        status += f"limit={state_limit}, current={cur_states}"

        msg += f"{lbpool_name}\t{nagios_service}\t{exit_code}\t{status}{separator}"

    return msg


def get_state_limit():
    # The default limit set in pf.conf, fetch it from what is loaded in pf
    default_limits = subprocess.run(
        ["sudo", "pfctl", "-sm"],
        capture_output=True,
        text=True,
    ).stdout.splitlines()

    for line in default_limits:
        if "states" in line:
            return int(line.split(" ")[-1])


def get_current_states():
    """
    Get pf ruleset including all anchors, look for route-to rules and get
    the amount of states associated with each rule. Identify LB Pool name
    for each rule and store the largest amount of states per LB Pool.
    """

    pfctl_output = subprocess.run(
        ["sudo", "pfctl", "-vsr", "-a*"],
        capture_output=True,
        text=True,
    ).stdout.splitlines()

    ret = defaultdict(int)
    for idx, line in enumerate(pfctl_output):
        if "route-to" not in line:
            continue
        lbpool_name = POOL_RE.search(line).group(1)
        last_states = int(STATES_RE.search(pfctl_output[(idx + 1)]).group(1))
        if last_states > ret[lbpool_name]:
            ret[lbpool_name] = last_states

    return ret


def send_grafsy(data, prefix):
    "For sending the results to grafana"

    output = ""
    ts = datetime.utcnow().strftime("%s")

    for k1, v1 in data.items():
        k1 = k1.replace(".", "_")
        for k2, v2 in v1.items():
            output += f"{prefix}.{k1}.{k2} {v2} {ts}\n"

    with tempfile.NamedTemporaryFile("w", delete=False) as tmpfile:
        tmpfile.write(output)
        tmpname = tmpfile.name
        chmod(tmpname, 0o644)

    grafsy_file = "/tmp/grafsy/" + tmpname.split("tmp/")[1]
    # We want Atomicity for writing files to grafsy
    rename(tmpname, grafsy_file)

    return output


if __name__ == "__main__":
    main()
