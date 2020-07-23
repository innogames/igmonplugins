#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - FreeBSD Memory Check

This script checks for memory allocation of FreeBSD systems.

Copyright (c) 2020 InnoGames GmbH
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

from argparse import ArgumentParser
from subprocess import check_output, CalledProcessError, STDOUT
from sys import exit

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
        cur_value = DataValue(mi[sysctl])
        max_value = DataValue(mi['physmem'])

        for threshold in ['warning', 'critical']:
            limit = getattr(args, mem_type + '_' + threshold)
            if cur_value > limit.scale(max_value):
                if getattr(ExitCodes, threshold) > local_code:
                    status = threshold
                    exit_code = getattr(ExitCodes, threshold)

        exit_multiline += '{}: {} memory {} {} {} of total {}\n'.format(
            status.upper(),
            mem_type,
            cur_value,
            '<=' if status == 'ok' else '>',
            getattr(args, mem_type + '_' + (
                'warning' if status == 'ok' else status
            )),
            max_value,
        )

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
            '--{}-warning'.format(memory_type),
            default='50%',
            type=DataValue,
            help='Warning threshold for {} memory'.format(memory_type),
        )
        parser.add_argument(
            '--{}-critical'.format(memory_type),
            default='75%',
            type=DataValue,
            help='Critical threshold for {} memory'.format(memory_type),
        )
    return parser.parse_args()


def sysctl(oid):
    return check_output(
        ['/sbin/sysctl', oid],
        universal_newlines=True,
        close_fds=False,
    ).splitlines()


def sysctl_line(oid):
    for line in sysctl(oid):
        return line.split(':')[1]


def parse_memory_info():
    memory_info = {}

    memory_info['physmem'] = int(sysctl_line('hw.physmem'))
    # All other data is reported in pages
    pagesize = int(sysctl_line('hw.pagesize'))

    memory_data = sysctl('vm.stats.vm')

    for line in memory_data:
        line = line.split(':')
        name = line[0].split('.')[3]
        # After multiplying by page size they are not _count anymore
        if name.endswith('_count'):
            name = name.replace('_count', '')
            memory_info[name] = int(line[1]) * pagesize

    return memory_info


class DataValue(object):
    units = [
        ('B', 1),
        ('KiB', 1024),
        ('MiB', 1024 ** 2),
        ('GiB', 1024 ** 3),
        ('TiB', 1024 ** 4),
        ('PiB', 1024 ** 5),
        ('EiB', 1024 ** 6),
        ('ZiB', 1024 ** 7),
        ('YiB', 1024 ** 8),
        ('%', None),
    ]

    def __init__(self, value):
        """Parse the value"""
        for unit in reversed(self.units):
            if str(value).endswith(unit[0]):
                self.value = float(value[:-len(unit[0])])
                self.unit = unit
                break
        else:
            self.value = float(value)
            self.unit = None

    def __str__(self):
        """If necessary change the value to number + unit format by rounding"""
        if self.unit:
            unit = self.unit
            value = self.value
        else:
            unit = self.choose_unit()
            value = self.value / unit[1]
        return '{:.2f}{}'.format(value, unit[0])

    def __float__(self):
        """If necessary change the value to number format"""
        if self.unit:
            if not self.unit[1]:
                raise Exception('Relative limits cannot be compared')
            return self.value * self.unit[1]
        return self.value

    def __lt__(self, other):
        return other is not None and float(self) < float(other)

    def __gt__(self, other):
        return other is not None and float(self) > float(other)

    def choose_unit(self):
        """Choose the appropriate unit for the value"""
        assert not self.unit
        for unit in reversed(self.units):
            if unit[1] and self.value > unit[1]:
                break
        return unit

    def scale(self, max_value):
        if self.unit and self.unit[0] == '%':
            return type(self)(float(max_value) * self.value * 0.01)
        return self


if __name__ == '__main__':
    exit(main())
