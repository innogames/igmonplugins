#!/usr/bin/env python
#
# Nagios memcached miss ratio check
#
# This is a Nagios script which checks if the number of cachemisses
# exceeds a given percent value. Different commandos can be checked
#
# Copyright (c) 2016, InnoGames GmbH
#

import os
import memcache
import time

from argparse import ArgumentParser


def parse_args():
    parser = ArgumentParser()
    parser.add_argument('--check_get',             type=bool, default=True,  help="")
    parser.add_argument('--check_delete',          type=bool, default=True,  help="")
    parser.add_argument('--check_incr',            type=bool, default=False, help="")
    parser.add_argument('--check_decr',            type=bool, default=False, help="")
    parser.add_argument('--check_cas',             type=bool, default=False, help="")
    parser.add_argument('--check_touch',           type=bool, default=False, help="")
    parser.add_argument('--hit_threshold',         type=int,  default=0,     help="") # TODO find good threshold
    parser.add_argument('--warning_misses_limit',  type=int,  default=30,    help="")
    parser.add_argument('--critical_misses_limit', type=int,  default=50,    help="")

    return vars(parser.parse_args())

# Get all stats from the local memcached server
def get_stats():
    host = memcache._Host('127.0.0.1:11211')
    host.connect()
    host.send_cmd('stats')
    stats = {}
    while 1:
        line = host.readline().split(None, 2)
        if line[0] == "END": break
        stat, key, value = line
        try:
            value = int(value)
        except ValueError:
            pass
        stats[key] = value
    host.close_socket()

    return stats

# Calculate for a given value how much percent were misses in the last second
def check_value(value, hit_threshold, old_stats, new_stats):
    misses_percent = 0

    # we will ignore values who had not a minimum of hits, as the cache is propably warming update
    # maybe we have to change this to catch errors where the cache is always missed
    if new_stats[value + '_hits'] >= hit_threshold:
        hits_count   = new_stats[value + '_hits']   - old_stats[value + '_hits']
        misses_count = new_stats[value + '_misses'] - old_stats[value + '_misses']

        # work around if there were no hits in the last second
        if hits_count > 0:
            misses_percent = ( misses_count / hits_count ) * 100
        else:
            if misses_count > 0:
                misses_percent = 100

    return misses_percent


def main(check_get, check_delete, check_incr, check_decr, check_cas, check_touch, hit_threshold, warning_misses_limit, critical_misses_limit):
    # get stats one second apart to calculate current miss ratio
    old_stats = get_stats()
    time.sleep(1)
    new_stats = get_stats()

    maximum_misses_value = 0
    list_failed_checks = ''

    # if the warning limit is higher than the critical limit we will ignore it    
    if warning_misses_limit > critical_misses_limit:
        warning_misses_limit == critical_misses_limit

    # now we check for all activted values if they miss more percent than the warning limit
    if check_get:
        misses_value = check_value('get', hit_threshold, old_stats, new_stats)
        # if the percent is higher than the limit, set the maximum misses value the higher of the old
        # or the current value and add the checked value to the list of failed values
        if misses_value > warning_misses_limit:
            maximum_misses_value = max(maximum_misses_value, misses_value)
            list_failed_checks += " GET"

    if check_delete:
        misses_value = check_value('delete', hit_threshold, old_stats, new_stats)
        if misses_value > warning_misses_limit:
            maximum_misses_value = max(maximum_misses_value, misses_value)
            list_failed_checks += " DELETE"

    if check_incr:
        misses_value = check_value('incr', hit_threshold, old_stats, new_stats)
        if misses_value > warning_misses_limit:
            maximum_misses_value = max(maximum_misses_value, misses_value)
            list_failed_checks += " INCR"

    if check_decr:
        misses_value = check_value('decr', hit_threshold, old_stats, new_stats)
        if misses_value > warning_misses_limit:
            maximum_misses_value = max(maximum_misses_value, misses_value)
            list_failed_checks += " DECR"

    if check_cas:
        misses_value = check_value('cas', hit_threshold, old_stats, new_stats)
        if misses_value > warning_misses_limit:
            maximum_misses_value = max(maximum_misses_value, misses_value)
            list_failed_checks += " CAS"

    if check_touch:
        misses_value = check_value('touch', hit_threshold, old_stats, new_stats)
        if misses_value > warning_misses_limit:
            maximum_misses_value = max(maximum_misses_value, misses_value)
            list_failed_checks += " TOUCH"
    
    # check if the worst value is higher than the critical limit
    if maximum_misses_value > critical_misses_limit:
        print ("CRITCAL - " + list_failed_checks)
        return 2
    # check if the worst value is higher than the warning limit
    if maximum_misses_value > warning_misses_limit:
        print ("WARNING - " + list_failed_checks)
        return 1

    # if we reach this point everthing should(tm) be ok
    print ("OK")
    return 0


if __name__ == '__main__':
    main(**parse_args())
