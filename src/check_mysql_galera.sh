#!/bin/sh
#
# InnoGames Monitoring Plugins - MySQL Galera Cluster Check
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

help_message="\n
This tool connects to mysql with user -u and password -p\n
gets global status of wsrep cluster and checks, if cluster in a valid state\n
USAGE: \n\t$0 -u username -p password\n
AUTHOR: \n\thttps://github.com/leoleovich"

while getopts ":u:p:" OPTION; do
	case "$OPTION" in
		u)		user="$OPTARG" ;;
		p)		pass="$OPTARG" ;;
		*)		echo -e $help_message && exit 1 ;;
	esac
done

if [ -z $user ]; then
	mysqlAuthSection=''
elif [ -z $pass ]; then
	mysqlAuthSection="-u ${user}"
else
	mysqlAuthSection="-u ${user} -p${pass}"
fi

wsrep_local_state=$(mysql $mysqlAuthSection -Bse "SHOW GLOBAL STATUS LIKE 'wsrep_local_state'" 2>/dev/null | awk '{print $2}')
wsrep_cluster_status=$(mysql $mysqlAuthSection -Bse "SHOW GLOBAL STATUS LIKE 'wsrep_cluster_status'" 2>/dev/null | awk '{print $2}')
wsrep_incoming_addresses=$(mysql $mysqlAuthSection -Bse "SHOW GLOBAL STATUS LIKE 'wsrep_incoming_addresses'" 2>/dev/null | awk '{print $2}')
wsrep_local_state_comment=$(mysql $mysqlAuthSection -Bse "SHOW GLOBAL STATUS LIKE 'wsrep_local_state_comment'" 2>/dev/null | awk '{print $2}')

if [ "$wsrep_local_state" = "4" ] && [ "$wsrep_cluster_status" = "Primary" ]; then
	echo "Node is a part of cluster $wsrep_incoming_addresses"
else
	echo "Something is wrong with this node. Status is $wsrep_local_state_comment"
	exit 2
fi
