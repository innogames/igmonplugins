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
import json, subprocess, re
from os.path import exists
from sys import exit

nagios_service = 'lbpool_states'


def main():
    parser = ArgumentParser()
    parser.add_argument(
        '-H', dest='nsca_srv', nargs='+',
        help='Nagios servers to report the results to'
    )

    parser.add_argument(
        '-W', dest='warning', type=int, default=70,
        help='Warning threshold in percentage, default 70'
    )

    parser.add_argument(
        '-C', dest='critical', type=int, default=85,
        help='Critical threshold in percentage, default 85'
    )

    args = parser.parse_args()
    lbpools = get_lbpools()

    pfctl_output, err = subprocess.Popen(['sudo', 'pfctl', '-vsr'],
                                         stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE).communicate()

    # The default limit set in pf.conf, fetch it from what is loaded in pf
    default_limits, err1 = subprocess.Popen(['sudo', 'pfctl', '-sm'],
                                            stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE).communicate()

    states_dict = pfctl_parser(pfctl_output)

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
        print("\ndefault_state_limit is {}\n".format(default_state_limit))
        print(send_msg)
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


def get_lbpools():
    # For allowing both old hwlb style configs and new ones
    configs = ['/etc/iglb/lbpools.json', '/etc/iglb/iglb.json']
    for config in configs:
        if exists(config):
            try:
                with open(config) as jsonfile:
                    dict = json.load(jsonfile)
                    if 'lbpools' in dict.keys():
                        lbpools_obj = dict['lbpools']
                    else:
                        lbpools_obj = dict
            except IOError:
                print("Config file not found")
                exit(1)

    return lbpools_obj


def check_states(lbpools, states_dict, default_state_limit, nagios_service,
                 separator, warn, crit):
    """ Compare the current states of each lbpool and compute results """

    msg = ''
    for lbname, lb_params in lbpools.items():
        statuses = ''
        exit_code = local_exit_code = 0
        if lb_params['state_limit']:
            state_limit = int(lb_params['state_limit'])
        else:
            state_limit = default_state_limit
        lbpool = lb_params['pf_name']
        critical = state_limit * (crit * 0.01)
        warning = state_limit * (warn * 0.01)

        if not lb_params['default_snat'] and \
                lb_params['protocol_port'] and \
                lb_params['nodes'] and \
                lbpool in states_dict:  # To exclude those lbpools which have just
                                        # been made but not deployed

            cur_states = int(states_dict[lbpool]['cur_states'])

            if cur_states >= critical:
                local_exit_code = 2
                statuses += 'Used states are above {}% of states limit | Total states limit: {}, Current states: {}'.format(
                    crit, state_limit, cur_states)
            elif cur_states >= warning:
                local_exit_code = 1
                statuses += 'Number of states are above {}% of states limit | Total states limit: {}, Current states: {}'.format(
                    warn, state_limit, cur_states)

            if exit_code < local_exit_code:
                exit_code = local_exit_code

            if exit_code == 0:
                statuses = 'Used states are below the thresholds | Total states limit: {}, Current states: {}'.format(
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
        if "round-robin" in line:
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
