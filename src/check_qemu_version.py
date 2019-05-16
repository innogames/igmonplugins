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


from subprocess import Popen, PIPE, STDOUT, DEVNULL
from argparse import ArgumentParser

import platform
import re
import psutil
import apt_pkg


def get_args():
    parser = ArgumentParser(
        description=(
            'Check if QEMU version of domains aren\'t newer than the '
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
    same = 0  # Same version
    newer = 1  # Domain newer than HV
    older = 2  # Domain older than HV
    unknown = 3


class HVQEMUVersionException(Exception):
    """Raised when Hypervisor QEMU version can't be retrieved"""
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


def parse_qemu_version(version):
    r = re.compile(r'.*version\s([\d\.]+\([\w\d\.\s:\+-]+\)).*')
    match = r.match(version)
    # Return None if couldn't match string. Deal with None as couldn't
    # retrieve version.
    if match is None:
        return None
    return match.group(1)


def get_domain_list():
    domains = []
    hvname = platform.node()
    r = re.compile(r'guest=(\d+_)?([\w\.\d-]+)')
    for proc in psutil.process_iter():
        if proc.username() != 'libvirt-qemu':
            continue
        vmname = list(filter(r.match, proc.cmdline()))[0]
        if vmname:
            domain = {
                'pid':    proc.pid,
                'vmname': r.search(vmname).group(2),
                'hvname': hvname
            }
            domains.append(domain)
    return domains


def check_versions(domains):
    # Get QEMU on the hypervisor
    result = execute(
        ['/usr/bin/qemu-system-x86_64', '-version']
    )
    hypervisor_qemu_version = parse_qemu_version(result)
    if hypervisor_qemu_version is None:
        raise HVQEMUVersionException()
    for domain in domains:
        result = execute(
            ['/proc/{}/exe'.format(domain['pid']), '-version']
        )
        version = parse_qemu_version(result)
        # QEMU version couldn't be obtained for domain
        if version is None:
            domain['status'] = CheckResult.unknown
            continue
        domain['version'] = version
        vc = apt_pkg.version_compare(
            domain['version'],
            hypervisor_qemu_version
        )
        if vc > 0:
            domain['status'] = CheckResult.newer
        elif vc == 0:
            domain['status'] = CheckResult.same
        else:
            domain['status'] = CheckResult.older

    return hypervisor_qemu_version, domains


def build_nsca_output(hypervisor_qemu_version, domains):
    nsca_output = ''
    newer_doms = []
    unknown_doms = []
    for domain in domains:
        if domain['status'] == CheckResult.unknown:
            unknown_doms.append(domain['vmname'])
            nsca_output += (
                '{}\tqemu_version\t{}\tUNKNOWN - '
                'QEMU domain version could not be determined on HV'
                ' {}.'
                    .format(
                    domain['vmname'], ExitCodes.unknown,
                    domain['hvname']
                )
            )
        elif domain['status'] == CheckResult.newer:
            newer_doms.append(domain['vmname'])
            nsca_output += (
                '{}\tqemu_version\t{}\tWARNING - '
                'QEMU domain version is newer than HV {} version'
                '. Domain: {} Hypervisor: {}\x17'
                    .format(
                    domain['vmname'], ExitCodes.warning,
                    domain['hvname'], domain['version'],
                    hypervisor_qemu_version
                )
            )
        else:
            nsca_output += (
                '{}\tqemu_version\t{}\tOK - '
                'QEMU domain version is acceptable.\x17'
                    .format(
                    domain['vmname'], ExitCodes.ok,
                    domain['hvname']
                )
            )

    return nsca_output, newer_doms, unknown_doms


def build_plugin_output(newer_doms, unknown_doms, nsca_result):
    # If version mismatches happened
    if not nsca_result:
        return (ExitCodes.warning,
                'Error when pushing passive check results with '
                'NSCA'
                )
    elif newer_doms:
        return (ExitCodes.warning, (
            'QEMU version mismatch. Virtual machines {}'
            ' have a version newer than HV.')
                .format(', '.join(newer_doms))
                )
    # If any machine couldn't have version retrieved
    elif unknown_doms:
        return (ExitCodes.unknown, (
            'Error obtaining QEMU version. Could not '
            'obtain QEMU version for virtual '
            'machines {}.')
                .format(', '.join(unknown_doms))
                )
    else:
        return ExitCodes.ok, 'All versions are acceptable.'


def send_nsca(hosts, output):
    result = True
    for monitor in hosts:
        nsca = Popen(
            [
                '/usr/sbin/send_nsca',
                '-H', monitor,
                '-c', '/etc/send_nsca.cfg',
            ],
            stdin=PIPE,
            stdout=DEVNULL,
            stderr=DEVNULL
        )
        nsca.communicate(output.encode())
        returncode = nsca.wait()
        if returncode > 0:
            result = False

    return result


def main():
    args = get_args()

    # Initialize apt system
    apt_pkg.init_system()

    # Get domain list
    domains = get_domain_list()

    # Get back domains with version result
    try:
        hypervisor_qemu_version, domains = check_versions(domains)
    except HVQEMUVersionException:
        print_nagios_message(
            ExitCodes.unknown, 'Could not retrieve hypervisor QEMU version'
        )
        exit(ExitCodes.unknown)
    except Exception:
        print_nagios_message(
            ExitCodes.warning,
            'An exception occurred when retrieving HV QEMU version'
        )
        exit(ExitCodes.warning)

    # Build output
    nsca_output, mismatch_doms, unknown_doms \
        = build_nsca_output(hypervisor_qemu_version, domains)
    # Push NSCA results
    nsca_result = send_nsca(args.hosts, nsca_output)

    # Generate plugin results for HV
    code, reason = build_plugin_output(
        mismatch_doms, unknown_doms, nsca_result
    )

    print_nagios_message(code, reason)
    exit(code)


if __name__ == '__main__':
    main()
