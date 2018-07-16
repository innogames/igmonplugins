#!/usr/bin/env python
#
# igmonplugins - Switch checks:
#                - cpu usage
#                - port state
#
# Copyright (c) 2017, InnoGames GmbH
#
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
from pysnmp.entity.rfc3413.oneliner.cmdgen import (
    CommandGenerator,
    CommunityData,
    UdpTransportTarget,
    UsmUserData,
    usmAesCfb128Protocol,
    usmDESPrivProtocol,
    usmHMACSHAAuthProtocol,
)
from pysnmp.proto.rfc1902 import Integer, Counter32, Counter64
import re
import sys

# Predefine some variables, it makes this program run a bit faster.
cmd_gen = CommandGenerator()

OIDS = {
    'if_index': '1.3.6.1.2.1.2.2.1.1',  # Index of all ports.
    'if_admin_status': '1.3.6.1.2.1.2.2.1.7',  # Status of port. Up="1"
    'if_oper_status': '1.3.6.1.2.1.2.2.1.8',  # Status of port. Up="1"
    'if_name': '1.3.6.1.2.1.31.1.1.1.1',  # name / display-string of port.
    'if_alias': '1.3.6.1.2.1.31.1.1.1.18',  # name / display-string of port.
    'switch_model': '.1.3.6.1.2.1.1.1.0',
    'port_name': '.1.3.6.1.2.1.31.1.1.1.1',
    'port_state': '1.3.6.1.2.1.2.2.1.8',
}

LAGG_OIDS = {
    'procurve': '.1.3.6.1.4.1.11.2.14.11.5.1.7.1.3.1.1.8',
    'powerconnect': '.1.2.840.10006.300.43.1.2.1.1.12',
}

CPU_OIDS = {
    'procurve': '.1.3.6.1.4.1.11.2.14.11.5.1.9.6.1.0',
    'powerconnect': 'iso.3.6.1.4.1.674.10895.5000.2.6132.1.1.1.1.4.9.0',
    'extreme': '.1.3.6.1.4.1.1916.1.32.1.2.0',
    # 1-minute average for the 1st cpu of stack because we don't stack them.
    'force10_mxl': '1.3.6.1.4.1.6027.3.26.1.4.4.1.4.2.1.1',
}


class SwitchException(Exception):
    pass


def main():
    args = parse_args()
    snmp = get_snmp_connection(args)
    model = get_switch_model(snmp)

    if not model:
        return -1

    if args.check == 'links':
        exit_code, exit_msg = check_ports(snmp, model, args)
        if exit_code != 0:
            exit_msg = 'Some ports have problems:\n' + exit_msg
    elif args.check == 'cpu':
        exit_code, exit_msg = check_cpu(snmp, model, args)
    else:
        exit_code = 3
        exit_msg = 'Unknown check type {} requested'.format(args.check)

    print(exit_msg)
    sys.exit(exit_code)


def parse_args():
    parser = ArgumentParser()
    parser.add_argument(
        '-H', dest='switch', required=True,
        type=str, help='Hostname of a switch'
    )
    parser.add_argument(
        '--check', type=str, help='Check to perform',
        choices=['cpu', 'links'],
        default='links',
    )
    parser.add_argument(
        '-v', dest='verbose', action='store_true',
        help='Verbose output - show OK ports',
    )
    parser.add_argument(
        '-w', dest='warning', type=int, help='Warning threshold', default=75)
    parser.add_argument(
        '-c', dest='critical', type=int, help='Critical threshold', default=90)

    snmp_mode = parser.add_mutually_exclusive_group(required=True)
    snmp_mode.add_argument('--community', help='SNMP community')
    snmp_mode.add_argument('--user', help='SNMPv3 user')

    parser.add_argument('--auth', help='SNMPv3 authentication key')
    parser.add_argument('--priv', help='SNMPv3 privacy key')
    parser.add_argument(
        '--priv_proto',
        help='SNMPv3 privacy protocol: aes (default) or des',
        default='aes'
    )
    return parser.parse_args()


def get_snmp_connection(args):
    """ Prepare SNMP transport agent.

        Connection over SNMP v2c and v3 is supported.
        The choice of authentication and privacy algorithms for v3 is
        arbitrary, matching what our switches can do.
    """

    if args.community:
        auth_data = CommunityData(args.community, mpModel=1)
    else:
        if args.priv_proto == 'des':
            priv_proto = usmDESPrivProtocol
        if args.priv_proto == 'aes':
            priv_proto = usmAesCfb128Protocol

        auth_data = UsmUserData(
            args.user, args.auth, args.priv,
            authProtocol=usmHMACSHAAuthProtocol,
            privProtocol=priv_proto,
        )

    transport_target = UdpTransportTarget((args.switch, 161))

    return {
        'auth_data': auth_data,
        'transport_target': transport_target,
    }


def get_snmp_value(snmp, OID):
    """ Get a single value from SNMP """

    errorIndication, errorStatus, errorIndex, varBinds = cmd_gen.getCmd(
        snmp['auth_data'],
        snmp['transport_target'],
        OID,
    )
    if errorIndication:
        raise SwitchException('Unable to get SNMP value: {}'
                              .format(errorIndication))

    return convert_snmp_type(varBinds)


def get_snmp_table(snmp, OID):
    """ Fetch a table from SNMP.

        Returned is a dictionary mapping the last number of OID (converted to
        Python integer) to value (converted to int or str).
    """

    ret = {}
    errorIndication, errorStatus, errorIndex, varBindTable = cmd_gen.bulkCmd(
        snmp['auth_data'],
        snmp['transport_target'],
        1,
        50,
        OID,
    )
    for varBind in varBindTable:
        # The joy of pysnmp library!
        # It might in fact return objects from another tree.
        if not str(varBind[0][0]).startswith(OID):
            break
        if errorIndication:
            raise SwitchException('Unable to get SNMP value: {}'.
                                  format(errorIndication))
        index = int(str(varBind[0][0][-1:]))
        ret[index] = convert_snmp_type(varBind)

    return ret


