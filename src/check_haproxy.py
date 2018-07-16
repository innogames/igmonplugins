#!/usr/bin/env python
#
# InnoGames Monitoring Plugins - check_haproxy.py
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

import socket
import sys
import argparse


parser = argparse.ArgumentParser(description='Check haproxy lbpool up and running')
parser.add_argument('-i', '--ignore_warnings', dest='ignore_warnings', action='store_true', default=False, help="Ignore if some hosts under LBpool are down")
args=parser.parse_args()

haproxy_socket_path = '/tmp/haproxy'
exit_code = 0
try:
  haproxy_socket = socket.socket( socket.AF_UNIX, socket.SOCK_STREAM )
  haproxy_socket.connect(haproxy_socket_path)

  haproxy_socket.send('show stat\n')

  f = haproxy_socket.makefile()
  lbpools = {}
  lbstatuses = {}
  status = ''

  for line in f.readlines():
    lbstatus = {}
    if line.startswith('#') or line == "\n":
      continue
    split = line.split(',')

    if split[1] == 'BACKEND':
      # Backend means we are at the end of haproxy output for this lbpool
      name = split[0]
      lbstatus = ''
      for key, value in lbstatuses.iteritems():
        lbstatus += (key + ' - ' + value + '; ')
      status = split[17]
      message = split[0] + ' - ' + split[17] + ': ' + lbstatus
      print message
      if status != 'UP':
        exit_code = 2

    elif len(split[1].split(':')) == 2:
      # If it is an ip - append it to dict of lbstatuses
      lbstatuses[split[1]] = split[17]
      # if any server under lbpool is down - print warning
      if split[17] != 'UP':
          if not args.ignore_warnings:
            exit_code = 1


except:
  print 'Error connecting to haproxy socket %s' % haproxy_socket_path
  raise
  exit_code = 2

sys.exit(exit_code)
