#!/usr/bin/env python
# -*- coding: utf-8 -*-


import os

import guestfs
import libvirt
from gluster import gfapi

from initialize import logger, log_emit, guest_event_emit


__author__ = 'James Iter'
__date__ = '2017/3/1'
__contact__ = 'james.iter.cn@gmail.com'
__copyright__ = '(c) 2017 by James Iter.'


class Guest(object):
    gf = None
    glusterfs_volume = 'gv0'

    def __init__(self, **kwargs):
        self.uuid = kwargs.get('uuid', None)
        self.name = kwargs.get('name', None)
        self.password = kwargs.get('password', None)
        # 模板镜像路径
        self.template_path = kwargs.get('template_path', None)
        # 不提供链接克隆(完整克隆，后期可以在模板目录，直接删除模板文件。从理论上讲，基于完整克隆的 Guest 读写速度、快照都应该快于链接克隆。)
        # self.clone = True
        # Guest 系统盘及数据磁盘
        self.disk = kwargs.get('disk', None)
        self.writes = kwargs.get('writes', None)
        self.xml = kwargs.get('xml', None)
        # Guest 系统镜像路径，不包含 glusterfs 卷标
        self.system_image_path = None
        self.g = guestfs.GuestFS(python_return_dict=True)

    @classmethod
    def init_gfapi(cls):
        cls.gf = gfapi.Volume('127.0.0.1', cls.glusterfs_volume)
        cls.gf.mount()

    def generate_system_image(self):
        if not self.gf.isfile(self.template_path):
            log = u' '.join([u'域', self.name, u', UUID', self.uuid, u'所依赖的模板', self.template_path, u'不存在.'])
            logger.error(msg=log)
            log_emit.error(msg=log)
            return False

        if not self.gf.isdir(os.path.dirname(self.system_image_path)):
            self.gf.makedirs(os.path.dirname(self.system_image_path), 0755)

        self.gf.copy(self.template_path, self.system_image_path)

        return True

    def init_config(self):
        self.g.add_drive(filename=self.glusterfs_volume + '/' + self.system_image_path, format=self.disk['format'],
                         protocol='gluster', server=['127.0.0.1'])
        self.g.launch()
        self.g.mount(self.g.inspect_os()[0], '/')

        for item in self.writes:
            self.g.write(item['path'], item['content'])

        self.g.sh('echo "{user}:{password}" | chpasswd'.format(user='root', password=self.password))

        self.g.shutdown()
        self.g.close()

    def define_by_xml(self, conn=None):
        try:
            if conn.defineXML(xml=self.xml):
                log = u' '.join([u'域', self.name, u', UUID', self.uuid, u'定义成功.'])
                logger.info(msg=log)
                log_emit.info(msg=log)
            else:
                log = u' '.join([u'域', self.name, u', UUID', self.uuid, u'定义时未预期返回.'])
                logger.info(msg=log)
                log_emit.info(msg=log)
                return False

        except libvirt.libvirtError as e:
            logger.error(e.message)
            log_emit.error(e.message)
            return False

        return True

    def start_by_uuid(self, conn=None):
        try:
            domain = conn.lookupByUUIDString(uuidstr=self.uuid)
            domain.create()
            log = u' '.join([u'域', self.name, u', UUID', self.uuid, u'启动成功.'])
            logger.info(msg=log)
            log_emit.info(msg=log)

        except libvirt.libvirtError as e:
            logger.error(e.message)
            log_emit.error(e.message)
            return False

        return True

    @staticmethod
    def guest_state_report(guest):

        try:
            _uuid = guest.UUIDString()
            state, maxmem, mem, ncpu, cputime = guest.info()
            # state 参考链接：
            # http://libvirt.org/docs/libvirt-appdev-guide-python/en-US/html/libvirt_application_development_guide_using_python-Guest_Domains-Information-State.html
            # http://stackoverflow.com/questions/4986076/alternative-to-virsh-libvirt

            log = u' '.join([u'域', guest.name(), u', UUID', _uuid, u'的状态改变为'])

            if state == libvirt.VIR_DOMAIN_RUNNING:
                log += u' Running。'
                guest_event_emit.running(uuid=_uuid)

            elif state == libvirt.VIR_DOMAIN_BLOCKED:
                log += u' Blocked。'
                guest_event_emit.blocked(uuid=_uuid)

            elif state == libvirt.VIR_DOMAIN_PAUSED:
                log += u' Paused。'
                guest_event_emit.paused(uuid=_uuid)

            elif state == libvirt.VIR_DOMAIN_SHUTDOWN:
                log += u' Shutdown。'
                guest_event_emit.shutdown(uuid=_uuid)

            elif state == libvirt.VIR_DOMAIN_SHUTOFF:
                log += u' Shutoff。'
                guest_event_emit.shutoff(uuid=_uuid)

            elif state == libvirt.VIR_DOMAIN_CRASHED:
                log += u' Crashed。'
                guest_event_emit.crashed(uuid=_uuid)

            elif state == libvirt.VIR_DOMAIN_PMSUSPENDED:
                log += u' PM_Suspended。'
                guest_event_emit.pm_suspended(uuid=_uuid)

            else:
                log += u' NO_State。'

                guest_event_emit.no_state(uuid=_uuid)

            logger.info(log)
            log_emit.info(log)

        except Exception as e:
            logger.error(e.message)
            log_emit.error(e.message)

    @staticmethod
    def update_xml(guest):
        xml = guest.XMLDesc(flags=libvirt.VIR_DOMAIN_XML_SECURE)
        if xml is None:
            return

        else:
            guest_event_emit.update(uuid=guest.UUIDString(), xml=xml)


