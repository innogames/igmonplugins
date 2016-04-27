#!/bin/bash
#
# InnoGames Monitoring Plugins - check_swapping.sh
#
# Copyright (c) 2016, InnoGames GmbH
#

if [ `ls -1 /var/spool/exim4/msglog/ | wc -l` -gt 10 ]
then
	echo "Warning: exim might not be able to send mails - please check your config"
	exit 1
fi

echo "OK - exim seems to work properly"
exit 0
