#!/usr/bin/env python
#
# InnoGames Monitoring Plugins - check_logrotate_missing.py
#
# Search for logs which are not logrotated
#
# This script checks that only the configured logfiles for logrotation
# are lying in the regarding log directories.
# Following logrotate configuration filetypes are supported:
# * logrotate
# * logback
# * log4j (xml only)
# It raises a warning if there are unconfigured logfiles found.
# It raises a unknown if the passed configuration file does not exist.
#
# Copyright (c) 2018, InnoGames GmbH
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

import glob
import os
import mimetypes
import xml.etree.ElementTree as ET
from argparse import ArgumentParser, RawTextHelpFormatter


class RotationConfigDoesNotExist(Exception):
    pass


def main():
    """Main entrypoint for script"""

    args = parse_args()

    try:
        logrotate_missing = check_logrotation_config(args.config, args.exclude)
    except RotationConfigDoesNotExist as e:
        code = 3
        print(e)
        exit(code)

    code = 0

    if logrotate_missing:
        code = 1
        for logfile in logrotate_missing:
            print(logfile)
    else:
        print('OK')

    exit(code)


def parse_args():
    """Get argument parser -> ArgumentParser

    We need the logrotation configuration files
    and potentially logfiles to exclude
    """

    parser = ArgumentParser(formatter_class=RawTextHelpFormatter)

    parser.add_argument(
        '--config',
        help='''
        logrotation config to parse,
        multiple possible
        EXAMPLE: --config /etc/logrotate.d/foe-logs /etc/logrotate.d/foe-logs2
        ''',
        action='append',
        default=[],
    )

    parser.add_argument(
        '--exclude',
        help='''
        logfiles to exclude from being checked,
        multiple possible
        EXAMPLE: --exclude /var/log/lastlog /var/log/faillog
        ''',
        action='append',
        default=[],
    )

    return parser.parse_args()


def check_logrotation_config(config, exclude):
    """Check the logrotation configuration

    Check configured logrotation directories if there are unconfigured logs
    lying around.

    :param: config: logrotation config file like:
                    /etc/logrotate.d/foe-logs
                    /www/gk/configs/gk-master-admin/logback.xml
                    /www/gk/gk-master/configs/log4j2.xml

    :param: exclude: logfile to exclude from being checked,
                     e.g. /var/log/lastlog

    :return: set
    """

    configured_logs = set()
    unconfigured_logs = set()
    log4j_appenders = [
        './Appenders/File',
        './Appenders/RollingFile',
        './Appenders/ReopenFile',
    ]

    for conf in config:
        conf_type = mimetypes.guess_type(conf)[0]

        if conf_type and 'xml' in conf_type:
            try:
                tree = ET.parse(conf)
            except IOError:
                raise RotationConfigDoesNotExist('{} does not exist'.format(
                    conf))
            # logback
            for lblog in tree.getroot().findall('appender'):
                    lblog_file = lblog.find('file')
                    if lblog_file is not None:
                        configured_logs.add(lblog_file.text)
            # log4j
            for appender in log4j_appenders:
                for jlog in tree.getroot().findall(appender):
                    jlog_file = jlog.get('fileName')
                    if jlog_file is not None:
                        configured_logs.add(jlog_file)
        # logrotate
        else:
            try:
                with open(conf) as in_file:
                    for line in in_file:
                        if line.startswith('/'):
                            configured_logs.add(line.rstrip('{\n\t '))
            except IOError:
                raise RotationConfigDoesNotExist('{} does not exist'.format(
                     conf))

        log_dirs = {os.path.dirname(c) for c in configured_logs}

        for log_dir in log_dirs:
            logfiles = glob.glob(log_dir + '/*log')
            for logfile in logfiles:
                if not any(logfile == l for l in configured_logs):
                    if logfile not in exclude:
                        unconfigured_logs.add(logfile)

        unconfigured_logs -= configured_logs

    return unconfigured_logs


if __name__ == '__main__':
    main()
