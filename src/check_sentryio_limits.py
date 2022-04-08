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
from typing import List
import requests
import sys


def args_parse():
    """
    Argument parser, usage helper
    Returns the parsed arguments in a dictionary.
    """

    p = ArgumentParser()
    p.add_argument('-b', '--bearer', required=True,
                   help='A sentry api token with at least read permissions')
    p.add_argument('-o', '--organization', required=True,
                   help='The organization slug for the sentry.io organization'
                   'to be queried')
    p.add_argument('-l', '--organization-limit', type=int,
                   help='If the total amount of events per day is higher '
                   'than this limit the script will exit with a warning and '
                   'the exit code 1, for nrpe compatibility')
    p.add_argument('-t', '--teams', action='append',
                   help='Only check this team, can be added repeatedly')
    p.add_argument('-p', '--per-team-limit', type=int,
                   help="If any teams' projects' keys summed up limits is "
                   "higher than this, or not set the script will exit with a "
                   "warning and the exit code 1")
    p.add_argument('-a', '--api-url', default='https://sentry.io/api',
                   help='The sentry API to use')
    p.add_argument('-v', '--verbose', action='store_true',
                   help='Print detailed stats')

    return p.parse_args()


def main():

    args = args_parse()
    teams = get_teams(args.api_url, args.organization, args.bearer)

    # Filter teams to the ones provided via arguments
    if args.teams:
        teams = list(filter(
            lambda t: t['slug'] in args.teams or t['name'] in args.teams,
            teams
        ))

    # Initiate exit code and organnization wide event counter
    exit = 0
    organization = {'summed_events': 0, 'unlimited_events': False}

    def traverse_dsns(dsns: List[dict], team: dict) -> None:
        """
        Iterate over DSNs and update the team and organization
        counters and unlimited states
        """
        for dsn in dsns:

            if args.verbose:
                print(f"  Key: \"{dsn['name']}\",", end=" ")

            if dsn['rateLimit']:
                # Calculate events per day and add them to the counters
                rate_count = dsn['rateLimit']['count']
                rate_window = dsn['rateLimit']['window']
                rate_daily = int(rate_count * 14400 / rate_window)
                organization['summed_events'] += rate_daily
                team['summed_events'] += rate_daily
                if args.verbose:
                    print(f'limited to {rate_daily} events per day')
            else:
                # Set unlimtied events if no limt is given
                team['unlimited_events'] = True
                organization['unlimited_events'] = True
                if args.verbose:
                    print('with unlimited events')

    # Iterate over teams and their projects to sum up their keys' rates
    for team in teams:

        if args.verbose:
            print(f"\nTeam \"{team['slug']}\", checking for projects")

        # Initiate team wide event counters
        team['summed_events'] = 0
        team['unlimited_events'] = False

        # Iterate over all projects of a team to find the limits of all dsns
        for project in team['projects']:

            if args.verbose:
                print(f" Project \"{project['slug']}\", checking for keys")

            # Fetch all keys on the project
            # TODO use concurrent requests to scale out for tons of projects
            dsns = get_dsns_from_project(
                args.api_url, args.organization, project['slug'], args.bearer)

            # Fetch rateLimits for each key and add them to the totals
            traverse_dsns(dsns, team)

    if args.verbose:
        print("")

    # Check if any team is over the team limit
    if args.per_team_limit:
        for team in teams:
            if team['unlimited_events']:
                exit = 1
                print('WARNING: Unlimited events configured for team: {}'
                      .format(team['slug']))
            elif team['summed_events'] > args.per_team_limit:
                exit = 1
                print('WARNING: {} are configured, but {} allowed for team: {}'
                      .format(team['summed_events'], args.per_team_limit,
                              team['slug']))

    # Check if organization wide limit is reached
    if args.organization_limit:
        # If any key is unlimited
        if organization['unlimited_events']:
            exit = 1
            print('WARNING: Unlimited events configured in total')
        # If the organizaion wide limit is hit
        elif organization['summed_events'] > args.organization_limit:
            exit = 1
            print('WARNING: {} events are configured, but {} allowed in total'
                  .format(organization['summed_events'],
                          args.organization_limit))
        # If team limit is hit but organization limit is not
        elif exit == 1:
            print('{} events are configured in total'.format(
                  organization['summed_events']))

    # If neither team nor organization limit is hit
    elif exit == 0:
        print('OK: {} events are configured in total'.format(
               organization['summed_events']))

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
