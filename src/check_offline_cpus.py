#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Offline CPU check

Copyright (c) 2023 InnoGames GmbH
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


def get_cpus():
    """
    Get the number of total and offline CPU cores.

    Returns:
    tuple: A tuple containing the number of total CPU
           cores and the list of offline CPU cores.
    """

    # Get the list of offline CPU cores
    offline_cpus = subprocess.check_output(
        "lscpu | grep '^Off-line CPU(s) list:' | awk -F: '{print $2}'",
        shell=True
    ).strip().decode()

    # Get the number of total CPU cores
    total_cpus = subprocess.check_output(
        "lscpu | grep '^CPU(s):' | awk '{print $2}'",
        shell=True
    ).strip().decode()

    return total_cpus, offline_cpus


def main():

    total_cpus, offline_cpus = get_cpus()

    if offline_cpus:
        print(f"WARNING - {offline_cpus} out of {total_cpus} CPUs are offline")
        sys.exit(1)

    print(f"OK - All {total_cpus} CPUs are online")
    sys.exit(0)


if __name__ == "__main__":
    """Main entry point"""
    main()
