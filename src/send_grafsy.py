"""InnoGames Monitoring Plugins - Helper for sending metrics to grafana and
passive checks to nagios

Copyright (c) 2019 InnoGames GmbH
"""
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

from time import time
from os import rename, chmod
import tempfile

def send_grafsy(data):
    "For sending the results to grafana"

    msg = ''

    for k1, v1 in data.items():
        template = k1.replace('.', '_') + '.'
        msg += fetch(template, v1)


    with tempfile.NamedTemporaryFile('w', delete=False) as tmpfile:
        grafsy_file = "/tmp/grafsy/" + tmpfile.name.split('tmp/')[1]
        tmpfile.write(msg)
        tmpfile.flush()
        tmpname = tmpfile.name
        chmod(tmpname, 0o644)
        rename(tmpname, grafsy_file)

    return None


def fetch(template, v1):
    msg2 = ''
    if isinstance(v1, dict):
        for k2, v2 in v1.items():
            prefix = template
            prefix += k2.replace('.', '_') + '.'
            ret = fetch(prefix, v2)
            msg2 += ret
    else:
        msg2 = template.rstrip('.') + ' ' + str(v1) + ' ' + (str(int(time()))) + '\n'

    return msg2
