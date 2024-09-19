#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Postgres Indexes Validity Check

This script checks if there are any invalid indexes across multiple PostgreSQL
databases. It queries pg_index to check for any invalid indexes.

Copyright (c) 2024
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


def main():
    """Main entrypoint for script"""
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} db1 [db2 ... dbN]")
        sys.exit(2)

    databases = sys.argv[1:]
    invalid_indexes = check_invalid_indexes(databases)

    if invalid_indexes:
        print(
            f"WARNING - There are invalid indexes in the following databases: {', '.join(invalid_indexes)}"
        )
        sys.exit(1)
    else:
        print("OK - All indexes are valid in all specified databases")
        sys.exit(0)


def check_invalid_indexes(databases):
    """Check for invalid indexes in the specified databases

    :param databases: list of database names
    :return: list of databases with invalid indexes
    """
    query = (
        "SELECT exists(SELECT indexrelid FROM pg_index i WHERE i.indisvalid IS FALSE);"
    )
    invalid_dbs = []

    for db in databases:
        try:
            result = (
                subprocess.check_output(
                    ["psql", db, "-XqtAc", query], stderr=subprocess.STDOUT
                )
                .decode()
                .strip()
            )
            if result != "f":
                invalid_dbs.append(db)
        except subprocess.CalledProcessError as e:
            print(f"Error checking database {db}: {e.output.decode().strip()}")
            sys.exit(2)

    return invalid_dbs


if __name__ == "__main__":
    main()
