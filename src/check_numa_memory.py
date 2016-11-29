#!/usr/bin/env python

import socket, sys, argparse

parser = argparse.ArgumentParser(description='Check free memory on all numa nodes')
parser.add_argument('-w', dest='warning',  type=int, required=True, help="Warning if less than given amount of MiB is free on any node.")
parser.add_argument('-c', dest='critical', type=int, required=True, help="Critical if less than given amount of MiB is free on any node.")
args=parser.parse_args()

def get_numa_nodes():
    # does not support offline nodes seperates with ','
    nodes = list()
    with open('/sys/devices/system/node/online') as f:
        line = f.readline().rstrip()
    if '-' in line:
        # range of nodes
        max = line.split('-')[1]
    # max is exclusive in range so plus 1
        nodes = range(0,int(max)+1)
    else:
        # We don't need stats for servers with only one node
        sys.exit(0)
    return nodes

if args.warning < args.critical:
    print 'Warning must not be smaller than critical!'
    sys.exit(3)

result = {}
exitcode = 0
nodes = get_numa_nodes()

for node in nodes:
    with open('/sys/devices/system/node/node{0}/meminfo'.format(node)) as f:
        lines = [line.strip().split() for line in f]
    stats = dict()
    for line in lines:
        stats[line[2].rstrip(':')] = int(line[3])
    # We consider file buffers to be usable memory,
    # as they can be flushed and freed.
    memfree = stats['MemFree'] + stats['FilePages']
    memfree /= 1024
    result[node] = 'Node {}: {} MiB free (with buffers)'.format(node, memfree)
    if memfree < args.warning:
        exitcode = 1
    if memfree < args.critical:
        exitcode = 2

# 1st line of output is the one shown in Nagios normal view.
if exitcode == 0:
    print 'All NUMA nodes have at least {} MiB free memory'.format(args.warning)
if exitcode == 1:
    print 'One of NUMA nodes has below {} MiB free memory!'.format(args.warning)
if exitcode == 2:
    print 'One of NUMA nodes has below {} MiB free memory!'.format(args.critical)

# Add more lines with detailed output.
for node in nodes:
    print result[node]

sys.exit(exitcode)
