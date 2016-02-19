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

statefile="/var/lib/nagios3/check_swapping.db"
limit=2500 #// Blocks writen to swap
out_new=0
out_old=0

[[ -r $statefile ]] && {
    out_old=$(<$statefile) || {
        echo "CRITICAL - Error while reading '$statefile'!"
        exit 2
    }
}

[[ -r /proc/vmstat ]] || {
    echo "CRITICAL - Error - cant read '/proc/vmstat'!"
    exit 2
}

line=$( grep pswpout /proc/vmstat )
out_new=${line#* }

[[ $out_old -eq 0 ]] && out_old=$out_new

echo "$out_new" > $statefile || {
	echo "CRITICAL - Error - cant write to '$statefile'!"
	exit 2
}

[[ $out_new -gt $(($out_old + $limit)) ]] && {
    echo "WARNING - System is swapping ($(( $out_new - $out_old )) blocks writen to swap since last check) !"
    exit 1
}

# Test if /etc/fstab has an entry 'swap' that doesn't start with a '#' (plus spaces)
# AND test if 'swapon -s' will show more than the table header (<2 lines on error)
[[ "$( grep -E '^[^# ]+.*swap' /etc/fstab | wc -l )" -gt 0 ]] &&
[[ "$( swapon -s | wc -l )" -lt 2 ]] && {
    echo "WARNING - Swap is disabled. Use 'swapon -a' to enable it!"
    exit 1
} || {
    echo "OK - No swap activity"
    exit 0
}
