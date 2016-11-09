#!/usr/bin/env python

import subprocess
import sys
from argparse import ArgumentParser

parser = ArgumentParser(
    description='Executes origin_command as many times with an element of '
                'iterate_over as iterate_over passed')
parser.add_argument(
    'origin_command',
    help='Original command with base params. e.g. '
         '"check_rabbitmq_queue --vhost=events -H localhost --port=15672 '
         '-u user -p pass --warning=50 --critical=100 --queue"'
)
parser.add_argument('iterate_over', nargs='+',
                    help='Queue list separated by space. e.g. "queue1 queue2"')
args = parser.parse_args()

exit_code = 0
message = ''
subs = {}

for iterate_param in args.iterate_over:
    subs[iterate_param] = subprocess.Popen(
        args.origin_command + ' ' + iterate_param,
        stdout=subprocess.PIPE,
        shell=True)

for iterate_param, process in subs.iteritems():
    out, err = process.communicate()
    if process.returncode != 0:
        exit_code = 2
        message += '(' + iterate_param + '): ' + out + '\n'

if not message:
    print('Everything is fine')
else:
    print('Found some problems: ' + message.replace('\n', ' <> '))

sys.exit(exit_code)
