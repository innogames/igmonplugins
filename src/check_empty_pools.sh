#!/bin/sh

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

