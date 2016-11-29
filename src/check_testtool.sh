#!/bin/sh

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

