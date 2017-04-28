#!/usr/bin/awk -f
#
# InnoGames Monitoring Plugins - check_open_deleted_files.awk
#
# Copyright (c) 2017, InnoGames GmbH
#
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
#

BEGIN {
    mebibytes_warning = ARGV[1]
    if (mebibytes_warning !~ /^[0-9]+$/) {
        print "Usage: "ARGV[0] " -f check_open_deleted_files.awk <warning_threshold_MiB>"
        exit 3
    }

    M = 1048576
    cmd = "/usr/bin/lsof -n"
    while (cmd | getline line) {
        split(line, line_split)
        if (line_split[10] == "(deleted)") {
            total_waste += line_split[7]/M
            if (line_split[7] > mebibytes_warning*M) {
                message = message "\n" line_split[7]/M " MiB wasted by " line_split[9]
            }
        }
    }
    close(cmd)

    print total_waste " MiB wasted by deleted files" message
    if (total_waste > mebibytes_warning) {
        exit 1
    }
}
