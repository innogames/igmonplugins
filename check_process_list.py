#!/usr/bin/env python
"""InnoGames Monitoring Plugins - check_process_list.py

This is a monitoring check that calls the "ps" binary, and parses
the results.  It is compatible with BSD and GNU "ps", though they
provide different set of variables.  It is possible to use any
supported variable.  See you man pages for the list of them.

The script is capable of executing multiple operators on the processes.
Some examples are:

    --exclude 'pid == 0'
    --warning 'etime >= 3600'
    --critical 'user != root'
    --parent 'command ~= cron'

Copyright (c) 2016, InnoGames GmbH
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

from argparse import ArgumentParser, RawTextHelpFormatter
from collections import defaultdict
from operator import itemgetter
from re import compile
from subprocess import Popen, PIPE
from sys import exit

# The option arguments which accept a check
CHECK_ARGS = ('exclude', 'warning', 'critical', 'parent')


def main():
    """The main program

    This function puts together everything.  It parses the arguments,
    runs the tests, prints the results and exits with a Nagios compatible
    exit code.
    """
    args = parse_args()
    columns = ['pid', 'command']
    for arg_name in CHECK_ARGS:
        for check in getattr(args, arg_name):
            if check.key not in columns:
                # "command" has to go at last because it can contain spaces.
                columns.insert(-1, check.key)
    if args.parent:
        columns.insert(0, 'ppid')

    processes = get_processes(columns)
    check_groups = [
        ('exclude', args.exclude),
        ('warning', args.warning),
        ('critical', args.critical),
    ]
    if args.parent:
        try:
            processes = filter_process_tree(processes, args.parent)
        except NoProcess:
            print('CRITICAL no parent process')
            exit(2)
        # We don't want to check the parent or descendant family members.
        # Putting them as the first check groups would cause this.  We
        # would also get the change to give information about them.
        check_groups.insert(0, ('parent', (
            Check('mark', '==', 'parent'),
        )))
        check_groups.insert(0, ('descendant', (
            Check('mark', '==', 'descendant'),
        )))

    processes = filter_processes(processes, check_groups)
    messages = get_messages(processes, [c[0] for c in reversed(check_groups)])
    if messages[0]:
        status = 'CRITICAL'
        exit_code = 2
    elif messages[1]:
        status = 'WARNING'
        exit_code = 1
    else:
        status = 'OK'
        exit_code = 0

    print(' '.join((status, '; '.join(m for m in messages if m))))
    exit(exit_code)


def parse_args():
    """Return parsed arguments as an object"""
    parser = ArgumentParser(
        description=__doc__, formatter_class=RawTextHelpFormatter
    )
    for arg_name in CHECK_ARGS:
        parser.add_argument(
            '--' + arg_name,
            action='append',
            type=Check.parse,
            default=[],
            help=Check.__doc__,
        )
    return parser.parse_args()


def get_processes(columns):
    """Get all processes from the "ps" output"""
    cmd = ('ps', '-A')
    for column in columns:
        cmd += ('-o', column + '=')
    ps = Popen(cmd, stdout=PIPE)
    with ps.stdout as fd:
        while True:
            line = fd.readline()
            if not line:
                break
            values = (cast(v) for v in line.split(None, len(columns) - 1))
            yield dict(zip(columns, values))
    if ps.wait() != 0:
        raise Exception('Command "{}" failed'.format(' '.join(cmd)))


def filter_processes(processes, check_groups):
    """Filter processes using the given checks and mark them"""
    for process in processes:
        for mark, checks in check_groups:
            if execute_checks(process, checks, mark):
                yield process
                continue


def filter_process_tree(processes, parent_checks):
    """Filter the parent process with the given checks and then its children

    We are taking advantage of "ps" output being sorted by by controlling
    process by default to iterate the process list only once.
    """
    child_checks = []
    descendant_checks = []
    for process in filter_processes(processes, (
        ('parent', parent_checks),
        ('child', child_checks),
        ('descendant', descendant_checks),
    )):
        parentship_check = Check('ppid', '==', process['pid'])
        if process['mark'] == 'parent':
            child_checks.append(parentship_check)
        else:
            descendant_checks.append(parentship_check)
        yield process
    if not child_checks:
        raise NoProcess()


def execute_checks(process, checks, mark):
    """Execute all checks on a process and mark it"""
    for check in checks:
        if check(process):
            process['mark'] = mark
            process['matching_check'] = check
            return True
    return False


def get_messages(processes, marks):
    """Group processes by matching checks and format for printing"""
    counters = [defaultdict(int) for i in range(len(marks))]
    for process in processes:
        if process['mark'] in marks:
            index = marks.index(process['mark'])
            counters[index][process['matching_check']] += 1
    return [
        ', '.join(
            '{} process have {}'.format(c, m)
            for m, c in sorted(counts.items(), key=itemgetter(1), reverse=True)
        )
        for counts in counters
    ]


def cast(value):
    """Cast the values"""
    if value.isdigit():
        return int(value)
    return value


class Check:
    """Check consists of the variable name, operator, and a value"""
    operators = {
        '~=': lambda b: compile(b).match,
        '==': lambda b: lambda a: a == b,
        '<=': lambda b: lambda a: a <= b,
        '>=': lambda b: lambda a: a >= b,
        '<': lambda b: lambda a: a < b,
        '>': lambda b: lambda a: a > b,
    }

    def __init__(self, key, symbol, value):
        self.key = key
        self.symbol = symbol
        self.value = value
        self.executor = self.operators[symbol](value)

    def __str__(self):
        return '{} {} {}'.format(self.key, self.symbol, self.value)

    def __call__(self, process):
        return self.executor(process[self.key])

    @classmethod
    def parse(cls, pair):
        for symbol in sorted(cls.operators.keys(), key=len, reverse=True):
            if symbol in pair:
                index = pair.index(symbol)
                key = pair[:index].strip()
                value = cast(pair[(index + len(symbol)):].strip())
                return cls(key, symbol, value)
        raise ValueError('Cannot parse {}'.format(pair))


class NoProcess(Exception):
    pass


if __name__ == '__main__':
    main()
