#!/usr/bin/env python
#
# Nagios clickhouse-server check
#
# This check tests multiple clickhouse-server's health metrics
#
# Copyright (c) 2020 InnoGames GmbH
#


class Code(object):
    OK = 0
    WARNING = 1
    CRITICAL = 2
    UNKNOWN = 3
    valid = [OK, WARNING, CRITICAL, UNKNOWN]
    names = ['OK', 'WARNING', 'CRITICAL', 'UNKNOWN']

    def __init__(self, code: int = OK):
        self.current = code

    def reset(self, code: int = OK):
        """
        Resets 'current' property to optionally given code, 0 by default
        """
        self._check_code(code)
        self.__current = code

    def _check_code(self, code: int):
        """
        Checks if code is valid
        """
        if code not in self.valid:
            raise Exception('code {} must be in {}'.format(code, self.valid))

    @property
    def name(self):
        return self.names[self.current]

    @property
    def current(self):
        return self.__current

    @current.setter
    def current(self, code):
        self._check_code(code)
        self.__current = getattr(self, 'current', 0)

        if self.__current == self.OK:
            self.__current = code
            return
        elif (self.__current == self.UNKNOWN and
                code in [self.WARNING, self.CRITICAL, self.UNKNOWN]):
            self.__current = code
            return
        elif (self.__current == self.WARNING and
              code in [self.WARNING, self.CRITICAL]):
            self.__current = code
            return
        elif self.__current == self.CRITICAL:
            return
