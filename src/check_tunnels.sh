#!/bin/sh
#
# InnoGames Monitoring Plugins - check_tunnels.sh
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

EXIT_WARNING="no"
EXIT_CRITICAL="no"

MLINE=""
BADIFS=""

# Get a list of all interfaces.
for iface in `/sbin/ifconfig -l`; do
	# Work only on gre_* and gif_* interfaces.
	if echo "${iface}" | grep -qE '^(gif|gre)_'; then
		# Get interface configuration, remove newlines.
		IFCONFIG=`/sbin/ifconfig ${iface} | tr '\n' ' '`

		# Check if interface is UP or DOWN.
		if echo "${IFCONFIG}" | grep -q UP; then
			# For UP interface get peer's IP address and ping it.
			IP=`echo "${IFCONFIG}" | sed -E 's/.* --> ([0-9\.]+) netmask.*/\1/'`  # only IPv4!
			# Ping the tunnel endpoing. Don't resolve DNS, be quiet, send 10 pings, with 100ms delay and wait up to 1s for answer.
			PING_RAW=`/usr/local/bin/sudo -u root /sbin/ping -n -q -c10 -i 0.1 -W1000 "${IP}"`
			# 10 packets transmitted, 0 packets received, 100.0% packet loss
			PING=`echo "${PING_RAW}" | grep "round-trip"  | sed -E 's/.* = [0-9\.]+\/([0-9]+)\.[0-9]+\/.*/\1/'`
			# 10 packets transmitted, 0 packets received, 100.0% packet loss
			LOSS=`echo "${PING_RAW}" | grep "packet loss" | sed -E 's/.*, ([0-9]+)\..* packet loss/\1/'`
	
			THISIF="${iface}: UP, ping ${PING}ms, loss ${LOSS}%"

			[ "${LOSS}" -gt  20 ] && EXIT_CRITICAL="yes"
			[ "${PING}" -gt 350 ] && EXIT_WARNING="yes"

			[ "${LOSS}" -gt  20 ] || [ "${PING}" -gt 350 ] && BADIFS="${iface}, ${BADIFS}"
		else
			EXIT_WARNING="yes"
			THISIF="${iface}: ifconfig down"
		fi

		MLINE="${THISIF};${MLINE}"
	fi
done

if [ -n "$BADIFS" ]; then
	echo "Tunnels with problems: $BADIFS"
else
	echo "All tunnels are fine"
fi
echo
echo "${MLINE}" | tr ';' '\n'

[ "${EXIT_CRITICAL}" == "yes" ] && exit 2
[ "${EXIT_WARNING}"  == "yes" ] && exit 1 

exit 0 # OK if no trouble

