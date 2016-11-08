# InnoGames Monitoring Plugins - check_ssl_expiry.py
#
# This is a script that checks for ssl certificatexpiration in the next 30 days,
# for all ssl certificate files in a given directory.
# The script will exit with:
#  - 0 (OK) if no certificate in the checked directory will expire in the next
#           30 days
#
#  - 1 (Warning) if a script in the checked directory will expire in the next 30
#                days
# Copyright (c) 2016, InnoGames GmbH
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

import os
import re
import sys
import time
import datetime
import fnmatch
from OpenSSL import crypto


# If this server is ever updated to python2.7 and wheezy remove the dirty hacks and use pyopenssl fro crl handling
# http://stackoverflow.com/questions/4115523/is-there-a-simple-way-to-parse-crl-in-python

expire_cns = ''
check_time = time.time() + 2592000
CERT_DIR = sys.argv[1]
certs = os.listdir(CERT_DIR)

for certfile in certs:
  st_cert=open(os.path.join(CERT_DIR, certfile), 'r').read()
  c=crypto
  if certfile.endswith('.pem') or certfile.endswith('.crt') or certfile.endswith('.ca-bundle'):
    certobject=c.load_certificate(c.FILETYPE_PEM, st_cert)
    timestring= certobject.get_notAfter().rstrip('Z')
    expiry_date = datetime.datetime.strptime(timestring, '%Y%m%d%H%M%S')
    expiry_date_unix= date_object.strftime("%s")
    if check_time > expiry_date_unix and expiry_date > time.time():
       cn = str(cert.get_subject()).split('/')[6]
       expire_cns += cn + ' ({0}), '.format(time.strftime("%d.%m.%Y",time.localtime(int(expiry_date_unix))))

if expire_cns:
  print "WARNING: the following certs will expire soon: {0}".format(expire_cns)
  sys.exit(1)
else:
  print "OK: Everything is fine"

