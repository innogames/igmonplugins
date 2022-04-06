#!/usr/bin/env python3

from argparse import ArgumentParser
import requests
import sys


p = ArgumentParser()
p.add_argument('-b', '--bearer', type=str, required=True, dest='bearer',
               help='A sentry api token with at least read permissions')
p.add_argument('-o', '--organization', type=str, required=True,
               dest='organization', help='The organization slug for the\
               sentry.io organization to be queried')
p.add_argument('-t', '--team', type=str, action='append', dest='teams',
               help='Only check this team, can be added repeatetly')
p.add_argument('-g', '--globallimt', type=int, dest='globallimit',
               help='If the total amount if events per minute is higher \
               than this limit the script will exit with a warning and \
               a the exit code 1, for nrpe compatibility')
p.add_argument('-p', '--perteamlimit', type=int, dest='perteamlimit',
               help='If any teams\' projects\' keys summed up limits is \
               higher than this, or not set the script will exit with a \
               warning and the exit code 1')
p.add_argument('-v', '--verbose', action='store_true', dest='verbose',
               help='Print detailed stats')
args = p.parse_args()


def get_teams(organization, bearer):
    '''Return a list of all teams in the account'''
    teams = []
    headers = {'Authorization': 'Bearer  {}'.format(bearer)}
    r = requests.get('https://sentry.io/api/0/organizations/{}/teams/'.format(
        organization), headers=headers)
    teams = r.json()
    return(teams)


def get_dsns_from_project(organization, project, bearer):
    '''Retun a list of DSNs for the project'''
    dsns = []
    headers = {'Authorization': 'Bearer {}'.format(bearer)}
    r = requests.get('https://sentry.io/api/0/projects/{}/{}/keys/'.format(
        organization, project), headers=headers)
    dsns = r.json()

    return(dsns)


def main():

    teams = get_teams(args.organization, args.bearer)

    '''Filter teams if list is provided'''
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
                args.organization, project['slug'], args.bearer)
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
                print('WARNING: unlimited events configured for team: {}\
                    '.format(team['name']))
            elif args.perteamlimit and team['summed_events'] and \
                    team['summed_events'] > args.perteamlimit:
                exit = 1
                print('WARNING: {} are configure of {} allowed for team: {}\
                    '.format(team['summed_events'], args.perteamlimit,
                    team['name']))

    '''Check if global limit is reached'''
    if args.globallimit and not events:
        exit = -1
        print('WARNING: unlimited events configured in total')
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


if __name__ == '__main__':
    main()
