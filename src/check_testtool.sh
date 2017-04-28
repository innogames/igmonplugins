#!/bin/sh
#
# InnoGames Monitoring Plugins - check_testtool.sh
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

if [ ! -f $status_file ]; then
	echo "NO STATUS FILE: Could not read Testtool's status file."
	exit 2
fi

FSTAMP=`head -n1 /var/log/testtool.status | awk '{print $4" "$5}'`
TIMTTL=`date -jf '%Y-%m-%d %H:%M:%S.' "$FSTAMP" '+%s'`
TIMCUR=`date '+%s'`

case $TIMTTL in
	''|*[!0-9]*)
		echo "NO STATUS FILE: Could not read time from Testtool's status file."
		exit 2
		;;
        *)
		;;
esac

if [ $(( "$TIMCUR"-"$TIMTTL" )) -gt 120 ]; then
	echo "TIME EXCEEDED: Testtool's status log was not updated for longer than 2 minutes."
	exit 2
fi

echo "OK: Testtool has recently updated its status file."
exit 0