def convert_snmp_type(varBinds):
    """ Convert SNMP data types to something more convenient: int or str """
    val = varBinds[0][1]
    if type(val) in (Integer, Counter32, Counter64):
        return int(val)
    return str(val)


def get_switch_model(snmp):
    """ Recognize model of switch from SNMP MIB-2 sysDescr """

    model = get_snmp_value(snmp, OIDS['switch_model'])

    if 'PowerConnect' in model:
        return 'powerconnect'
    elif 'ProCurve' in model:
        return 'procurve'
    elif 'ExtremeXOS' in model:
        return 'extreme'
    elif 'Dell Networking OS' in model:
        return 'force10_mxl'

    raise SwitchException('Unknown switch model')


def check_ports(snmp, model, args):
    """ Check if ports have links established and if they have description """

    port_indexes = get_snmp_table(snmp, OIDS['if_index'])
    port_oper_states = get_snmp_table(snmp, OIDS['if_oper_status'])
    port_admin_states = get_snmp_table(snmp, OIDS['if_admin_status'])

    port_names = get_snmp_table(snmp, OIDS['if_name'])
    port_aliases = get_snmp_table(snmp, OIDS['if_alias'])

    # Strip port aliases.
    # The MXL switch returns 0x00 0x00 for an unnamed port.
    for port_name, port_alias in port_aliases.items():
        port_aliases[port_name] = port_alias.strip('\0')

    outmsg = ''
    exit_code = 0

    if not port_indexes:
        exit_code = 3
        outmsg = 'No ports found on the switch!'

    for port_index in sorted(port_indexes):

        # Filter out VLANs, CPU ports and LAGGs

        if model == 'extreme':
            if port_index >= 1000000:
                continue

        elif model == 'powerconnect':
            if (
                port_names[port_index].startswith('Vl') or
                port_names[port_index].startswith('CPU') or
                port_names[port_index].startswith('Po')
            ):
                continue
        elif model == 'procurve':
            if (
                port_names[port_index].startswith('DEFAULT_VLAN') or
                port_names[port_index].startswith('VLAN') or
                port_names[port_index].startswith('Trk') or
                port_names[port_index].startswith('lo0')
            ):
                continue
        elif model == 'force10_mxl':
            if (
                port_names[port_index].startswith('Vlan') or
                port_names[port_index].startswith('NULL') or
                port_names[port_index].startswith('ManagementEthernet') or
                port_names[port_index].startswith('Port-channel')
            ):
                continue

        local_exit = 1
        msg = (
            'WARNING: Unhandled bad status (admin: {}, oper:{})!'
            .format(
                port_admin_states[port_index], port_oper_states[port_index]
            )
        )

        # Stack port
        if port_oper_states[port_index] == 6:
            if port_admin_states[port_index] == 2:
                local_exit = 2
                msg = 'CRITICAL: Stack port disabled.'
            if port_admin_states[port_index] == 1:
                if not port_aliases[port_index]:
                    local_exit = 1
                    msg = 'WARNING: Stack port unnamed.'
                else:
                    local_exit = 0
                    msg = 'OK: Named and working stack port.'

        # Port is enabled
        elif port_admin_states[port_index] == 1:
            if not port_aliases[port_index]:
                if port_oper_states[port_index] == 1:
                    local_exit = 2
                    msg = 'CRITICAL: Unnamed port is up.'
                elif port_oper_states[port_index] == 2:
                    local_exit = 1
                    msg = 'WARNING: Unnamed port is enabled.'
            else:
                if port_oper_states[port_index] == 2:
                    local_exit = 2
                    msg = 'CRITICAL: Named port is down!'
                elif port_oper_states[port_index] == 1:
                    local_exit = 0
                    msg = 'OK: Port named, enabled and up.'

        # Port is disabled
        elif port_admin_states[port_index] == 2:
            if not port_aliases[port_index]:
                if port_oper_states[port_index] == 2:
                    local_exit = 0
                    msg = 'OK: Port unnamed, disabled and down.'
            else:
                local_exit = 2
                msg = 'WARNING: Named port is disabled.'

        if local_exit > 0 or args.verbose:
            outmsg += (
                '{} "{}": {}\n'.
                format(port_names[port_index], port_aliases[port_index], msg)
            )

        if local_exit > exit_code:
            exit_code = local_exit

    if exit_code == 0 and not args.verbose:
        outmsg = 'All ports are fine.'

    return exit_code, outmsg


def check_cpu(snmp, model, args):
    """ Measure CPU usage of a switch

        We use single OID which should percentage of CPU time used.
    """

    cpu_usage = get_snmp_value(snmp, CPU_OIDS[model])

    if model == 'powerconnect':
        # SNMP returns such ugly string
        #     5 Secs ( 18.74%)    60 Secs ( 17.84%)   300 Secs ( 18.12%)
        m = re.search('60 Secs \( *([0-9]+)[0-9\.]*%\)', cpu_usage)
        cpu_usage = int(m.group(1))
    else:
        cpu_usage = int(cpu_usage)

    outmsg = 'CPU usage is {}%'.format(cpu_usage)

    if cpu_usage > args.critical:
        return 2, outmsg

    if cpu_usage > args.warning:
        return 1, outmsg

    return 0, outmsg


if __name__ == '__main__':
    sys.exit(main())
