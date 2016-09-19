#!/bin/bash
#
# InnoGames Monitoring Plugins - check_exim_delivery.sh
#
# Copyright (c) 2016, InnoGames GmbH
#

set -euo pipefail

exim_dir="/var/spool/exim4/msglog/"
max_message=10

if ! [ -d $exim_dir ]; then
    echo "Can not open $exim_dir"
    exit 1
fi

messages=$(ls -1 $exim_dir | wc -l)

if [ $messages -gt $max_message ]; then
    echo "To many messages in queue ($messages > $max_message). See $exim_dir"
    exit 1
else
    echo "OK - exim seems to work properly"
fi
