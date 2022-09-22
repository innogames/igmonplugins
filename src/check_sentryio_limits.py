#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - sentry.io event limit check

The script will exit with:
 - 0 (OK) All the limits provided to this check are kept
 - 1 (WARNING) Limits are either set to high or not at all
 - 3 (UNKNOWN) Error while fetching team or project info via HTTP API

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

from argparse import ArgumentParser, Namespace
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List
import requests
import sys


def parse_args() -> Namespace:
    """
    Argument parser, usage helper
    Returns the parsed arguments in a dictionary.
    """

    p = ArgumentParser(description='Monitor Sentry teams and organization for '
                       'exceeding N events')
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

    args = parse_args()
    teams = get_teams(args.api_url, args.organization, args.bearer)

    # Filter teams to the ones provided via arguments
    if args.teams:
        teams = list(filter(
            lambda t: t['slug'] in args.teams or t['name'] in args.teams,
            teams
        ))

        if len(args.teams) != len(teams):
            print(f"UNKNOWN: Could not find all teams: {args.teams}! Typo ?")
            sys.exit(3)

    # Initiate exit code, organization wide event counters and lists
    exit = 0
    organization = {'summed_events': 0, 'unlimited_events': False}
    project_list = []
    results = []
    threads = 20

    for team in teams:
        team['summed_events'] = 0
        team['unlimited_events'] = False

    def merge_dsns(results: List[dict], teams: List[dict]) -> None:
        """
        Iterate over DSNs and update the team and organization
        counters and unlimited states
        """

        seconds_per_day = 60 * 60 * 24

        for team in teams:
            if args.verbose:
                print(f"\nTeam \"{team['slug']}\", checking for projects")

            for dsn in results:
                for project in team['projects']:
                    if (int(dsn['projectId']) == int(project['id'])
                            and dsn['rateLimit']):
                        rate_count = dsn['rateLimit']['count']
                        rate_window = dsn['rateLimit']['window']
                        rate_daily = int(
                            rate_count * seconds_per_day / rate_window)
                        organization['summed_events'] += rate_daily
                        team['summed_events'] += rate_daily
                        if args.verbose:
                            print(f'\tProject: {project["slug"]}, Key: '
                                  f'{dsn["name"]} limited to: {rate_daily} '
                                  'events per day')
                    elif int(dsn['projectId']) == int(project['id']):
                        organization['unlimited_events'] = True
                        team['unlimited_events'] = True
                        if args.verbose:
                            print(f'\tProject: {project["slug"]}, Key: '
                                  f'{dsn["name"]} with unlimited events')

    # Build list of all projects for parallel queries
    for team in teams:
        for project in team['projects']:
            project['team'] = team
            project_list.append(project)

    # Fetch all keys on the project
    with ThreadPoolExecutor(max_workers=threads) as executor:

        future_to_url = {executor.submit(
                get_dsns_from_project,
                args.api_url,
                args.organization,
                project['slug'],
                args.bearer) for project in project_list}

        for future in as_completed(future_to_url):
            try:
                results.append(future.result()[0])
            except Exception as e:
                print('Looks like something went wrong:', e)

    merge_dsns(results, teams)

    # Check if any team is over the team limit
    if args.per_team_limit:
        for team in teams:
            if team['unlimited_events']:
                exit = 1
                print("WARNING: Unlimited events configured for team: "
                      f"{team['slug']}")
            elif team['summed_events'] > args.per_team_limit:
                exit = 1
                print(f"WARNING: {team['summed_events']} "
                      f"events are configured, but {args.per_team_limit} "
                      f"allowed for team: {team['slug']}")

    # Check if organization wide limit is reached
    if args.organization_limit:
        # If any key is unlimited
        if organization['unlimited_events']:
            exit = 1
            print('WARNING: Unlimited events configured in total')
        # If the organizaion wide limit is hit
        elif organization['summed_events'] > args.organization_limit:
            exit = 1
            print(f"WARNING: {organization['summed_events']} events are "
                  f"configured, but {args.organization_limit} allowed in "
                  "total")
        # If team limit is hit but organization limit is not
        elif exit == 1:
            print(f"{organization['summed_events']} events are configured "
                  "in total")

    # If neither team nor organization limit is hit
    if exit == 0:
        print(f"OK: {organization['summed_events']} "
              "events are configured in total")

    sys.exit(exit)


def get_teams(api: str, organization_slug: str, bearer: str) -> dict:
    """Return a list of all teams in the account"""
    headers = {'Authorization': f'Bearer  {bearer}'}
    res = requests.get(
            f'{api}/0/organizations/{organization_slug}/teams/',
            headers=headers)
    if res.status_code != 200:
        print(f'Expected HTTP 200 but got {res.status_code} '
              'while fetching teams')
        sys.exit(3)  # Nagios code UNKNOWN

    return res.json()


def get_dsns_from_project(api: str, organization_slug: str, project: str,
                          bearer: str) -> dict:
    """Return a list of DSNs for the passed project"""
    headers = {'Authorization': f'Bearer {bearer}'}
    res = requests.get(
            f'{api}/0/projects/{organization_slug}/{project}/keys/',
            headers=headers)
    if res.status_code != 200:
        print(f'Expected HTTP 200 but got {res.status_code} while fetching '
              'dsns for project')
        sys.exit(3)  # Nagios code UNKNOWN

    return res.json()


if __name__ == '__main__':
    main()
