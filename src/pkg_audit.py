#!/usr/bin/env python3

"""InnoGames Monitoring Plugins - audit installed packages and kernel against known vulnerabilities

Copyright © 2023 InnoGames GmbH
"""

import json
import platform
import subprocess

from re import sub


def main():
    # `pkg audit` will exit with an error code if there are vulnerable packages installed
    # so we must use run() directly instead of the check_output() helper.
    proc = subprocess.run(['pkg', 'audit', '-Rjson'], capture_output=True, check=False)
    pkg_audit = json.loads(proc.stdout.decode().strip())

    # Based on /usr/local/etc/periodic/security/405.pkg-base-audit
    kernel_version = 'FreeBSD-kernel-' + platform.release()
    kernel_version = sub('-RELEASE-p', '_', kernel_version)
    kernel_version = sub('-RELEASE$', '', kernel_version)
    proc = subprocess.run(['pkg', 'audit', '-Rjson', kernel_version], capture_output=True, check=False)
    kernel_audit = json.loads(proc.stdout.decode().strip())

    exit_code = ExitCodes.ok
    message = 'No vulnerabilities found on this system'

    audit = {}
    if 'packages' in pkg_audit:
        audit.update(pkg_audit['packages'])
    if 'packages' in kernel_audit:
        audit.update(kernel_audit['packages'])

    if len(audit) > 0:
        exit_code = ExitCodes.warning
        message = f'There are {len(audit)} packages with vulnerabilities found | '
        perf_data = []
        for pkg_name, pkg_data in audit.items():
            perf_data.append(f'{pkg_name}={len(pkg_data["issues"])}')
        message += ' '.join(perf_data)

    print_nagios_message(exit_code, message)
    exit(exit_code)


def print_nagios_message(code, output):
    if code == ExitCodes.ok:
        state_text = 'OK'
    elif code == ExitCodes.warning:
        state_text = 'WARNING'
    elif code == ExitCodes.critical:
        state_text = 'CRITICAL'
    else:
        state_text = 'UNKNOWN'
    print('{} - {}'.format(state_text, output))


class ExitCodes:
    ok = 0
    warning = 1
    critical = 2
    unknown = 3


if __name__ == '__main__':
    main()
