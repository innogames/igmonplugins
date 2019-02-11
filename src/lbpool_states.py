#!/usr/bin/env python
"""InnoGames Monitoring Plugins - Load Balancing Pools' States Check

Copyright (c) 2019 InnoGames GmbH
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
import imp, json, subprocess, re
from os.path import exists
from sys import exit

nagios_service = 'lbpool_states'


def main():
    carps = check_carps()

    # Don't run any further if there are no MASTER carps on this hwlb
    carp_master = False
    for k, v in carps.items():
        carp_master = (carp_master | v['carp_master'])

    if not carp_master:
        print("The check is run only when there is a MASTER CARP")
        return

    args = args_parse()

    pfctl_output, err = subprocess.Popen(['sudo', 'pfctl', '-vsr'],
                                         stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE).communicate()

    # The default limit set in pf.conf, fetch it from what is loaded in pf
    default_limits, err1 = subprocess.Popen(['sudo', 'pfctl', '-sm'],
                                            stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE).communicate()

    states_dict = pfctl_parser(pfctl_output)

    lbpools = get_lbpools()

    lbpools = {
        lbname: {
            'state_limit': lb_params['state_limit'],
            'cur_states': int(states_dict[lb_params['pf_name']]['cur_states']),
            'carp_master': carp_status['carp_master'],
        }
        for vlan, carp_status in carps.items()
        for lbname, lb_params in lbpools.items()
        if (lb_params['protocol_port'] and
            lb_params['nodes'] and
            lb_params['pf_name'] in states_dict and
            lb_params['vlan'] == int(vlan)
            )
        }

    # Hard state limit is always printed in first line
    default_limit_lines = default_limits.decode().splitlines()

    for line in default_limit_lines:
        if "states" in line:
            default_state_limit = int(
                ''.join(default_limit_lines).split(' ')[-1])

    if not args.nsca_srv:
        separator = "\n"
    else:
        separator = "\27"

    send_msg = check_states(lbpools,
                            states_dict,
                            default_state_limit,
                            nagios_service,
                            separator,
                            args.warning,
                            args.critical
                            )

    if not args.nsca_srv:
        print(send_msg)
        print("\ndefault_state_limit is {}\n".format(default_state_limit))

    else:

        for monitor in args.nsca_srv:
            nsca = subprocess.Popen(
                [
                    '/usr/local/sbin/send_nsca',
                    '-H', monitor,
                    '-to', '20',
                    '-c', '/usr/local/etc/nagios/send_nsca.cfg',
                ],
                stdin=subprocess.PIPE,
            )
            nsca.communicate(send_msg.encode())


def args_parse():
    parser = ArgumentParser()

    parser.add_argument(
        '-H', dest='nsca_srv', action='append',
        help='Nagios servers to report the results to'
    )

    parser.add_argument(
        '-w', '--warning', dest='warning', type=int, default=70,
        help='Warning threshold in percentage, default 70'
    )

    parser.add_argument(
        '-c', '--critical', dest='critical', type=int, default=85,
        help='Critical threshold in percentage, default 85'
    )

    return parser.parse_args()


def check_carps():
    carps = {}
    configs = ['/etc/iglb/carp_settings.py', '/var/run/iglb/carp_state.json']

    if exists(configs[0]):

        carp_settings = imp.load_source(
            'carp_settings',
            '/etc/iglb/carp_settings.py'
        )

        for ifname in carp_settings.ifaces_carp.keys():
            vlan_tag = ifname.split('internal')[1]
            p = subprocess.Popen(
                ['/sbin/ifconfig', ifname],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )

            ifconfig, err = p.communicate()

            for line in ifconfig.decode().splitlines():
                # Find carp lines, the look like this:
                # carp: MASTER vhid 133 advbase 1 advskew 50
                ifconfig_match = re.match(
                    ".*carp: ([A-Z]+) vhid ([0-9]+) advbase.*",
                    line
                )

                if ifconfig_match:
                    status = ifconfig_match.group(1)
                    carps.update({
                        vlan_tag: {
                            'carp_master': True if status == 'MASTER' else False
                        }
                    })

    elif exists(configs[1]):

        with open(configs[1], 'r') as carp_statejson, \
                open('/etc/iglb/networks.json', 'r') as networkjson:
            carp_state = json.load(carp_statejson)
            network = json.load(networkjson)
            carps = {
                vn['vlan_tag']:
                    {
                        'carp_master': v['carp_master']
                    }
                for k, v in carp_state.items()
                for kn, vn in network['internal_networks'].items()
                if k == kn
                }

    return carps


def get_lbpools():
    # For allowing both old hwlb style configs and new ones
    configs = ['/etc/iglb/lbpools.json', '/etc/iglb/iglb.json']

    for config in configs:

        if exists(config):

            with open(config) as jsonfile:
                dict = json.load(jsonfile)

                if 'lbpools' in dict.keys():
                    lbpools_obj = dict['lbpools']
                else:
                    lbpools_obj = dict

    return lbpools_obj


def check_states(lbpools, states_dict, default_state_limit, nagios_service,
                 separator, warn, crit):
    """ Compare the current states of each lbpool and compute results """

    msg = ''

    for lbname, lb_params in lbpools.items():

        if lb_params['carp_master']:
            statuses = ''
            exit_code = local_exit_code = 0

            if lb_params['state_limit']:
                state_limit = int(lb_params['state_limit'])
            else:
                state_limit = default_state_limit
            critical = state_limit * (crit * 0.01)
            warning = state_limit * (warn * 0.01)
            cur_states = int(lb_params['cur_states'])

            if cur_states >= critical:
                local_exit_code = 2
                statuses += 'Used states are above {}% of states ' \
                            'limit | States limit: {}, Current states: {}'.format(
                    crit, state_limit, cur_states)
            elif cur_states >= warning:
                local_exit_code = 1
                statuses += 'Number of states are above {}% of states ' \
                            'limit | States limit: {}, Current states: {}'.format(
                    warn, state_limit, cur_states)

            if exit_code < local_exit_code:
                exit_code = local_exit_code

            if exit_code == 0:
                statuses = 'Used states are below the thresholds | ' \
                           'States limit: {}, Current states: {}'.format(
                    state_limit, cur_states)

            msg += ('{}\t{}\t{}\t{}{}').format(lbname, nagios_service,
                                               exit_code,
                                               statuses, separator
                                               )
    return msg


def pfctl_parser(pfctl_output):
    """
    For parsing pf output and create a dict containing the current max-states
    for every lbpool object
    """

    states_dict = {}
    output_pfctl_list = pfctl_output.decode().splitlines()
    for line in output_pfctl_list:
        indx = output_pfctl_list.index(line)
        if "route-to" in line:
            pool = re.search("(pool_\d{5,})(_)(\d)", line).group(1)
            new_states = int(
                output_pfctl_list[(indx + 1)].strip('[] ', ).split(
                    'States:')[1].strip()
            )
            if pool in states_dict.keys():
                if new_states > states_dict[pool]['cur_states']:
                    states_dict[pool] = {'cur_states': new_states}
            else:
                states_dict.update({
                    pool: {
                        'cur_states': new_states
                    }
                })

    return states_dict


if __name__ == "__main__":
    main()
