#!/bin/bash

####
# Check the git origin if there are non merged/rebased commits
####

if [[ ! -d $1/.git ]]
then
    echo "Unknown: No valid git repository found in $1"
    exit 3
fi

cd $1
git fetch > /dev/null
NUM_COMMITS=`git log --oneline HEAD..origin | wc -l`
if [[ $NUM_COMMITS -eq 0 ]]
then
    echo "OK: $1 is up to date"
    exit 0
fi

echo "WARNING: $1 is $NUM_COMMITS commits behind origin"
exit 1
