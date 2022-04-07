#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - sentry.io event limit check

The script will exit with:
 - 0 (OK) All the limits provided to this check are kept
 - 1 (WARNING) Limits are either set to high or not at all

Copyright (c) 2022 InnoGames GmbH
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
import requests
import sys


def args_parse():
    """Argument parser, usage helper

    Returns the parsed arguments in a dictionary.
    """

    p = ArgumentParser()
    p.add_argument('-a', '--api-url', default='https://sentry.io/api',
                   dest='api', help='The sentry API to use')
    p.add_argument('-b', '--bearer', required=True,
                   help='A sentry api token with at least read permissions')
    p.add_argument('-o', '--organization', required=True,
                   help='The organization slug for the sentry.io organization'
                   'to be queried')
    p.add_argument('-t', '--teams', action='append', dest='teams',
                   help='Only check this team, can be added repeatedly')
    p.add_argument('-l', '--organization-limit', type=int,
                   dest='organizationlimit', help='If the total amount of '
                   'events per minute is higher than this limit the script '
                   'will exit with a warning and the exit code 1, for nrpe '
                   'compatibility')
    p.add_argument('-p', '--per-team-limit', type=int, dest='perteamlimit',
                   help="If any teams' projects' keys summed up limits is "
                   "higher than this, or not set the script will exit with a "
                   "warning and the exit code 1")
    p.add_argument('-v', '--verbose', action='store_true',
                   help='Print detailed stats')

    return p.parse_args()


def main():

    args = args_parse()
    teams = get_teams(args.api, args.organization, args.bearer)

    # Filter teams to the ones provided via arguments
    if args.teams:
        teams = list(filter(lambda t: t['slug'] in args.teams or t['name']
                     in args.teams, teams))

    # Set exit code and organnization wide event counter
    exit = 0
    organization = {'summed_events': 0, 'unlimited_events': False}

    # Iterate over teams, their projects and sum up their keys' rates
    for team in teams:
        for project in team['projects']:
            team['summed_events'] = 0
            team['unlimited_events'] = False

            dsns = get_dsns_from_project(
                args.api, args.organization, project['slug'], args.bearer)
            for dsn in dsns:
                if dsn['rateLimit']:
                    organization['summed_events'] += \
                        int(dsn['rateLimit']['count'] * 60 /
                            (dsn['rateLimit']['window']))
                    team['summed_events'] += int(
                                dsn['rateLimit']['count'] * 60 /
                                (dsn['rateLimit']['window']))
                else:
                    team['unlimited_events'] = True
                    organization['unlimited_events'] = True

                if args.verbose:
                    print('Team: {}, Project: {}, Key: {}, Limit: {}'.format(
                        team['name'], project['name'], dsn['name'],
                        dsn['rateLimit']))

            # Check if this team is over the team limit
            if args.perteamlimit and team['unlimited_events']:
                exit = 1
                print('WARNING: Unlimited events configured for team: {}'
                      .format(team['name']))
            elif (args.perteamlimit and team['summed_events'] >
                  args.perteamlimit):
                exit = 1
                print('WARNING: {} are configure of {} allowed for team: {}'
                      .format(team['summed_events'], args.perteamlimit,
                              team['name']))

    # Check if organization wiede limit is reached
    if args.organizationlimit and organization['unlimited_events']:
        exit = 1
        print('WARNING: Unlimited events configured in total')
    elif organization['summed_events'] > args.organizationlimit:
        exit = 1
        print('WARNING: {} of {} events are configured in total'.format(
            organization['summed_events'], args.organizationlimit))
    elif exit == 0 and args.organizationlimit:
        print('OK: {} events are configured in total'.format(
              organization['summed_events']))
    elif exit == 1 and args.organizationlimit:
        print('{} events are configured in total'.format(
              organization['summed_events']))
    else:
        exit = 3
        print('UKNOWN: This shoud not happen')

    sys.exit(exit)


def get_teams(api: str, organization_slug: str, bearer: str) -> dict:
    """Return a list of all teams in the account"""
    headers = {'Authorization': f'Bearer  {bearer}'}
    res = requests.get('{}/0/organizations/{}/teams/'.format(
        api, organization_slug), headers=headers)
    return res.json()


def get_dsns_from_project(api: str, organization_slug: str, project: str,
                          bearer: str) -> dict:
    """Return a list of DSNs for the passed project"""
    headers = {'Authorization': f'Bearer {bearer}'}
    res = requests.get('{}/0/projects/{}/{}/keys/'.format(
        api, organization_slug, project), headers=headers)
    return res.json()


if __name__ == '__main__':
    main()
