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

from argparse import ArgumentParser


def parse_args():
    parser = ArgumentParser()
    parser.add_argument('-s', '--status_to_check', default='dead', help="which status should be checked")
    parser.add_argument('-w', '--warning_limit', default=1, type=int, help="limit for warning status")
    parser.add_argument('-c', '--critical_limit', default=1, type=int, help="limit for critical status")
    parser.add_argument('-l', '--services_to_check', default=[], nargs='*', help="list of services to check")

    return vars(parser.parse_args())


def main(status_to_check, warning_limit, critical_limit, services_to_check):

    number_servs_found = 0
    list_servs_found = ''

    # get all systemd services
    services = os.popen("systemctl --all --no-legend --no-pager list-units").read()
    service_list = services.splitlines()

    # iterate through all services and find the ones which match the status to check
    for service in service_list:
        # replace multiple whitespaces with single space
        service = re.sub( '\s+', ' ', service ).strip()
        serv_name, serv_load, serv_active, serv_sub, serv_desc = service.split(' ', 4)

        # do we have a list of services we should check?
        if services_to_check:
            # is the current service in the list we should check
            if serv_name.split(".")[0] in services_to_check:
                # is the the current service in the status we are checking
                if serv_sub == status_to_check:
                    number_servs_found += 1
                    list_servs_found += ' ' + serv_name
        # else we check all services
        else:
            # is the the current service in the status we are checking
            if serv_sub == status_to_check:
                number_servs_found += 1
                list_servs_found += ' ' + serv_name

    # if we have found more services than the critical limit return a critical statuscode
    # and print the number and list of services
    if number_servs_found >= critical_limit:
        print("CRITICAL - " + str(number_servs_found) + " services found with status " + status_to_check + " (" + list_servs_found + " )")
        return 2

    # if we have found more services than the warning limit return a warning statuscode
    # and print the number and list of services
    if number_servs_found >= warning_limit:
        print("WARNING - " + str(number_servs_found) + " services found with status " + status_to_check + " (" + list_servs_found + " )")
        return 1

    # only if the warning limit is smaller than the critical limit
    # we will use it for the status message
    if warning_limit < critical_limit:
        print("OK - not more or equal than " + str(warning_limit) + " services found with status " + status_to_check)
    else:
        print("OK - not more or equal than " + str(critical_limit) + " services found with status " + status_to_check)
    return 0

if __name__ == '__main__':
    main(**parse_args())