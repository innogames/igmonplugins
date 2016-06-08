#!/usr/bin/env python
#
# Nagios apt package source check
#
# This is a Nagios script which checks if packages are installed
# which are not available in any repository gotten from sources.lists
# and sources.lists.d
# This check will not do apt-get update before
# It will exit with 1 (warning) if packages without sourcerepository are found
# An ignorefile can be created to exclude packages that are installed and i
# not available anymore
#
# Copyright (c) 2016, InnoGames GmbH
#

import re
from os import path
from apt import Cache
from argparse import ArgumentParser

# File contains packages to be ignored by check_apt_missing_repositorys
# Deprecated. Will be removed soon. UZse option -i
ignorefile = '/etc/nagios-plugins/check_apt_missing_repositorys_ignore'

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


def check_if_debian():
    if not path.isfile('/etc/debian_version'):
        print "OK: This isn't a debian system"
        exit(0)


def parse_ignore(ignored_packages):
    if path.isfile(ignorefile):
        with open(ignorefile) as fd:
            ignored_packages = ([i.rstrip('\n') for i in fd.readlines()]
                                + ignored_packages)

    return ignored_packages


def check_ignored(pkg, ignore):
    return any(re.match(i, pkg.name) for i in ignore)


def main(ignored_packages):
    cache = Cache(memonly=True)
    not_in_repos = []
    ignore = parse_ignore(ignored_packages)
    for pkg in cache:
        if (pkg.is_installed and not pkg.is_upgradable
        and not check_ignored(pkg, ignore)
        and not any(pkg.installed.uris)):
            not_in_repos.append(pkg)

    if not_in_repos:
        pkgs = ' '.join([pkg.name for pkg in not_in_repos])
        msg = u'WARNING: {0} packages have no candidate in repositorys!' \
                ' | {1}'.format(len(not_in_repos), pkgs)
        sig = 1
    else:
        msg = 'OK: All packages are found in repositorys'
        sig = 0

    print(msg)
    exit(sig)

if __name__ == '__main__':
    check_if_debian()
    main(**parse_args())

