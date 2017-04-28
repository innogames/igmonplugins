#!/bin/sh
#
# InnoGames Monitoring Plugins - check_carps_simple.sh
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

getcarps () {
	ifconfig | sed -En ':iface
	{ /metric/{s/([a-z0-9]+):.*/\1/; h;}; /carp:/{H;g;s/\n//;s/^([a-z0-9]+).*carp: ([A-Z]+) vhid ([0-9]+).*/\1 vhid \3 \2/;p;}; d; };
	/metric/biface'
}

CARPS=`getcarps`

if hostname | grep -vq 2; then
	ROLE=MASTER
	BADCARPS=`echo "$CARPS" | grep -v $ROLE`

	if [ -n "$BADCARPS" ]; then
		echo "CRITICAL: my role is $ROLE but some carps are wrong:"
		echo "$CARPS"
		exit 2
	fi
else
	ROLE=BACKUP
	BADCARPS=`echo "$CARPS" | grep -v $ROLE`

	if [ -n "$BADCARPS" ]; then
		echo "CRITICAL: my role is $ROLE but some carps are wrong:"
		echo "$CARPS"
		exit 2
	fi
fi

echo "OK: my role is $ROLE and all carps are fine"
echo "$CARPS"
exit 0

