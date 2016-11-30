#!/bin/sh

# Nagios return codes
#0   OK
#1   WARNING
#2   CRITICAL
#3   UNKNOWN

TF="/etc/iglb/translate_poolnames.conf"
PF="/etc/iglb/pf.conf"
SF="/var/log/testtool.status"
TMPF="/tmp/check_lbpool.tmp"

rm $TMPF 2>/dev/null

if [ -z "$TF" ]; then
	echo "Could not read pool list file"
	exit 1
fi

if [ -z "$PF" ]; then
	echo "Could not read pf.conf file"
	exit 1
fi

# master ok   - OK - my role is MASTER
# master fail - CR - y role is MASTER; carp 103 is BACKUP; carp 143 is BACKUP;
# backup ok   - OK - my role is BACKUP
# backup fail - CR - grep -E 'role is BACKUP, carp([a-z0-9]| ?)+ is MASTER'

CARP=`/usr/local/libexec/nagios/igmonplugins/check_carps.py`

CARPEXIT=$?

if [ -z "$CARP" ]; then
	echo "Can't determine CARP status"
	exit 1
fi

if grep -q "'`hostname | cut -d . -f 1`'": /etc/iglb/carp_settings.py; then
	ROLE=MASTER
else
	ROLE=BACKUP
fi

case $ROLE in
	MASTER)
		if [ $CARPEXIT -eq 2 ]; then
			echo "Skipping test for MASTER HWLB in BACKUP state"
			exit 1
		fi
		;;
	BACKUP)
		if [ $CARPEXIT -eq 0 ]; then
			echo "Skipping test for BACKUP HWLB in BACKUP state"
			exit 1
		fi
		;;
	*)
		echo "could not determine master/backup function";
		exit 3
		;;
esac


while read LINE; do
	[ -z "$LINE" ] && continue

	# Convert line to $1 $2
	set $LINE

	NODES=`grep "lbpool: $1 " $SF | cut -d ' ' -f 4`

	if [ -z "$NODES" ]; then
		NODES=`sed -En "/^table <$1> {/s/.*{ *([0-9\. ]+) *}.*/\1/p" $PF | wc -w`
		if [ "$NODES" -eq 1 ]; then
			printf '%s\tcheck_lbpool\t%d\tOK: Pool is not monitored by testtool but has only 1 node\27' $2 0 >> $TMPF
		elif [ "$NODES" -eq 0 ]; then
			# Pool has 0 nodes and is not monitored. It probably does not exist in Admintool anyway.
			continue
		else
			printf '%s\tcheck_lbpool\t%d\tWARNING: Pool is not monitored by testtool but has %d nodes\27' $2 1 $NODES >> $TMPF
		fi
	else
		if [ "$NODES" -gt 0 ]; then
			printf '%s\tcheck_lbpool\t%d\tOK: Pool has %d nodes alive\27' $2 0 $NODES >> $TMPF
		else
			printf '%s\tcheck_lbpool\t%d\tCRITICAL:Pool has %d nodes alive\27' $2 2 $NODES >> $TMPF
		fi
	fi

done < $TF

#tr '\27' '\n' < $TMPF

/usr/local/sbin/send_nsca -H af-monitor.ig.local. -c /usr/local/etc/nagios/send_nsca.cfg < $TMPF
/usr/local/sbin/send_nsca -H aw-monitor.ig.local. -c /usr/local/etc/nagios/send_nsca.cfg < $TMPF
