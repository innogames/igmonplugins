#!/bin/sh
#
# InnoGames Monitoring Plugins - check_empty_pools.sh
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

# Nagios return codes
#0   OK
#1   WARNING
#2   CRITICAL
#3   UNKNOWN

status_file="/var/log/testtool.status"

if [ -f $status_file ]; then
	ALL_OK="YES"
	EMPTY_POOLS=""

	while read line; do
		if echo "$line" | grep -qE 'nodes_alive: 0|backup_pool: active'; then
			ALL_OK="NO"
			POOL=`echo "$line" | cut -d ' ' -f 2`
			EMPTY_POOLS="${EMPTY_POOLS}${POOL} "
		fi
	done < $status_file

	case "$ALL_OK" in
		"NO"*)
		echo "EMPTY OR BACKUP POOLS: $EMPTY_POOLS"
		exit 2;;
		"YES"*)
		echo "OK: All pools have nodes to serve traffic."
		exit 0;;
	esac

else
	echo "NO STATUS FILE: No status file found."
	exit 3
fi

