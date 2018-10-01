#!/usr/bin/env python
import json
import subprocess

debug = False

if debug:
    separator = "\n"
else:
    separator = "\27"

nagios_service = 'check_lbpool'

def get_lbpools():
    with open('/etc/iglb/iglb.json') as jsonfile:
        lbpools_obj = json.load(jsonfile)['lbpools']
    return lbpools_obj

def get_states():
   (out,err) = subprocess.Popen(['sudo', 'pfctl', '-vsr'], stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
   return out

lbpools = get_lbpools()
states  = get_states()
msg = ''

def get_allow_from_acls(lbpools):
    for lbpool, lb_params in lbpools.items():
        allow_from = {}
        for acl_name, acl_params in lb_params['allow_from'].items():
            allow_from.update({
                acl_params['acls'][-1].strip("acl_ipaddr"): acl_name
            })

for lbpool, lb_params in lbpools.items():
    statuses = 'States: '
    index = 0
    exit_code = None
    states_list = states.splitlines()

    # The allow_from field of every lbpool has a number of acl objects with each having its own dedicated state_limit
    allow_from = {}
    for acl_name, acl_params in lb_params['allow_from'].items():
        allow_from.update({
            acl_name: acl_params['acls'][-1].strip("acl_ipaddr")
        })

    for line in states_list:
        if lb_params['pf_label'] in line and not ('dns' in line) and not ('inet6' in line):
            cur_protocol = line.split('::')[-2].split(":")[-1]
            cur_port = line.split('::')[-1].strip('"')
            cur_states = states_list[(index+1)].strip('[] ',).split('States:')[1].strip()
            status = ''
            if cur_protocol in line:
                if cur_port in line:
                    if not lb_params['state_limit']:
                        lb_params['state_limit'] == 1200000
                    else:
                        if int(cur_states) < int(lb_params['state_limit']):
                            # If there was a state_limits reached on one of the previously checked ports of this lbpool,
                            # don't mark this lbpool as OK no matter if this current port has less states than limit
                            if exit_code != 2:
                                exit_code = 0
                        elif cur_states >= lb_params['state_limit']:
                            exit_code = 2

                        # To bind the ports to their acl objects, every port has state_limit set separately for each
                        # acl object in allow_from attribute
                        for acl_name, acl_object_id in allow_from.items():
                            if acl_object_id in line:
                                status += '{} Port {} = {}, '.format(acl_name, cur_port, cur_states)
                    statuses += status
        index += 1
    msg += ('{}\t{}\t{}\t{}{}').format(
                                 lbpool,
                                 nagios_service,
                                 exit_code,
                                 statuses,
                                 separator
                                 )

if debug:
    print msg
else:
    for monitor in ('af-monitor.admin', 'aw-monitor'):
        nsca = subprocess.Popen(
            [
                '/usr/local/sbin/send_nsca',
                '-H', '{}.ig.local.'.format(monitor),
                '-to', '20',
                '-c', '/usr/local/etc/nagios/send_nsca.cfg',
            ],
            stdin=subprocess.PIPE,
        )
        nsca.communicate(msg)
