#!/bin/sh

# Nagios return codes
#0   OK
#1   WARNING
#2   CRITICAL
#3   UNKNOWN

birdc 'show protocols' | awk '$2=="BGP" { ORS=" "; print $1":"; for (i=6; i<=NF; i++) print $i; ORS="\n"; print ""}' > /tmp/bgpstatus

while read proto; do
    router=${proto%%:*}
    status=${proto#*:}
    status=${status# *}

    if [ "$status" != "Established" ]; then
        CRIT="yes"
    fi
    routers="${routers}${router}: ${status}"$'\n'
done < /tmp/bgpstatus

if [ -n "$CRIT" ]; then
    echo "No connection to some routers!"
    echo "$routers"
    exit 2
else
    echo "All routers are fine."
    echo "$routers"
    exit 0
fi
