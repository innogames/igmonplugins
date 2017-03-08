#!/usr/bin/env python

import socket
import sys
from argparse import ArgumentParser

parser = ArgumentParser(description='Check haproxy lbpool up and running')
parser.add_argument('-i', '--ignore_warnings', dest='ignore_warnings',
                    action='store_true', default=False,
                    help='Ignore if some hosts under LBpool are down')
args = parser.parse_args()

haproxy_socket_path = '/tmp/haproxy'
exit_code = 0
try:
    haproxy_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    haproxy_socket.connect(haproxy_socket_path)

    haproxy_socket.send('show stat\n')

    f = haproxy_socket.makefile()
    lbpools = {}
    lbstatuses = {}
    status = ''

    for line in f.readlines():
        lbstatus = {}
        if line.startswith('#') or line == '\n':
            continue
        split = line.split(',')

        if split[1] == 'BACKEND':
            # Backend means we are at the end of haproxy output for this lbpool
            name = split[0]
            lbstatus = ''
            for key, value in lbstatuses.iteritems():
                lbstatus += (key + ' - ' + value + '; ')
            status = split[17]
            message = split[0] + ' - ' + split[17] + ': ' + lbstatus
            print(message)
            if status != 'UP':
                exit_code = 2

        elif len(split[1].split(':')) == 2:
            # If it is an ip - append it to dict of lbstatuses
            lbstatuses[split[1]] = split[17]
            # if any server under lbpool is down - print warning
            if split[17] != 'UP':
                if not args.ignore_warnings:
                    exit_code = 1


except:
    print('Error connecting to haproxy socket %s' % haproxy_socket_path)
    raise
    exit_code = 2

sys.exit(exit_code)
