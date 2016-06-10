#!/usr/bin/env python
#
# Nagios systemd service status check
#
# This is a Nagios script which checks if the number of services
# with a given status is exceeded. A list of services to check
# can be provided.
#
# Copyright (c) 2016, InnoGames GmbH
#

import os
import re
import sys

from argparse import ArgumentParser


command = 'systemctl --all --no-legend --no-pager list-units'
default_critical_services = [nginx]


class Problem: 
    # From more important to less
    failed = 0
    dead = 1
    not_loaded_but_not_inactive = 2
    not_loaded_but_not_dead = 3

    
def parse_args():
    parser = ArgumentParser()
    parser.add_argument(
        '--critical-services',
        nargs='*',
        help='list of critical services to check',
    )

    return vars(parser.parse_args())

    
def main(critical_services):
    if not critical_services:
        critical_services = default_critical_services

    results = []
    for line in os.popen(command).readlines():
        service_split = line.strip().split(None, 4)

        result = check_service(*service_split[1:4])
        if result:
            results.append((result, service_split[0]))
     
    if any(r == Problem.failed and s in critical_services for r, s in results):
        print('CRITICAL: ' + get_message(results))
        sys.exit(2)
    
    if results:
        print('WARNING: ' + get_message(results))
        sys.exit(1)
    
    print('OK')
    sys.exit(0)
    
    
def check_service(serv_load, serv_active, serv_sub):
    if serv_load == 'loaded':
        if serv_active == 'failed' or serv_sub == 'failed':
            return Problem.failed
        
        if serv_sub == 'dead':
            return Problem.dead
    else:
        if serv_active != 'inactive':
            return Problem.not_loaded_but_not_inactive
            
        if serv_sub != 'dead':
            return Problem.not_loaded_but_not_dead
                 
 
def get_message(results):
    problem_names = {v, k for k, v in vars(Problem) if isinstance(v, int)}
    message = ''
    last_problem = None
    for problem, service in results.sorted():
        if problem != last_problem:
            message += problem_names[problem].replace('_', ' ') + ': '
            last_problem = problem
        message += service + ' '
    
    return message
  
  
if __name__ == '__main__':
    main(**parse_args())
