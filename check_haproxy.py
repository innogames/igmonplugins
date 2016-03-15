#!/usr/bin/env python

import socket, sys

haproxy_socket_path = '/tmp/haproxy'
exit_code = 0
try:
  haproxy_socket = socket.socket( socket.AF_UNIX, socket.SOCK_STREAM )
  haproxy_socket.connect(haproxy_socket_path)

  haproxy_socket.send('show stat\n')

  f = haproxy_socket.makefile()
  for line in f.readlines():
    if 'BACKEND' in line:
      split = line.split(',')
      status = split[17]
      print split[0] + ' ' + status
      if status != 'UP':
        exit_code = 2
except:
  print 'Error connecting to haproxy socket %s' % haproxy_socket_path
  exit_code = 2

sys.exit(exit_code)
