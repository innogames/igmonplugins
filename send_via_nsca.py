#!/usr/bin/env python
#
# Helper script to run send results of a check via NSCA
#
# Copyright (c) 2016, InnoGames GmbH
#

import subprocess
import argparse


def parse_args():
    """Argument parser, usage helper

    Returns the parsed arguments in a dictionary.
    """

    parser = argparse.ArgumentParser(description='NSCA helper')
    parser.add_argument(
        '-H',
        action='append',
        dest='hosts',
        required=True,
        help='NSCA server to send the status',
    )
    parser.add_argument(
        '-s',
        dest='service',
        required=True,
        help='NSCA service to send the status',
    )
    parser.add_argument(
        'command',
        nargs='+',
        help='Active command to run',
    )

    return vars(parser.parse_args())


def main(hosts, service, command):
    """The main program """

    # Run the actual command
    process = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True)
    output = process.communicate()

    # Prepare the result to send
    result = '\t'.join((
        subprocess.check_output('hostname').strip(),
        service,
        str(process.returncode),
        output[0].splitlines()[0][:4096],
    ))

    # Send the data to NSCA servers
    for host in hosts:
        send_process = subprocess.Popen(
            ('send_nsca', '-H', host),
            stdin=subprocess.PIPE,
        )
        send_process.communicate(result)


if __name__ == '__main__':
    main(**parse_args())
