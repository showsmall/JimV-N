#!/usr/bin/env python
# -*- coding: utf-8 -*-


import commands
import jimit as ji
import json

from models import LogLevel, EmitKind, GuestState, ResponseState


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
        self.upstream_queue = None
        self.hostname = ji.Common.get_hostname()
        self.r = None

    def emit(self, _kind=None, _type=None, message=None):
        from initialize import logger

        if all([key is None for key in [_kind, _type, message]]):
            logger.warning(u'参数 _kind, _type, message 均不能为None.')
            return False

        msg = json.dumps({'kind': _kind, 'type': _type, 'timestamp': ji.Common.ts(), 'host': self.hostname,
                          'message': message}, ensure_ascii=False)
        return self.r.rpush(self.upstream_queue, msg)


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

    def no_state(self, uuid):
        return self.emit2(_type=GuestState.no_state.value, uuid=uuid)

    def running(self, uuid):
        return self.emit2(_type=GuestState.running.value, uuid=uuid)

    def blocked(self, uuid):
        return self.emit2(_type=GuestState.blocked.value, uuid=uuid)

    def paused(self, uuid):
        return self.emit2(_type=GuestState.paused.value, uuid=uuid)

    def shutdown(self, uuid):
        return self.emit2(_type=GuestState.shutdown.value, uuid=uuid)

    def shutoff(self, uuid):
        return self.emit2(_type=GuestState.shutoff.value, uuid=uuid)

    def crashed(self, uuid):
        return self.emit2(_type=GuestState.crashed.value, uuid=uuid)

    def pm_suspended(self, uuid):
        return self.emit2(_type=GuestState.pm_suspended.value, uuid=uuid)


class ResponseEmit(Emit):
    def __init__(self):
        super(ResponseEmit, self).__init__()

    def emit2(self, _type=None, action=None, uuid=None):
        return self.emit(_kind=EmitKind.response.value, _type=_type, message={'action': action, 'uuid': uuid})

    def success(self, action, uuid):
        return self.emit2(_type=ResponseState.success.value, action=action, uuid=uuid)

    def failure(self, action, uuid):
        return self.emit2(_type=ResponseState.failure.value, action=action, uuid=uuid)

"""
    def create_vm_success(self, uuid):
        return self.emit2(_type=ResponseState.create_vm_success.value, uuid=uuid)

    def create_vm_failure(self, uuid):
        return self.emit2(_type=ResponseState.create_vm_failure.value, uuid=uuid)

    def create_disk_success(self, uuid):
        return self.emit2(_type=ResponseState.create_disk_success.value, uuid=uuid)

    def create_disk_failure(self, uuid):
        return self.emit2(_type=ResponseState.create_disk_failure.value, uuid=uuid)

    def resize_disk_success(self, uuid):
        return self.emit2(_type=ResponseState.resize_disk_success.value, uuid=uuid)

    def resize_disk_failure(self, uuid):
        return self.emit2(_type=ResponseState.resize_disk_failure.value, uuid=uuid)

    def delete_disk_success(self, uuid):
        return self.emit2(_type=ResponseState.delete_disk_success.value, uuid=uuid)

    def delete_disk_failure(self, uuid):
        return self.emit2(_type=ResponseState.delete_disk_failure.value, uuid=uuid)
"""

