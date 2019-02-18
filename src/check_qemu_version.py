#!/usr/bin/env python
"""InnoGames Monitoring Plugins - QEMU Version Check

Copyright (c) 2019 InnoGames GmbH
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


from subprocess import Popen, PIPE, STDOUT
from argparse import ArgumentParser

import platform
import re
import psutil

hypervisor_qemu_version = False


def get_args():
    parser = ArgumentParser(
        description=(
            'Check if QEMU version of domains matches the '
            'version on the Hypervisor running them'
        )
    )
    parser.add_argument(
        '-H',
        dest='hosts',
        type=str,
        action='append',
        required=True,
        help=(
            'Hosts to which NSCA notifications will be sent to.'
        )
    )

    return parser.parse_args()


class ExitCodes:
    ok = 0
    warning = 1
    critical = 2
    unknown = 3


class CheckResult:
    match = 0
    mismatch = 1
    unknown = 2


class CheckException(Exception):
    """Raised to exit with a valid nagios state"""
    pass


def print_nagios_message(code, reason):
    if code == ExitCodes.ok:
        state_text = 'OK'
    elif code == ExitCodes.warning:
        state_text = 'WARNING'
    elif code == ExitCodes.critical:
        state_text = 'CRITICAL'
    else:
        state_text = 'UNKNOWN'
    print('{} - {}'.format(state_text, reason))


def execute(cmd):
    process = Popen(
        cmd,
        stdout=PIPE,
        stderr=STDOUT,
    )
    content = process.communicate()[0].decode()
    returncode = process.wait()

    if returncode > 0:
        return False

    return content


def get_domain_list():
    domains = []
    hvname = platform.node()
    r = re.compile(r'guest=\d+_([\w\-\.]+)')
    for proc in psutil.process_iter():
        if proc.username() != 'libvirt-qemu':
            continue
        vmname = list(filter(r.match, proc.cmdline()))[0]
        if vmname:
            domain = {
                'pid': proc.pid,
                'vmname': r.search(vmname).group(1),
                'hvname': hvname
                }
            domains.append(domain)
    return domains


def check_versions(domains):
    # Get QEMU on the hypervisor
    hypervisor_qemu_version = execute(
        ['/usr/bin/qemu-system-x86_64', '-version']
        )
    if not hypervisor_qemu_version:
        return CheckResult.unknown, 'Could not retrieve QEMU version for '
        'hypervisor {}.'.format(platform.node())

    for domain in domains:
        domain['version'] = execute(
            ['/proc/{}/exe'.format(domain['pid']), '-version']
            )

        # QEMU version couldn't be obtained for domain
        if not domain['version']:
            domain['status'] = CheckResult.unknown

        if domain['version'] == hypervisor_qemu_version:
            domain['status'] = CheckResult.match
        else:
            domain['status'] = CheckResult.mismatch

    return domains


def build_nsca_output(domains):
    nsca_output = ''
    mismatch_doms = []
    unknown_doms = []
    for domain in domains:
        if domain['status'] == CheckResult.match:
            nsca_output += ('{}\tqemu_version\t{}\tOK - '
                            'QEMU domain version matches HV {} version.\x17'
                            .format(
                                    domain['vmname'], ExitCodes.ok,
                                    domain['hvname']
                                    ))
        elif domain['status'] == CheckResult.mismatch:
            mismatch_doms.append(domain)
            nsca_output += ('{}\tqemu_version\t{}\tWARNING - '
                            'QEMU domain version DOES NOT match HV {} version'
                            '. Domain: {} Hypervisor:{}\x17'
                            .format(
                                    domain['vmname'], ExitCodes.warning,
                                    domain['hvname'], domain['version'],
                                    hypervisor_qemu_version
                                    ))
        elif domain['status'] == CheckResult.unknown:
            unknown_doms.append(domain)
            nsca_output += ('{}\tqemu_version\t{}\tUNKNOWN - '
                            'QEMU domain version could not be determined on HV'
                            ' {}.'
                            .format(
                                    domain['vmname'], ExitCodes.unknown,
                                    domain['hvname']
                                    ))

    return nsca_output, mismatch_doms, unknown_doms


def build_plugin_output(mismatch_doms, unknown_doms):
    # If version mismatches happened
    if mismatch_doms:
        return (ExitCodes.warning,
                'QEMU version mismatch. Virtual machines {}'
                ' do not match HV QEMU version.'
                .format(', '.join(mismatch_doms))
                )
    # If any machine couldn't have version retrieved
    elif unknown_doms:
        return (ExitCodes.unknown, 'Error obtaining QEMU version. Could not '
                'obtain QEMU version for virtual machines {}.'
                .format(', '.join(unknown_doms))
                )
    else:
        return ExitCodes.ok, 'All versions match.'


def send_nsca(hosts, output):
    for monitor in hosts:
        nsca = Popen(
                [
                    '/usr/sbin/send_nsca',
                    '-H', monitor,
                    '-c', '/etc/send_nsca.cfg',
                ],
                stdin=PIPE,
            )
        nsca.communicate(output.encode())
        returncode = nsca.wait()
        if returncode > 0:
            return False

    return True


def main():
    args = get_args()

    # Get domain list
    domains = get_domain_list()

    # Get back domains with version result
    domains = check_versions(domains)

    # Build output
    nsca_output, mismatch_doms, unknown_doms \
        = build_nsca_output(domains)

    # Push NSCA results
    nsca = send_nsca(args.hosts, nsca_output)
    if not nsca:
        print_nagios_message(ExitCodes.critical,
                             'Error when pushing VM results with NSCA')

    # Generate plugin results for HV
    code, reason = build_plugin_output(
        mismatch_doms, unknown_doms
        )

    print_nagios_message(code, reason)
    exit(code)


if __name__ == '__main__':
    main()
