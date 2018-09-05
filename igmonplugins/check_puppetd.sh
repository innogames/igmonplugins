#!/bin/sh
#
# InnoGames Monitoring Plugins - Last Puppet Run Check
#
# Copyright (c) 2018 InnoGames GmbH
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

diff_crit=15000

case `uname` in
	FreeBSD)
		puppet_state_file="/var/puppet/lastupdate"
		puppet_disabled_file="/var/lib/nagios3/.nopuppetd"
		;;
	Linux)
		puppet_state_file="/var/tmp/puppet_lastupdate"
		puppet_disabled_file="/var/lib/nagios3/.nopuppetd"
		;;
esac

#// Log for disable tag
#if(is_readable("/var/lib/nagios3/.nopuppetd"))
[ -r $puppet_disabled_file ] && {
    echo "OK - check skipped!"
    exit 0
}

#// Check state file
#if(!is_readable($puppet_state))
[ -r $puppet_state_file ] || {
    echo "CRITICAL - cant read statefile!"
    exit 2
}

#// Get puppet state from file
#$state = file($puppet_state);
#$state = intval($state[0]);
#$date_cur = time();
#$date_puppet = $state;
date_cur=$( date +%s )
date_puppet=$(cat $puppet_state_file)

date_diff=$(( $date_cur - $date_puppet ))

[ $date_diff -lt $diff_crit ] && {
    echo "OK - $date_diff sec."
    exit 0
} || {
    echo "WARNING - $date_diff sec."
    exit 1
}
