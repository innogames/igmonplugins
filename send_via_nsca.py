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
        '--target',
        action='append',
        help='NSCA server to send the status',
    )
    parser.add_argument(
        '--hostname',
        default=socket.gethostname(),
        help='Hostname to send the status for',
    )
    parser.add_argument(
        '--service',
        default='passive_check',
        help='Service to send the status for',
    )
    parser.add_argument(
        'command',
        nargs='+',
        help='Command to run',
    )

    return vars(parser.parse_args())


def main(command, hostname, service, target):
    """The main program """
    process = subprocess.Popen(
        ' '.join(command), stdout=subprocess.PIPE, shell=True
    )
    output = process.communicate()[0][:4096] or 'NO OUTPUT'
    result = '\t'.join((hostname, service, str(process.returncode), output))

    if target:
        for host in target:
            send_process = subprocess.Popen(
                ('send_nsca', '-H', host),
                stdin=subprocess.PIPE,
            )
            send_process.communicate(result)
    else:
        print(result)


if __name__ == '__main__':
    main(**parse_args())
