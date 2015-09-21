#!/bin/bash
#
# Script to Check Old Files under a Directory
#
# Copyright (c) 2015, InnoGames GmbH
#

if ! [ "$1" ]; then
    echo "Usage: $0 path [warning_minute] [critical_minute]" >&2
fi

if [ "$3" ]; then
    found=$(find $1 -mmin +$3 -type f -not -name '.*' | wc -l)
    if [[ $found -gt 0 ]]; then
        echo "CRITICAL $found file found older than $3 minute"
        exit 2
    fi
fi

if [ "$2" ]; then
    found=$(find $1 -mmin +$2 -type f -not -name '.*' | wc -l)
    if [[ $found -gt 0 ]]; then
        echo "WARNING $found file found older than $2 minute"
        exit 2
    fi
fi

echo "OK no old files found"
exit 0
