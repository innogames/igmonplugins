#!/usr/bin/python

# author: Juergen Thomann

import libvirt
import sys

try:
    conn = libvirt.openReadOnly(None)
except libvirt.libvirtError as e:
    print "WARNING: could not connect to libvirt: {0}".format(e)
    sys.exit(1)
domids = conn.listAllDomains()
messages = []

for dom in domids:
    if not dom.isActive():
        messages.append('{0} is defined but not running'.format(dom.name()))

if messages:
    message =', '.join(messages)
    print "WARNING: {0}".format(message)
    sys.exit(1)
else:
    print "OK: all defined domains are running"

