#!/usr/bin/env python
"""InnoGames Monitoring Plugins - APT Package Source Check

This is a Nagios script which checks, if packages are installed which
are not available in any repository gotten from sources.lists and
sources.lists.d.  This check will not do apt-get update before it will
exit with 1 (warning) if packages without source repository are found.
An ignore file can be created to exclude packages that are installed
and, not available anymore.

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
from os import path
from apt import Cache
from argparse import ArgumentParser

# File contains packages to be ignored by check_apt_missing_repository
# Deprecated. Will be removed soon. UZse option -i
ignorefile = '/etc/nagios-plugins/check_apt_missing_repositorys_ignore'


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


def check_if_debian():
    if not path.isfile('/etc/debian_version'):
        print("OK: This isn't a Debian system")
        exit(0)


def parse_ignore(ignored_packages):
    if path.isfile(ignorefile):
        with open(ignorefile) as fd:
            ignored_packages = (
                [i.rstrip('\n') for i in fd.readlines()] +
                ignored_packages
            )

    return ignored_packages


def check_ignored(pkg, ignore):
    return any(re.match(i, pkg.name) for i in ignore)


def main(ignored_packages):
    cache = Cache(memonly=True)
    not_in_repos = []
    ignore = parse_ignore(ignored_packages)
    for pkg in cache:
        if (
            pkg.is_installed and
            not pkg.is_upgradable and
            not check_ignored(pkg, ignore) and
            not any(pkg.installed.uris)
        ):
            not_in_repos.append(pkg)

    if not_in_repos:
        print(
            'WARNING: packages not in repositories: {}'
            .format(' '.join(pkg.name for pkg in not_in_repos))
        )
        exit(1)

    print('OK: All packages are found in repositories')
    exit(0)


if __name__ == '__main__':
    check_if_debian()
    main(**parse_args())
