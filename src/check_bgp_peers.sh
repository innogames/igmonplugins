#!/bin/sh
#
# InnoGames Monitoring Plugins - BGP Peers Check
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

# Nagios return codes
#0   OK
#1   WARNING
#2   CRITICAL
#3   UNKNOWN

birdc 'show protocols' | awk '$2=="BGP" { ORS=" "; print $1":"; for (i=3; i<=NF; i++) print $i; ORS="\n"; print ""}' > /tmp/bgpstatus

while read proto; do
    router=${proto%%:*}
    message=${proto#*:}
    status=${message##* }

    if [ "$status" != "Established" ]; then
        CRIT="yes"
    fi
    routers="${routers}${router}: ${message}"$'\n'
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
