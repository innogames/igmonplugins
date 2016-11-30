#!/bin/sh

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

