#!/usr/bin/env python
# -*- coding: utf-8 -*-


import os
import sys
import time
import libvirt
import json
from gluster import gfapi

from jimvn_exception import ConnFailed

from initialize import config, logger, r, emit
from guest import Guest


__author__ = 'James Iter'
__date__ = '2017/3/1'
__contact__ = 'james.iter.cn@gmail.com'
__copyright__ = '(c) 2017 by James Iter.'


class Host(object):
    def __init__(self):
        self.conn = None
        self.dirty_path = None
        self.glusterfs_volume = None
        self.gf = None

    def init_conn(self):
        self.conn = libvirt.open()

        if self.conn is None:
            raise ConnFailed(u'打开连接失败 --> ' + sys.stderr)

    def clear_scene(self):

        if self.dirty_path is not None:

            if self.gf is None:
                self.gf = gfapi.Volume('127.0.0.1', self.glusterfs_volume)
                self.gf.mount()

            if self.gf.exists(self.dirty_path):
                self.gf.rmtree(self.dirty_path)

            else:
                log = u'清理现场失败: 不存在的路径 --> ' + self.dirty_path
                logger.warn(msg=log)
                emit.warn(msg=log)

            self.dirty_path = None

    def define_guest_by_xml(self, xml):
        try:
            if self.conn.defineXML(xml=xml):
                log = u'域定义成功.'
                logger.info(msg=log)
                emit.info(msg=log)
            else:
                log = u'域定义时未预期返回.'
                logger.info(msg=log)
                emit.info(msg=log)
                return False

        except libvirt.libvirtError as e:
            logger.error(e.message)
            emit.error(e.message)
            return False

        return True

    def start_guest(self, uuid):
        try:
            domain = self.conn.lookupByUUID(uuid=uuid)
            # libvirtd 服务启动时，虚拟机不随之启动
            domain.setAutostart(0)
            domain.create()
            log = u'域成功启动.'
            logger.info(msg=log)
            emit.info(msg=log)

        except libvirt.libvirtError as e:
            logger.error(e.message)
            emit.error(e.message)
            return False

        return True

    def create_guest_engine(self):
        while True:
            try:
                # 清理上个周期弄脏的现场
                self.clear_scene()
                # 取系统最近 5 分钟的平均负载值
                load_avg = os.getloadavg()[1]
                # sleep 加 1，避免 load_avg 为 0 时，循环过度
                time.sleep(load_avg * 10 + 1)

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

                guest = Guest(uuid=msg['uuid'], name=msg['name'], glusterfs_volume=msg['glusterfs_volume'],
                              template_path=msg['template_path'], disks=msg['guest_disks'],
                              writes=msg['writes'], xml=msg['xml'])
                guest.generate_guest_dir()

                self.glusterfs_volume = guest.glusterfs_volume
                # 虚拟机定义成功后，重置该变量为 None
                self.dirty_path = guest.guest_dir

                if not guest.generate_system_image():
                    continue

                # 由该线程最顶层的异常捕获机制，处理其抛出的异常
                guest.init_config()

                if not guest.generate_disk_image():
                    continue

                if not self.define_guest_by_xml(xml=guest.xml):
                    continue

                # 虚拟机定义成功后，重置该变量为 None，避免下个周期被清理现场
                self.dirty_path = None

                if not self.start_guest(uuid=guest.uuid):
                    # 不清理现场，如需清理，让用户手动通过面板删除
                    continue

            except Exception as e:
                logger.error(e.message)
                emit.error(e.message)

