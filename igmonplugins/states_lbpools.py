#!/usr/bin/env python
"""InnoGames Monitoring Plugins - Load Balancing Pools' States Check

Copyright (c) 2017 InnoGames GmbH
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
import subprocess

def main():
    debug = False
    lbpools = get_lbpools()
    pfctl_output, err = subprocess.Popen(['sudo', 'pfctl', '-vsr'], stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
    send_msg = ''
    if debug:
        separator = "\n"
    else:
        separator = "\27"

    for nagios_service in ['states_lbpool_4', 'states_lbpool_6']:
        send_msg += check_states(lbpools, pfctl_output, nagios_service, separator)

    if debug:
        print(send_msg)
    else:
        for monitor in ('af-monitor.admin.ig.local', 'aw-monitor.ig.local'):
            nsca = subprocess.Popen(
                [
                    '/usr/local/sbin/send_nsca',
                    '-H', monitor,
                    '-to', '20',
                    '-c', '/usr/local/etc/nagios/send_nsca.cfg',
                ],
                stdin=subprocess.PIPE,
            )
            nsca.communicate(send_msg)

def get_lbpools():
    with open('/etc/iglb/iglb.json') as jsonfile:
        lbpools_obj = json.load(jsonfile)['lbpools']
    return lbpools_obj

def get_allow_from_acls(lb_params):
    # The allow_from field of every lbpool has a number of acl objects with each having its own dedicated state_limit
    ret = {}
    for acl_name, acl_params in lb_params['allow_from'].items():
        ret.update({
            acl_name: acl_params['acls'][-1].strip("acl_ipaddr_dns")
        })
    return ret


def compare_states(line, output_pfctl_list, index, lb_params, allow_from, nagios_service, exit_code):
    cur_protocol = line.split('::')[-2].split(":")[-1]
    cur_port = line.split('::')[-1].strip('"')
    cur_states = int(output_pfctl_list[(index + 1)].strip('[] ', ).split('States:')[1].strip())
    status = ''
    ret = ' '
    if cur_protocol in line:
        if cur_port in line:
            if not lb_params['state_limit']:
                # The default limit set in pf.conf
                lb_params['state_limit'] == 1200000

            if cur_states >= (int(lb_params['state_limit']) * 0.85):
                exit_code = 2
            elif cur_states >= (int(lb_params['state_limit']) * 0.70):
                if exit_code != 2: # If already critical, then don't make it warning by other ports/acls
                    exit_code = 1
            elif cur_states < int(lb_params['state_limit'] * 0.70):
                if exit_code not in [1, 2]: # If already critical/warning, then don't make it ok by other ports/acls
                    exit_code = 0

            # To bind the ports to their acl objects, every port has state_limit set separately for each
            # acl object in allow_from attribute
            for acl_name, acl_object_id in allow_from.items():
                if acl_object_id in line:
                    status += '{} Port {} = {}, '.format(acl_name, cur_port, cur_states)
            ret += status
    return ret, exit_code


def check_states(lbpools, pfctl_output, nagios_service, separator):
    msg = ''
    for lbpool, lb_params in lbpools.items():
        status_changed = False
        statuses = 'States: '
        exit_code = None
        output_pfctl_list = pfctl_output.splitlines()
        allow_from = get_allow_from_acls(lb_params)

        for line in output_pfctl_list:
            indx = output_pfctl_list.index(line)
            if lb_params['pf_name'] in line and not ('dns' in line):
                if 'inet6' not in line and nagios_service == 'states_lbpool_4':
                    cmp_out, exit_code = compare_states(line, output_pfctl_list, indx, lb_params, allow_from, nagios_service, exit_code)
                    statuses += cmp_out
                    status_changed = True
                elif 'inet6' in line and nagios_service == 'states_lbpool_6':
                    cmp_out, exit_code = compare_states(line, output_pfctl_list, indx, lb_params, allow_from, nagios_service, exit_code)
                    statuses += cmp_out
                    status_changed = True

        if status_changed:
            if exit_code == 0:
                statuses = 'Everything is ok | {}'.format(statuses)
            elif exit_code == 1:
                statuses = 'State limit is reaching 85% | {}'.format(statuses)
            elif exit_code == 2:
                statuses = 'State limit has reached 85% | {}'.format(statuses)

            msg += ('{}\t{}\t{}\t{}{}').format(lbpool, nagios_service, exit_code, statuses, separator)
    return msg

if __name__ == "__main__":
    main()