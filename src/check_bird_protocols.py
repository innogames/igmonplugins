#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - BIRD BGP Protocols Health Check

This is a Nagios script which queries BIRD to check if all protocols
are up and established/running.

Copyright (c) 2020 InnoGames GmbH
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

import sys

from argparse import ArgumentParser
from subprocess import check_output, STDOUT, CalledProcessError


def parse_args():
    parser = ArgumentParser(
        description='Check if all BIRD BGP protocols are up and established'
    )
    parser.add_argument('path', help='Path to the birdc/birdc6 binary')

    return parser.parse_args()


def main():
    args = parse_args()
    birdc_path = args.path

    code, reason = check_birdc_protocols(birdc_path)

    print(format_nagios_message(code, reason))
    sys.exit(code)


def check_birdc_protocols(path):
    try:
        output = check_output([path, 'show', 'protocols'], stderr=STDOUT)
    except (FileNotFoundError, PermissionError):
        return (
            ExitCodes.critical,
            'The path to the birdc binary does not exist or is not executable'
        )
    except CalledProcessError:
        return (
            ExitCodes.critical,
            'birdc returned a non-zero exit code'
        )

    if not output:
        return (ExitCodes.critical, 'Could not retrieve BIRD\'s output')

    protocols_parsed = parse_birdc_output(output.decode())

    if not protocols_parsed:
        return (ExitCodes.critical, 'Could not find any BGP protocol entries')

    result = {
        ProtocolStates.up: [],
        ProtocolStates.down: [],
        ProtocolStates.disabled: [],
        ProtocolStates.unknown: [],
    }

    for protocol in protocols_parsed:
        if protocol['type'] == 'BGP':
            ret = check_bgp_protocol(protocol)
        elif protocol['type'] == 'OSPF':
            ret = check_ospf_protocol(protocol)
        elif protocol['type'] in ['Device', 'Kernel', 'Static', 'Direct']:
            ret = check_other_protocol(protocol)
        else:
            ret = ProtocolStates.unknown

        result[ret].append(protocol['name'])

    if result[ProtocolStates.down]:
        return (
            ExitCodes.critical,
            'Some protocols are down: {}'
            .format(', '.join(result[ProtocolStates.down]))
        )
    elif result[ProtocolStates.disabled]:
        return (
            ExitCodes.warning,
            'Some protocols are disabled: {}'
            .format(', '.join(result[ProtocolStates.disabled]))
        )
    elif result[ProtocolStates.unknown]:
        return (
            ExitCodes.unknown,
            'Unknown protocols are seen: {}'
            .format(', '.join(result[ProtocolStates.unknown]))
        )
    else:
        return (ExitCodes.ok, 'All protocols are up')


def check_bgp_protocol(protocol):
    def is_bgp_up(protocol):
        is_established = protocol['info'] == 'Established'
        is_up = protocol['state'] == 'up'
        return is_up and is_established

    def is_bgp_disabled(protocol):
        state_down = protocol['state'] == 'down'
        return state_down

    if is_bgp_up(protocol):
        return ProtocolStates.up
    elif is_bgp_disabled(protocol):
        return ProtocolStates.disabled
    else:
        return ProtocolStates.down


def check_ospf_protocol(protocol):
    def is_ospf_up(protocol):
        is_up = protocol['state'] == 'up'
        is_running = protocol['info'] == 'Running'
        return is_up and is_running

    def is_ospf_disabled(protocol):
        is_down = protocol['state'] == 'down'
        return is_down

    if is_ospf_up(protocol):
        return ProtocolStates.up
    elif is_ospf_disabled(protocol):
        return ProtocolStates.disabled
    else:
        return ProtocolStates.down


def check_other_protocol(protocol):
    if protocol['state'] == 'up':
        return ProtocolStates.up
    elif protocol['state'] == 'down':
        return ProtocolStates.disabled
    else:
        return ProtocolStates.down


def parse_birdc_output(output):
    # Matching protocol lines from BIRD:
    # BIRD 1.6.3 ready.
    # name     proto    table    state  since       info
    # direct1  Direct   master   up     2020-02-27
    # b_af     BGP      master   up     2020-02-28  Established
    # b_lb     BGP      master   start  18:43:46    Active        Socket: conn
    # b_home   BGP      master   down   2020-02-29
    # We are extracting the protocol name, state, date/time since last
    # change and the additional information about the state of the session.
    lines = output.splitlines()
    lines = lines[2:]

    tokenized_lines = [
        [field.strip() for field in line.split(None, 5)]
        for line in lines
    ]
    protocols_dicts = [
        build_dict(line) for line in tokenized_lines
    ]

    return protocols_dicts


def build_dict(line):
    # The next line ensures that we always have 6 elements in the line,
    # as the tokenization of protocols that are disabled yield only 5 elements.
    line += [None] * (6 - len(line))
    return {
        'name': line[0],
        'type': line[1],
        'table': line[2],
        'state': line[3],
        'since': line[4],
        'info': line[5],
    }


def format_nagios_message(code, reason):
    if code == ExitCodes.ok:
        state_text = 'OK'
    elif code == ExitCodes.warning:
        state_text = 'WARNING'
    elif code == ExitCodes.critical:
        state_text = 'CRITICAL'
    else:
        state_text = 'UNKNOWN'
    return '{0} - {1}'.format(state_text, reason)


class ProtocolStates:
    up = 0
    disabled = 1
    down = 2
    unknown = 3


class ExitCodes:
    ok = 0
    warning = 1
    critical = 2
    unknown = 3


if __name__ == '__main__':
    main()
