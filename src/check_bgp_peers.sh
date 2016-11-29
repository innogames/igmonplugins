#!/bin/sh

# Nagios return codes
#0   OK
#1   WARNING
#2   CRITICAL
#3   UNKNOWN

protos=`birdc 'show protocols' | awk '$2=="BGP" { print $1":"$6}'`

for proto in $protos; do
	router=${proto%:*}
	status=${proto#*:}

	if [ "$status" != "Established" ]; then
		CRIT="yes"
		dead="$dead $router"
	fi
done

if [ -n "$CRIT" ]; then
	echo "No connection to routers $dead!"
else
	echo "All routers are fine."
fi


for proto in $protos; do
	router=${proto%:*}
	status=${proto#*:}

	echo "$router is $status"
done


if [ -n "$CRIT" ]; then
	exit 2
else
	exit 0
fi

