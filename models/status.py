#!/usr/bin/env python
# -*- coding: utf-8 -*-


from enum import IntEnum


__author__ = 'James Iter'
__date__ = '2017/3/22'
__contact__ = 'james.iter.cn@gmail.com'
__copyright__ = '(c) 2017 by James Iter.'


class EmitKind(IntEnum):
    log = 0
    guest_event = 1
    host_event = 2
    response = 3


class GuestState(IntEnum):
    # 参考地址：
    # http://libvirt.org/docs/libvirt-appdev-guide-python/en-US/html/libvirt_application_development_guide_using_python-Guest_Domains-Information-State.html

    no_state = 0
    running = 1
    blocked = 2
    paused = 3
    shutdown = 4
    shutoff = 5
    crashed = 6
    pm_suspended = 7
    migrating = 8
    update = 9


class HostEvent(IntEnum):
    heartbeat = 0


class LogLevel(IntEnum):
    critical = 0
    error = 1
    warn = 2
    info = 3
    debug = 4


class ResponseState(IntEnum):
    success = True
    failure = False


class OperateRuleKind(IntEnum):
    cmd = 0
    write_file = 1
    append_file = 2


