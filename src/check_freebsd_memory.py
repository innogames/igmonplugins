#!/usr/bin/env python
#
# InnoGames Monitoring Plugins - check_freebsd_memory.py
#
# This script checks for memory allocation of FreeBSD systems.
#
# Copyright (c) 2017, InnoGames GmbH
#
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
#

from __future__ import print_function
from argparse import ArgumentParser
from subprocess import check_output, CalledProcessError, STDOUT
import sys


# Translate human-readable names to sysctl
MEMORY_TYPES = {
    'active': 'v_active',
    'wired': 'v_wire',
}


# Nagios plugin exit codes
class ExitCodes:
    ok = 0
    warning = 1
    critical = 2
    unknown = 3


def main():
    args = parse_args()

    try:
        mi = parse_memory_info()
    except CalledProcessError as e:
        print('Unable to get memory information: {}'.format(e.output))
        return ExitCodes.unknown

    exit_code = ExitCodes.ok
    exit_multiline = ''

    for mem_type, sysctl in MEMORY_TYPES.items():
        local_code = ExitCodes.ok
        status = 'ok'
        for threshold in ['warning', 'critical']:
            if (
                mi[sysctl] > mi['physmem'] *
                getattr(args, mem_type + '_' + threshold) * 0.01
            ):
                if getattr(ExitCodes, threshold) > local_code:
                    status = threshold
                    exit_code = getattr(ExitCodes, threshold)
        if status == 'ok':
            exit_multiline += (
                '{}: {} memory {}MiB <= {}MiB * {}%\n'
                .format(
                    status.upper(),
                    mem_type,
                    mi[sysctl]/1048576,
                    mi['physmem']/1048576,
                    getattr(args, mem_type + '_warning')
                ))
        else:
            exit_multiline += (
                '{}: {} memory {}MiB > {}MiB * {}%\n'
                .format(
                    status.upper(),
                    mem_type,
                    mi[sysctl]/1048576,
                    mi['physmem']/1048576,
                    getattr(args, mem_type + '_' + status)
                ))

    if exit_code == 0:
        print('Memory allocation within limits')
    else:
        print('Memory allocation exceeds limits!')

    print(exit_multiline)
    return exit_code


def parse_args():
    parser = ArgumentParser()
    for memory_type in MEMORY_TYPES.keys():
        parser.add_argument(
            '--{}-warning'.format(memory_type), default=50,
            metavar='%', type=int,
            help='Warning threshold for {} memory'.format(memory_type),
        )
        parser.add_argument(
            '--{}-critical'.format(memory_type), default=75,
            metavar='%', type=int,
            help='Critical threshold for {} memory'.format(memory_type),
        )
    return parser.parse_args()


def parse_memory_info():
    memory_info = {}

    sysctl = check_output(['/sbin/sysctl', 'hw.physmem'], stderr=STDOUT)
    memory_info['physmem'] = int(sysctl.split(':')[1])

    # All other data is reported in pages
    sysctl = check_output(['/sbin/sysctl', 'hw.pagesize'], stderr=STDOUT)
    pagesize = int(sysctl.split(':')[1])

    sysctl = check_output(['/sbin/sysctl', 'vm.stats.vm'], stderr=STDOUT)
    memory_data = sysctl.splitlines()

    for line in memory_data:
        line = line.split(':')
        name = line[0].split('.')[3]
        # After multiplying by page size they are not _count anymore
        if name.endswith('_count'):
            name = name.replace('_count', '')
            memory_info[name] = int(line[1]) * pagesize

    return memory_info


if __name__ == '__main__':
    sys.exit(main())
