#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Pressure Stall Information Check

This script checks the PSI (Pressure Stall Information) stats for CPU, memory,
and I/O on a Linux host. It monitors the "some" metric values and raises a
warning or critical state if reasonable thresholds are reached.

Copyright (c) 2025 InnoGames GmbH
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
import os
from sys import exit


def get_parser():
    """Get argument parser -> ArgumentParser"""

    parser = ArgumentParser()

    parser.add_argument(
        '--warning', '-w',
        help='warning threshold for pressure stall percentage, int or float',
        default=10,
        type=float,
    )
    parser.add_argument(
        '--critical', '-c',
        help='critical threshold for pressure stall percentage, int or float',
        default=15,
        type=float,
    )
    parser.add_argument(
        '--average', '-a',
        help='which average to use: avg10, avg60, or avg300',
        choices=['avg10', 'avg60', 'avg300'],
        default='avg60',
        type=str,
    )

    return parser


def main():
    """Main entrypoint for script"""

    args = get_parser().parse_args()

    try:
        pressure_stats = get_pressure_stats(args.average)
    except Exception as e:
        print('UNKNOWN - Error reading pressure stats: {}'.format(str(e)))
        exit(3)

    # Find the maximum "some" value across all pressure types
    max_pressure = max(pressure_stats.values())
    max_pressure_type = [k for k, v in pressure_stats.items() if v == max_pressure][0]

    code = 0

    if max_pressure > args.critical:
        status = 'CRITICAL'
        code = 2
    elif max_pressure > args.warning:
        status = 'WARNING'
        code = 1
    else:
        status = 'OK'

    # Format pressure stats for output
    stats_str = ', '.join(['{}: {:.2f}%'.format(k, v) for k, v in pressure_stats.items()])
    
    print('{} - Highest pressure stall is {} at {:.2f}% | {}'.format(
        status, max_pressure_type, max_pressure, stats_str))

    exit(code)


def get_pressure_stats(average_type):
    """Get PSI stats from /proc/pressure/ files"""
    
    pressure_files = {
        'cpu': '/proc/pressure/cpu',
        'memory': '/proc/pressure/memory', 
        'io': '/proc/pressure/io'
    }
    
    pressure_stats = {}
    
    for pressure_type, filepath in pressure_files.items():
        if not os.path.exists(filepath):
            raise Exception('PSI not supported - {} not found'.format(filepath))
            
        try:
            with open(filepath, 'r') as f:
                content = f.read().strip()
                
            # Parse the "some" line (first line)
            # Format: some avg10=X.XX avg60=X.XX avg300=X.XX total=XXXXX
            some_line = content.split('\n')[0]
            if not some_line.startswith('some '):
                raise Exception('Unexpected format in {}'.format(filepath))
                
            # Extract the specified average value
            parts = some_line.split()
            avg_part = None
            for part in parts:
                if part.startswith(f'{average_type}='):
                    avg_part = part
                    break
                    
            if not avg_part:
                raise Exception(f'Could not find {average_type} value in {filepath}')
                
            avg_value = float(avg_part.split('=')[1])
            pressure_stats[pressure_type] = avg_value
            
        except (IOError, ValueError, IndexError) as e:
            raise Exception('Error parsing {}: {}'.format(filepath, str(e)))
    
    return pressure_stats


if __name__ == '__main__':
    main()
