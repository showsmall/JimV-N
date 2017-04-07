#!/usr/bin/env python
# -*- coding: utf-8 -*-


from enum import Enum, IntEnum


__author__ = 'James Iter'
__date__ = '2017/3/22'
__contact__ = 'james.iter.cn@gmail.com'
__copyright__ = '(c) 2017 by James Iter.'


class GuestStatus(IntEnum):
    shutdown = 0
    booting = 1
    running = 2
    rebooting = 3
    suspend = 4
    resuming = 5


class LogLevel(IntEnum):
    critical = 0
    error = 1
    warn = 2
    info = 3
    debug = 4

