#!/bin/bash
#
# An helper script to format output fro NSCA
#
# We have some Nagios checks that run long enough not to be used as an active
# one.  With this wrapper, we will get the data from them to be send to Nagios
# via NSCA.
#
# Copyright (c) 2015, InnoGames GmbH
#

if ! [ "$2" ]; then
    echo "Usage: $0 service command arguments" >&2
    exit 3
fi

hostname=$(hostname)
service=$1
output=$(${@:2})    # Run the command.
exitcode=$?

echo -e "$hostname\t$service\t$exitcode\t$output"
