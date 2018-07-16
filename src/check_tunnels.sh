#!/bin/sh
#
# InnoGames Monitoring Plugins - Tunnels Check
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

MLINE=""
BADIFS=""
EXIT_CODE=0

# Get a list of all interfaces.
for IFACE in `/sbin/ifconfig -l`; do
	# Work only on gre_* and gif_* interfaces.
	if echo "${IFACE}" | grep -qE '^(gif|gre)_'; then
		# Get interface configuration, remove newlines.
		IFCONFIG="$(/sbin/ifconfig ${IFACE})"
		LOCAL_EXIT=0

		# Check if interface is UP or DOWN.
		if echo "${IFCONFIG}" | grep -q UP; then

			# For UP interface get peer's IP address and ping it.
			IP=$(echo "${IFCONFIG}" | awk '/^[ \t]+inet / {print $4}')  # only IPv4!

			# Ping the tunnel endpoing. Don't resolve DNS, be quiet, send 10 pings, with 100ms delay and wait up to 1s for answer.
			PING_RAW=$(/usr/local/bin/sudo -u root /sbin/ping -n -q -c10 -i 0.1 -W1000 "${IP}" 2>&1)
			PING_EXIT=$?

			if [ $PING_EXIT -eq 0 ] || [ $PING_EXIT -eq 2 ]; then
				# round-trip min/avg/max/stddev = 0.164/0.286/0.440/0.087 ms
				PING=$(echo "${PING_RAW}" | awk 'BEGIN {FS="[/ ]"}; /round-trip/ {print $8}')
				PING_INT=${PING%.*}

				# 10 packets transmitted, 0 packets received, 100.0% packet loss
				LOSS=$(echo "${PING_RAW}" | awk '/packet loss/ {print $7}')
				LOSS=${LOSS%\%*}
				LOSS_INT=${LOSS%.*}

				THISIF="${IFACE}: UP, ping ${PING}ms, loss ${LOSS}%"

				[ "${PING_INT}" -gt 200 ] && LOCAL_EXIT=1
				[ "${LOSS_INT}" -gt  20 ] && LOCAL_EXIT=2
			else
				THISIF="${IFACE}: Ping failure: $PING_RAW"
				LOCAL_EXIT=2
			fi


			[ "$LOCAL_EXIT" -ne 0 ] && BADIFS="${IFACE}, ${BADIFS}"
		else
			LOCAL_EXIT=1
			THISIF="${IFACE}: ifconfig down"
		fi

		[ $LOCAL_EXIT -gt $EXIT_CODE ] && EXIT_CODE=$LOCAL_EXIT

		MLINE="${THISIF};${MLINE}"
	fi
done

if [ -n "$BADIFS" ]; then
	echo "Tunnels with problems: $BADIFS"
else
	echo "All tunnels are fine"
fi

echo "${MLINE}" | tr ';' '\n'

exit $EXIT_CODE
