#!/bin/bash
#
# InnoGames Monitoring Plugins - Exim Delivery Check
#
# Copyright (c) 2017 InnoGames GmbH
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

set -euo pipefail

log_dir="/var/spool/exim4/msglog/"
input_dir="/var/spool/exim4/input/"
max_message=10
max_age=1200

for dir in "$log_dir" "$input_dir"; do
    if ! [ -d "$dir" ]; then
        echo "Can not open $dir"
        exit 1
    fi
done


messages=$(find "$log_dir" -maxdepth 1 -type f | wc -l)
if [ "$messages" -gt "$max_message" ]; then
    echo "To many messages in queue ($messages > $max_message). See $log_dir"
    exit 1
fi


oldest_message=$(find "$input_dir" -type f -printf '%T@\n' | sort | head -n1)
if [ "$oldest_message" ]; then
    oldest_age="$(($(date +%s) - ${oldest_message%.*}))"
    if [ "$oldest_age" -gt "$max_age" ]; then
        echo "The oldest_message in the queue older than $max_age seconds: $oldest_age"
        exit 1
    fi
fi

echo "OK - exim seems to work properly"
