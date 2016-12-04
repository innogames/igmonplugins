#!/usr/bin/env python
"""
InnoGames Monitoring Plugins - nrpe.py

This is Python implementation of the NRPE protocol.

Copyright (c) 2012, Henning Pridoehl
Copyright (c) 2016, InnoGames GmbH
"""
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the 'Software'), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED 'AS IS', WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import binascii
import struct
import socket
import sys
import ssl

# NRPE uses the following struct for communication:
# h: NRPE protocol version (currently 2)
# h: NRPE packet type (1=query, 2=response)
# i: CRC32 checksum of the struct with checksum set to 0
# h: Return code (0=OK, 1=WARN, 2=CRIT, 3=UNKNOWN)
# 1024s: The command or the response of the plugin
# c: unknown, set to N on queries, varying on response
# c: unknown, set to D on queries, varying on response
NRPE_STRUCT = '!hhih1024scc'
PROTOCOL_VERSION = 2
NRPE_QUERY = 1
NRPE_RESPONSE = 2


class InvalidResponse(Exception):
    pass


def build_query(command):
    crc = _checksum(PROTOCOL_VERSION, NRPE_QUERY, 0, command, 'N', 'D')
    return struct.pack(NRPE_STRUCT, PROTOCOL_VERSION, NRPE_QUERY, crc, 0,
                       command, 'N', 'D')


def parse_response(response):
    try:
        prot, type, crc, returncode, resp, r1, r2 = struct.unpack(NRPE_STRUCT,
                                                                  response)
    except struct.error:
        raise InvalidResponse('NRPE packet was malformed')

    if prot != PROTOCOL_VERSION:
        raise InvalidResponse(('Protocol version does not match: expected {0} '
                               'but got {1}'.format(PROTOCOL_VERSION, prot)))

    if type != NRPE_RESPONSE:
        raise InvalidResponse('Invalid packet type {0}'.format(type))

    expected_crc = _checksum(prot, type, returncode, resp, r1, r2)
    if crc != expected_crc:
        raise InvalidResponse(('Invalid CRC32 checksum. Expected {0} but got '
                               '{1}').format(expected_crc, crc))

    return returncode, resp.rstrip('\x00')


def _checksum(prot, type, returncode, command, r1, r2):
    query_crc = struct.pack(NRPE_STRUCT, prot, type, 0, returncode, command,
                            r1, r2)
    return binascii.crc32(query_crc)


def send_query(command, host, port=5666, use_ssl=True, timeout=None):
    use_m2crypto = use_ssl and sys.version_info[1] <= 6
    if use_ssl:
        if use_m2crypto:
            from M2Crypto import SSL
            ctx = SSL.Context('tlsv1')
            ctx.set_cipher_list('ADH')
            ctx.set_verify(SSL.verify_none, depth=0)
            sock = SSL.Connection(ctx)
            sock.set_post_connection_check_callback(None)
        else:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock = ssl.wrap_socket(sock, ssl_version=ssl.PROTOCOL_TLSv1,
                                   ciphers='ADH')
    else:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    if timeout:
        if use_m2crypto:
            orig_timeout = socket.getdefaulttimeout()
            socket.setdefaulttimeout(timeout)
        else:
            sock.settimeout(timeout)

    ssl_exception_class = SSL.SSLError if use_m2crypto else ssl.SSLError
    try:
        sock.connect((host, port))
        sock.sendall(build_query(command))
        return parse_response(sock.recv(1036))
    except ssl_exception_class as e:
        if use_m2crypto:
            raise ssl.SSLError(*e.args)
        else:
            raise
    finally:
        if timeout and use_m2crypto:
            socket.setdefaulttimeout(orig_timeout)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print >> sys.stderr, 'Usage: {0} <command> <host>'.format(sys.argv[0])
        sys.exit(1)

    print send_query(sys.argv[1], sys.argv[2])
