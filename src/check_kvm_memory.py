#!/usr/bin/env python
#
# KVM - check_kvm_memory
#
# This script checks the KVM memory allocation of all domains and raises a
# warning or critical state if overallocation of memory is reached. Values for
# overhead of domain and memory to reserver for OS can be specified using
# parameters.
#
# Copyright (c) 2016, InnoGames GmbH
#

from libvirt import openReadOnly

from sys import exit
from os import sysconf
from argparse import ArgumentParser


def main():
    args = get_args()

    domain_memory = get_domain_memory(args.overhead)
    domain_allocated = sum(domain_memory.values())
    hypervisor_memory = get_hypervisor_memory(args.reserved)
    hypervisor_free = hypervisor_memory - domain_allocated
    hypervisor_allocated = 100.0 - round(
        domain_allocated / hypervisor_memory * 100, 2
    )

    code = 0
    if hypervisor_free < args.critical:
        status = 'CRITICAL'
        code = 2
    elif hypervisor_free < args.warning:
        status = 'WARNING'
        code = 1
    else:
        status = 'OK'

    print('Memory {} {} MiB {}% free|{}'.format(
        status, hypervisor_free, hypervisor_allocated, hypervisor_free
    ))

    if args.verbose:
        print('')
        for name, memory in domain_memory.iteritems():
            if args.verbose:
                print('{}: {} MiB'.format(name, memory))
        print('')
        print('usable: {} MiB'.format(hypervisor_memory))
        print('used: {} MiB'.format(domain_allocated))
        print('free: {} MiB'.format(hypervisor_free))
        print('reserved incl.: {} MiB'.format(args.reserved))
        print('overhead incl.: {} MiB'.format(args.overhead))

    exit(code)


def get_args():
    """Get parsed arguments -> args"""

    parser = ArgumentParser()
    parser.add_argument(
        '-w', '--warning', type=float, default=0.0,
        help='Warning if less than MiB of memory are free (usually 0.0)'
    )
    parser.add_argument(
        '-c', '--critical', type=float, default=0.0,
        help='Critical if less than MiB of memory are free (usually 0.0)'
    )
    parser.add_argument(
        '-r', '--reserved', type=float, default=2048.0,
        help='MiB to reserve for OS overhead usually 1024.0 or 2048.0 MiB'
    )
    parser.add_argument(
        '-o', '--overhead', type=float, default=50.0,
        help='MiB to add on top per domain (qemu overhead)'
    )
    parser.add_argument(
        '-v', '--verbose', action='store_true',
        help='Be verbose about the allocated memory of every domain'
    )

    return parser.parse_args()


def get_hypervisor_memory(reserved):
    """Get physical available memory for hypervisor in MiB -> float

    arguments:
        reserved - MiB reserved for OS
    """

    memory_bytes = sysconf('SC_PAGE_SIZE') * sysconf('SC_PHYS_PAGES')
    return float(memory_bytes) / 1024.0**2.0 - reserved


def get_domain_memory(overhead):
    """Get memory allocated by domains in MiB -> dict

    arguments:
        overhead - MiB qemu overhead per domain
    """

    result = dict()

    try:
        con = openReadOnly(None)
        domains = con.listAllDomains()

        for domain in domains:
            name = domain.name()
            result[name] = float(domain.maxMemory()) / 1024.0 + overhead
    finally:
        con.close()

    return result


if __name__ == '__main__':
    main()
