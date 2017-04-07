#!/usr/bin/env python
# -*- coding: utf-8 -*-


import commands
import jimit as ji
import json

from models import LogLevel


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

    def emit(self, _type=None, message=''):
        msg = json.dumps({'type': _type, 'timestamp': ji.Common.ts(), 'host': self.hostname, 'message': message},
                         ensure_ascii=False)
        return self.r.rpush(self.host_event_report_queue, msg)

    def info(self, msg):
        return self.emit(_type=LogLevel.info.value, message=msg)

    def warn(self, msg):
        return self.emit(_type=LogLevel.warn.value, message=msg)

    def error(self, msg):
        return self.emit(_type=LogLevel.error.value, message=msg)

    def critical(self, msg):
        return self.emit(_type=LogLevel.critical.value, message=msg)

