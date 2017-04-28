#!/bin/bash
#
# InnoGames Monitoring Plugins - check_git_origin.sh
#
# Copyright (c) 2017, InnoGames GmbH
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
#

####
# Check the git origin if there are non merged/rebased commits
####

if [[ ! -d $1/.git ]]
then
    echo "UNKNOWN: No valid git repository found in $1"
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
