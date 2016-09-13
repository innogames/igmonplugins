#!/usr/bin/env python
#
# Helper script to run send results of a check via NSCA
#
# Copyright (c) 2016, InnoGames GmbH
#

import argparse
import socket
import subprocess


def parse_args():
    """Argument parser, usage helper

    Returns the parsed arguments in a dictionary.
    """
    parser = argparse.ArgumentParser(description='NSCA helper')
    parser.add_argument(
        '-H',
        '--target',
        action='append',
        dest='targets',
        default=['localhost'],
        help='NSCA server to send the status',
    )
    parser.add_argument(
        '--hostname',
        default=socket.gethostname(),
        help='Hostname to send the status for',
    )
    parser.add_argument(
        '-s',
        '--service',
        dest='service',
        default='passive_check',
        help='Service to send the status for',
    )
    parser.add_argument(
        'command',
        nargs='+',
        help='Command to run',
    )

    return vars(parser.parse_args())


def main(targets, hostname, service, command):
    """The main program """
    process = subprocess.Popen(
        ' '.join(command), stdout=subprocess.PIPE, shell=True
    )
    output = process.communicate()[0][:4096]
    result = '\t'.join((hostname, service, str(process.returncode), output))

    for target in targets:
        send_process = subprocess.Popen(
            ('send_nsca', '-H', target),
            stdin=subprocess.PIPE,
        )
        send_process.communicate(result)


if __name__ == '__main__':
    main(**parse_args())
