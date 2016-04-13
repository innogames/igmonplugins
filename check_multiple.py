#!/usr/bin/env python

import argparse
import subprocess
import sys

parser = argparse.ArgumentParser(description='Executes origin_command as many times with an element of iterate_over as iterate_over passed')
parser.add_argument('origin_command', help='Queue list separated by space. e.g. "queue1 queue2"')
parser.add_argument('iterate_over', nargs='+', help='Original command with base params. e.g. "check_rabbitmq_queue --vhost=events -H localhost --port=15672 -u user -p pass --warning=50 --critical=100 --queue"')
args=parser.parse_args()

exit_code = 0
message = ''
subs = {}

for q in args.iterate_over:
    subs[q] = subprocess.Popen(args.origin_command + ' ' + q , stdout=subprocess.PIPE, shell=True)

for q, p in subs.iteritems():
    out, err = p.communicate()
    if p.returncode != 0:
        exit_code = 2
        message += out + '\n'

if not message:
    print 'Everything is fine'
else:
    print 'Found some problems:\n' + message

sys.exit(exit_code)
