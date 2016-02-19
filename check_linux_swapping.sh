#!/bin/bash
#
# InnoGames Monitoring Plugins - check_swapping.sh
#
# Copyright (c) 2016, InnoGames GmbH
#
# This script checks for the swap-activity.  It is not useful to check
# the used swap space, because it is never get cleaned.
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

statefile="/tmp/check_linux_swapping.db"
limit=2500 # Blocks written to swap
out_new=0
out_old=0

if [[ -r $statefile ]]; then
    out_old=$(<$statefile)

    if [[ $? -ne 0 ]]; then
        echo "UNKNOWN - Error while reading '$statefile'!"
        exit 3
    fi
fi

if [[ ! -r /proc/vmstat ]]; then
    echo "UNKNOWN - Error - cant read '/proc/vmstat'!"
    exit 3
fi

line=$(grep pswpout /proc/vmstat)
out_new=${line#* }

if [[ $out_old -eq 0 ]]; then
    out_old=$out_new
fi

echo "$out_new" > $statefile

if [[ $? -ne 0 ]]; then
	echo "UNKNOWN - Error - cant write to '$statefile'!"
	exit 3
fi

if [[ $out_new -gt $(($out_old + $limit)) ]]; then
    echo "WARNING - System is swapping ($(($out_new - $out_old)) blocks written to swap since last check)!"
    exit 1
fi

# Test if /etc/fstab has an entry 'swap' that doesn't start with a '#' (plus spaces)
# AND test if 'swapon -s' will show more than the table header (<2 lines on error)
if [[ "$( grep -E '^[^# ]+.*swap' /etc/fstab | wc -l )" -gt 0 ]] &&
   [[ "$( swapon -s | wc -l )" -lt 2 ]]; then
    echo "WARNING - Swap is disabled. Use 'swapon -a' to enable it!"
    exit 1
fi

echo "OK - No swap activity"
exit 0
