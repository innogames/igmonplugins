#!/usr/bin/env python
"""InnoGames Monitoring Plugins - APT Check for Upgradeable Packages

This is a Nagios script which checks if package upgrades are available
It will exit with 1 (warning) if any upgradeable packages are found.
An ignore file can be provided to exclude packages from being checked.

Copyright (c) 2016 InnoGames GmbH
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
        help='exclude packages from being checked',
    )
    return vars(parser.parse_args())


def check_debianos():
    if not os.path.isfile('/etc/debian_version'):
        print("OK: This isn't a Debian system")
        sys.exit(0)


def parse_ignore(ignored_packages):
    if os.path.isfile(ignorefile):
        with open(ignorefile) as fd:
            ignored_packages = (
                [i.rstrip('\n') for i in fd.readlines()] +
                ignored_packages
            )

    return ignored_packages


def check_ignored(pkg, ignore):
    return any(re.match(i, pkg.name) for i in ignore)


def main(ignored_packages):
    check_debianos()
    ignore = parse_ignore(ignored_packages)
    cache = apt.Cache()
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
        print((
            'WARNING: {0} packages do not have the newest version installed!'
            ' | {1}'
        ).format(len(to_upgrade), packages))
        sys.exit(1)

    print('OK: All packages are at the newest available version')


if __name__ == '__main__':
    main(**parse_args())
