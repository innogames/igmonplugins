#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - VM Data Export Script

Copyright (c) 2021 InnoGames GmbH
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

import sys

from argparse import ArgumentParser
from libvirt import openReadOnly
from redis import Redis
from redis.exceptions import ConnectionError


def parse_args():
    parser = ArgumentParser()

    parser.add_argument(
        '-H', dest='redis_servers', action='append', required=True,
        help='Redis servers to report the results to',
    )

    parser.add_argument(
        '-n', dest='hostname', required=True,
        help='Hypervisor hostname to suffix the keys with',
    )

    parser.add_argument(
        '-p', dest='redis_password',
        help='Password for Redis server authentication',
    )

    parser.add_argument(
        '--ttl', default=900,
        help='TTL in seconds for keys inserted into Redis',
    )

    return parser.parse_args()


def main():
    args = parse_args()

    domains = get_domains_info()

    error = False
    for server in args.redis_servers:
        try:
            result = send_to_redis(
                server, args.redis_password,
                args.hostname, domains, args.ttl,
            )
            if result:
                print(f'Results successfully sent to {server}')
            else:
                print(f'Errors while sending results to {server}')
                error = True
        except ConnectionError as e:
            print(str(e))
            error = True

    if error:
        return 1

    return 0


def get_domains_info():
    conn = openReadOnly(None)
    libvirt_domains = conn.listAllDomains()

    domains = {}
    for d in libvirt_domains:
        state, reason = d.state()
        domain_name = d.name()
        domains[domain_name] = {
            'state': state, 'reason': reason,
        }

    return domains


def send_to_redis(redis_server, redis_password, hypervisor, results, ttl):
    r = Redis(
        host=redis_server, port=6379,
        db=0, password=redis_password,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    pipe = r.pipeline()

    for vm_name, mapping in results.items():
        redis_key = f'igvm_consistency:{hypervisor}:{vm_name}'

        # TODO: hmset was deprecated in version 3.5.0. Buster is running with
        # 3.2.1 but Bullseye is running with 3.5.3, so we will need to
        # update this soon.
        pipe.hmset(redis_key, mapping=mapping)
        # If the Hypervisor stops sending data, the entries in Redis will
        # expire after this amount of time.
        pipe.expire(redis_key, ttl)

    # pipe.execute() returns an array with booleans for each command that
    # was queued in the pipeline.
    # We return a convoluted result that says if all succeeded or not.
    return all(pipe.execute())


if __name__ == '__main__':
    sys.exit(main())
