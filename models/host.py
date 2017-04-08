#!/usr/bin/env python
# -*- coding: utf-8 -*-


import os
import sys
import time
import libvirt
import json
import jimit as ji

from jimvn_exception import ConnFailed

from initialize import config, logger, r, emit
from guest import Guest
from utils import Utils


__author__ = 'James Iter'
__date__ = '2017/3/1'
__contact__ = 'james.iter.cn@gmail.com'
__copyright__ = '(c) 2017 by James Iter.'


class Host(object):
    def __init__(self):
        self.conn = None
        self.dirty_scene = False
        self.guest = None

    def init_conn(self):
        self.conn = libvirt.open()

        if self.conn is None:
            raise ConnFailed(u'打开连接失败 --> ' + sys.stderr)

    def clear_scene(self):

        if self.dirty_scene:

            if self.guest.gf.exists(self.guest.guest_dir):
                self.guest.gf.rmtree(self.guest.guest_dir)

            else:
                log = u'清理现场失败: 不存在的路径 --> ' + self.guest.guest_dir
                logger.warn(msg=log)
                emit.warn(msg=log)

            self.dirty_scene = False

    def create_guest_engine(self):
        while True:
            if Utils.exit_flag:
                Utils.thread_counter -= 1
                print 'Thread say bye-bye'
                return

            try:
                # 清理上个周期弄脏的现场
                self.clear_scene()
                # 取系统最近 5 分钟的平均负载值
                load_avg = os.getloadavg()[1]
                # sleep 加 1，避免 load_avg 为 0 时，循环过度
                time.sleep(load_avg * 10 + 1)
                print ji.JITime.gmt(ts=time.time())

                # 大于 0.6 的系统将不再被分配创建虚拟机
                if load_avg > 0.6:
                    continue

                msg = r.rpop(config.get('vm_create_queue', 'Q:VMCreate'))
                if msg is None:
                    continue

                try:
                    msg = json.loads(msg)
                except ValueError as e:
                    logger.error(e.message)
                    emit.emit(e.message)
                    continue

                self.guest = Guest(uuid=msg['uuid'], name=msg['name'], glusterfs_volume=msg['glusterfs_volume'],
                                   template_path=msg['template_path'], disks=msg['guest_disks'],
                                   writes=msg['writes'], xml=msg['xml'])
                if Guest.gf is None:
                    Guest.glusterfs_volume = msg['glusterfs_volume']
                    Guest.init_gfapi()

                self.guest.generate_guest_dir()

                # 虚拟机基础环境路径创建后，至虚拟机定义成功前，认为该环境是脏的
                self.dirty_scene = True

                if not self.guest.generate_system_image():
                    continue

                # 由该线程最顶层的异常捕获机制，处理其抛出的异常
                self.guest.init_config()

                if not self.guest.generate_disk_image():
                    continue

                if not self.guest.define_by_xml(conn=self.conn):
                    continue

                # 虚拟机定义成功后，该环境由脏变为干净，重置该变量为 False，避免下个周期被清理现场
                self.dirty_scene = False

                if not self.guest.start_by_uuid(conn=self.conn):
                    # 不清理现场，如需清理，让用户手动通过面板删除
                    continue

            except Exception as e:
                logger.error(e.message)
                emit.error(e.message)

