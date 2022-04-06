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

    p=ArgumentParser()
    p.add_argument('-a', '--api-url', default='https://sentry.io/api',
                   dest='api', help='The sentry API to use')
    p.add_argument('-b', '--bearer', required=True,
                   help='A sentry api token with at least read permissions')
    p.add_argument('-o', '--organization', required=True,
                   help='The organization slug for the sentry.io organization'
                   'to be queried')
    p.add_argument('-t', '--teams', action='append', dest='teams',
                   help='Only check this team, can be added repeatedly')
    p.add_argument('-g', '--global-limit', type=int, dest='globallimit',
                   help='If the total amount if events per minute is higher '
                   'than this limit the script will exit with a warning and '
                   'the exit code 1, for nrpe compatibility')
    p.add_argument('-p', '--per-team-limit', type=int, dest='perteamlimit',
                   help="If any teams' projects' keys summed up limits is "
                   "higher than this, or not set the script will exit with a "
                   "warning and the exit code 1")
    p.add_argument('-v', '--verbose', action='store_true',
                   help='Print detailed stats')

    return(p.parse_args())

def main():

    args = args_parse()
    teams = get_teams(args.api, args.organization, args.bearer)

    '''Filter teams if provided via arguments'''
    if args.teams:
        filtered_teams = []
        for team in teams:
            if team['slug'] in args.teams or team['name'] in args.teams:
                filtered_teams.append(team)
        teams = filtered_teams

    '''Set exit code and global event counter'''
    exit = 0
    events = 0

    '''Iterate over teams, their projects and sum up their keys' rates'''
    for team in teams:
        for project in team['projects']:
            team['summed_events'] = 0

            dsns = get_dsns_from_project(
                args.api, args.organization, project['slug'], args.bearer)
            for dsn in dsns:
                if dsn['rateLimit']:
                    if type(events) is int:
                        events += int(dsn['rateLimit']['count'] * 60 /
                                      (dsn['rateLimit']['window']))
                    if type(team['summed_events']) is int:
                        team['summed_events'] += int(
                                dsn['rateLimit']['count'] * 60 /
                                (dsn['rateLimit']['window']))
                else:
                    events = None
                    team['summed_events'] = None

                if args.verbose:
                    print('Team: {}, Project: {}, Key: {}, Limit: {}'.format(
                        team['name'], project['name'], dsn['name'],
                        dsn['rateLimit']))

            '''Check if this team is over the team limit'''
            if args.perteamlimit and not team['summed_events']:
                exit = 1
                print('WARNING: Unlimited events configured for team: {}'
                      .format(team['name']))
            elif args.perteamlimit and team['summed_events'] and \
                    team['summed_events'] > args.perteamlimit:
                exit = 1
                print('WARNING: {} are configure of {} allowed for team: {}'
                      .format(team['summed_events'], args.perteamlimit,
                              team['name']))

    '''Check if global limit is reached'''
    if args.globallimit and not events:
        exit = -1
        print('WARNING: Unlimited events configured in total')
    elif args.globallimit and events > args.globallimit:
        exit = 1
        print('WARNING: {} of {} events are configured in total'.format(
            events, args.globallimit))
    elif events and exit == 0:
        print('OK: {} events are configured in total'.format(events))
    elif not args.globallimit:
        print('OK: no global event limit')
    else:
        exit = 3
        print('UKNOWN Contidion this shoud not happen')

    sys.exit(exit)


def get_teams(api, organization, bearer):
    """Return a list of all teams in the account"""
    teams = []
    headers = {'Authorization': f'Bearer  {bearer}'}
    r = requests.get('{}/0/organizations/{}/teams/'.format(
        api, organization), headers=headers)
    teams = r.json()
    return(teams)


def get_dsns_from_project(api, organization, project, bearer):
    """Retun a list of DSNs for the project"""
    dsns = []
    headers = {'Authorization': f'Bearer {bearer}'}
    r = requests.get('{}/0/projects/{}/{}/keys/'.format(
        api, organization, project), headers=headers)
    dsns = r.json()

    return(dsns)


if __name__ == '__main__':
    main()
