#!/bin/bash
#
# Script to Check Directory Sizes
#
# Copyright (c) 2015, InnoGames GmbH
#

if ! [ "$1" ]; then
    echo "Usage: $0 path [warning_mib] [critical_mib]" >&2
fi

msize=$(du -sm $1 | cut -f 1)
hsize=$(du -sh $1 | cut -f 1)

if [ "$3" ] && [[ $msize -gt $3 ]]; then
    echo "CRITICAL $1 is $hsize exceeds $3M"
    exit 2
fi

if [ "$2" ] && [[ $msize -gt $2 ]]; then
    echo "WARNING $1 is $hsize exceeds $2M"
    exit 1
fi

echo "OK $1 is $hsize"
exit 0
