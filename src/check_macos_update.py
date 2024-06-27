#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Check for pending MacOS updates

This is a Nagios script which checks if there are any recommended updates
for the current major version of macOS. It will only warn.

Copyright (c) 2024 InnoGames GmbH
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

import subprocess
import sys
from typing import List
import re


def main():
    if sys.platform != "darwin":
        print("UNKNOWN - This script is only supported on macOS")
        sys.exit(3)

    current_os_version = get_os_version()
    update_list = get_update_list()

    lines = update_list.split("\n")
    updates = filter_relevant_updates(lines, current_os_version)

    if updates:
        print(
            f"WARNING - {len(updates)} recommended updates are available for MacOS {current_os_version}:"
        )
        for update in updates:
            print(
                f"{update}: sudo softwareupdate --restart --os-only --install {update}"
            )
        sys.exit(1)

    print("OK - No recommended updates available")
    sys.exit(0)


def get_update_list() -> str:
    """
    Get the list of available updates from the macOS software update tool.

    Returns:
        str: A string output of available updates, provided by "softwareupdate -l".
    """
    try:
        result = subprocess.run(
            ["softwareupdate", "--product-types=macOS", "--no-scan", "--list"],
            capture_output=True,
            text=True,
            check=True,
        )
        output = result.stdout
    except subprocess.CalledProcessError as err:
        print(f"UNKNOWN - Unable to check for updates: {err.stderr}")
        sys.exit(3)

    return output


def get_os_version() -> str:
    """
    Get the current OS version.

    Returns:
        str: The major version number of the current macOS, e.g., "13" for macOS Ventura.
    """
    result = subprocess.run(
        ["sw_vers", "-productVersion"], capture_output=True, text=True, check=True
    )

    return result.stdout.strip()


def filter_relevant_updates(lines: List[str], current_os_version: str) -> List[str]:
    """
    Filter the list of updates to include only relevant updates for the current major macOS version.

    Args:
        lines (List[str]): The list of update details.
        current_os_version (str): The current version of macOS.

    Returns:
        List[str]: A list of relevant update titles.
    """
    relevant_updates = []

    current_major_os_version = current_os_version.split(".")[0]
    for line in lines:
        if "Recommended: YES" not in line or "Title: macOS" not in line:
            continue

        version_match = re.search(r"Version: ([\d.]+),", line)
        if version_match:
            version = version_match.group(1)
            if current_major_os_version != version.split(".")[0]:
                # ignore updates for other major versions
                continue

            relevant_updates.append(version)

    return relevant_updates


if __name__ == "__main__":
    main()
