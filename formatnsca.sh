#!/bin/bash
#
# InnoGames Monitoring Plugins - formatnsca.sh
#
# Copyright (c) 2016, InnoGames GmbH
#
# This is an helper script to format output for NSCA.  It is useful for checks
# that run long enough not to be used as an active one.  With this wrapper,
# you can get the data from them to be send to the monitoring server via NSCA.
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

if ! [ "$2" ]; then
    echo "Usage: $0 service command arguments" >&2
    exit 3
fi

hostname=$(hostname)
service=$1
output=$(${@:2})    # Run the command.
exitcode=$?

echo -e "$hostname\t$service\t$exitcode\t$output"
