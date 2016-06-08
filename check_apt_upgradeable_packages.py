#!/usr/bin/env python
#
# Nagios apt check for upgradeable packages
#
# This is a Nagios script which checks if package upgrades are available
# It will exit with 1 (warning) if any upgradeable packages are found
# An ignorefile can be provided to exclude packages from beeing checked
#
# Copyright (c) 2016, InnoGames GmbH
#
import re
import os
import sys
import apt
from argparse import ArgumentParser

ignorefile = '/etc/check_apt_upgrade_ignores'

def parse_args():
    parser = ArgumentParser(prog='check_apt_missing_repository.py')
    parser.add_argument(
        '-i',
        action='append',
        dest='ignored_packages',
        default=[],
        help='exclude packages from beeing checked',
    )
    return vars(parser.parse_args())


def check_debianos():
    if not os.path.isfile('/etc/debian_version'):
        print "OK: This isn't a debian system"
        sys.exit(0)

def parse_ignore(ignored_packages):
    if os.path.isfile(ignorefile):
        with open(ignorefile) as fd:
            ignored_packages = ([i.rstrip('\n') for i in fd.readlines()]
                                + ignored_packages)

    return ignored_packages


def check_ignored(pkg, ignore):
    return any(re.match(i, pkg.name) for i in ignore)


def main(ignored_packages):
    check_debianos()
    ignore = parse_ignore(ignored_packages)
    cache=apt.Cache()
    cache.upgrade(dist_upgrade=True)
    upgradable = []
    for pkg in cache:
        if pkg.is_upgradable:
            upgradable.append(pkg)

    to_upgrade = []
    for pkg in upgradable:
        if not check_ignored(pkg, ignore):
            to_upgrade.append(pkg)

    if to_upgrade:
        packages = ' '.join([pkg.name for pkg in to_upgrade])
        print('WARNING: {0} packages do not have the newest version installed! | {1}'.format(
            len(to_upgrade),
            packages))
        sys.exit(1)
    print('OK: All packages are at the newest available version')

if __name__ == '__main__':
    main(**parse_args())

