#!/usr/bin/env python
# -*- coding: utf-8 -*-


import commands
import jimit as ji
import json

from models import LogLevel, EmitKind, GuestEvent


__author__ = 'James Iter'
__date__ = '2017/3/13'
__contact__ = 'james.iter.cn@gmail.com'
__copyright__ = '(c) 2017 by James Iter.'


class Utils(object):

    exit_flag = False
    thread_counter = 0

    @staticmethod
    def shell_cmd(cmd):
        try:
            exit_status, output = commands.getstatusoutput(cmd)

            return exit_status, str(output)

        except Exception as e:
            return -1, e.message

    @classmethod
    def signal_handle(cls, signum=0, frame=None):
        cls.exit_flag = True


class Emit(object):

    def __init__(self):
        # 初始化时，host_event_report_queue 必须由具体实例来指定
        self.host_event_report_queue = None
        self.hostname = ji.Common.get_hostname()
        self.r = None

    def emit(self, _kind=None, _type=None, message=None):
        from initialize import logger

        if all([key is None for key in [_kind, _type, message]]):
            logger.warning(u'参数 _kind, _type, message 均不能为None.')
            return False

        msg = json.dumps({'kind': _kind, 'type': _type, 'timestamp': ji.Common.ts(), 'host': self.hostname,
                          'message': message}, ensure_ascii=False)
        return self.r.rpush(self.host_event_report_queue, msg)


class LogEmit(Emit):
    def __init__(self):
        super(LogEmit, self).__init__()

    def emit2(self, _type=None, message=None):
        return self.emit(_kind=EmitKind.log.value, _type=_type, message=message)

    def debug(self, msg):
        return self.emit2(_type=LogLevel.debug.value, message=msg)

    def info(self, msg):
        return self.emit2(_type=LogLevel.info.value, message=msg)

    def warn(self, msg):
        return self.emit2(_type=LogLevel.warn.value, message=msg)

    def error(self, msg):
        return self.emit2(_type=LogLevel.error.value, message=msg)

    def critical(self, msg):
        return self.emit2(_type=LogLevel.critical.value, message=msg)


class EventEmit(Emit):
    def __init__(self):
        super(EventEmit, self).__init__()

    def emit2(self, _type=None, uuid=None):
        return self.emit(_kind=EmitKind.event.value, _type=_type, message={'uuid': uuid})

    def shutdown(self, uuid):
        return self.emit2(_type=GuestEvent.shutdown.value, uuid=uuid)

    def booting(self, uuid):
        return self.emit2(_type=GuestEvent.booting.value, uuid=uuid)

    def running(self, uuid):
        return self.emit2(_type=GuestEvent.running.value, uuid=uuid)

    def rebooting(self, uuid):
        return self.emit2(_type=GuestEvent.rebooting.value, uuid=uuid)

    def suspend(self, uuid):
        return self.emit2(_type=GuestEvent.suspend.value, uuid=uuid)

    def resuming(self, uuid):
        return self.emit2(_type=GuestEvent.resuming.value, uuid=uuid)

