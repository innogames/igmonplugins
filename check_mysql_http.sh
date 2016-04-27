#!/bin/sh
#
# This script checks if a mysql server is healthy running on 127.0.0.1. It will
# return:
# "HTTP/1.x 200 OK\r" (if mysql is running smoothly)
# - OR -
# "HTTP/1.x 500 Internal Server Error\r" (else)
#
# The purpose of this script is make haproxy capable of monitoring mysql properly
#

MYSQL_HOST="127.0.0.1"
MYSQL_PORT="3306"
MYSQL_OPTS="-N -q -A --connect-timeout=10"
MYSQL_BIN="/usr/bin/mysql"

CHECK_QUERY="show global status where variable_name='wsrep_local_state'"
CHECK_QUERY2="show global variables where variable_name='wsrep_sst_method'"

return_ok()
{
    printf "HTTP/1.1 200 OK\r\n"
    printf "Content-Type: text/html\r\n"
    printf "Content-Length: 43\r\n"
    printf "\r\n"
    printf "<html><body>MySQL is running.</body></html>\r\n"
    printf "\r\n"
    sleep 0.1
    exit 0
}

return_fail()
{
    printf "HTTP/1.1 503 Service Unavailable\r\n"
    printf "Content-Type: text/html\r\n"
    printf "Content-Length: 42\r\n"
    printf "\r\n"
    printf "<html><body>MySQL is *down*.</body></html>\r\n"
    printf "\r\n"
    sleep 0.1
    exit 1
}

status=$($MYSQL_BIN $MYSQL_OPTS --host=$MYSQL_HOST --port=$MYSQL_PORT --user=$MYSQL_USERNAME --password=$MYSQL_PASSWORD -e "$CHECK_QUERY;" 2>/dev/null | awk '{print $2;}')
if [ $? -ne 0 ]; then
        return_fail
fi
if [ $status -eq 2 ] || [ $status -eq 4 ] ; then
   if [ $status -eq 2 ]; then
     method=$($MYSQL_BIN $MYSQL_OPTS --host=$MYSQL_HOST --port=$MYSQL_PORT --user=$MYSQL_USERNAME --password=$MYSQL_PASSWORD -e "$CHECK_QUERY2;" 2>/dev/null | awk '{print $2;}')
     if [ $? -ne 0 ]; then
        return_fail
     fi
     if [ -z "$method" ] || [ "$method" = "rsync" ] || [ "$method" = "mysqldump" ]; then
         return_fail
     fi
   fi
   return_ok
fi

return_fail
