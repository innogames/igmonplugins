#!/bin/sh
#/////////////////////////////////////////////////////
#// check_puppetd
#/////////////////////////////////////////////////////
#//
#// Checks puppetd confuguration freshness
#//


#/////////////////////////////////////////////////////
#// Config

diff_crit=8000

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



#/////////////////////////////////////////////////////
#// Check freshnes

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
