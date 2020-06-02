#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Cron Runtime Check

Copyright (c) 2020 InnoGames GmbH
"""
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the 'Software'), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED 'AS IS', WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

from argparse import ArgumentParser
from subprocess import STDOUT, check_output, CalledProcessError
from sys import exit
from os.path import isfile


def parse_args():
    """The argument parser"""

    parser = ArgumentParser(
        description='CHECK_CRON_RUNNING_TIME',
        epilog=(
            'ps version 3.2.9 or above needed to run this script.  If no Cron '
            'is running, CRITICAL is returned.  If total running time '
            'is more that 1 hour, then WARNING is returned.  It calculates '
            'running time of each child using ps -o "etimes=" $pid.  etimes'
            'is the elapsed time in seconds.'
        ),
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Increase verbosity',
    )
    parser.add_argument(
        '--exclude-file',
        default='',
        help='File to get list of cron names to exclude (line separated)',
    )

    return vars(parser.parse_args())


def main(verbose=False, exclude_file=''):
    """The main program"""

    # Dictionary of pids containing th command that is running
    ps_aux = get_ps_aux()

    # Nagios Return codes
    ok_code = 0
    warn_code = 1
    crit_code = 2
    un_code = 3

    # pre check ps version
    if '3.2.8' in execute('ps --version').strip('\n').split(' ')[2]:
        print('PS version 3.2.9 or above needed to run this script')
        exit(int(un_code))

    # Check for main Cron, Return CRITICAL if not running
    try:
        parent_cron_pid = execute('pgrep -o cron').strip('\n')
    except AttributeError:
        print('MAIN CRON NOT RUNNING')
        exit(int(crit_code))

    if verbose:
        print('Cron PID: ' + parent_cron_pid)

    # Get child processes for main cron
    # Usage: pgrep -P pid
    cron_childs = execute('pgrep -P ' + parent_cron_pid)

    # Exit with CRITICAL if no child cron running
    if not cron_childs:
        print('No child crons running')
        exit(int(ok_code))

    cron_child_list = []
    cron_child_time = None

    exclude_list = parse_exclude_file(exclude_file)

    for child in cron_childs.split('\n'):
        cron_child_list.append(child)

    if verbose:
        print('Cron Childs: ' + str(cron_child_list))

    cron_pid_more_than1 = []
    warn_flag = 0
    for pid in cron_child_list:
        if pid:
            try:
                cron_child_time = execute("ps -o 'etimes=' " + pid)
                cron_child_time = cron_child_time.strip('    ').strip('\n')
            except AttributeError:
                pass

            if not cron_child_time:
                continue

            # check for 1 hour time
            if int(cron_child_time) >= 3600:
                # Check if cron name is on ignore list
                include = True
                child_pid = execute('pgrep -P ' + pid).strip()

                for exclude in exclude_list:
                    if child_pid in ps_aux:
                        if exclude in ps_aux[child_pid]:
                            include = False
                if include:
                    cron_pid_more_than1.append(pid)
                    warn_flag += 1
            elif int(cron_child_time) < 3600:
                continue
            else:
                print('UNKNOWN PID execution TIME')
                exit(int(un_code))

    if warn_flag:

        msg = '|'.join(str(pid) for pid in cron_pid_more_than1)
        print(msg)
        for i in cron_pid_more_than1:
            get_child(i)
        exit(int(warn_code))
    else:
        print('No CRON running more than 1 hour')
        exit(int(ok_code))


def execute(cmd):
    try:
        output = check_output(cmd, shell=True, stderr=STDOUT)
    except CalledProcessError:
        return False
    content = output.decode()

    if content == '':
        return True

    return content


def get_ps_aux():
    pids = {}
    pid_list = execute("ps ax -o 'pid=' -o 'cmd='")
    for line in pid_list.split('\n'):
        if len(line.split(' ')) > 1:
            the_pid, the_command = line.lstrip().split(' ', 1)
            pids[the_pid] = the_command
    return pids


def get_child(ppid):
    childs = execute('pgrep -P ' + ppid)
    if childs:
        for child in childs.strip('\n').split():
            exec_out = execute(
                'ps -ef | grep {} | grep -wv grep'.format(child)
            )
            print('|' + exec_out)
            get_child(child)


def parse_exclude_file(exclude_file):
    """Parses the exclude file and returns a combined list"""

    if not isfile(exclude_file):
        return []

    with open(exclude_file) as fd:
        return list(filter(None, [line.rstrip('\n') for line in fd]))


if __name__ == '__main__':
    main(**parse_args())
