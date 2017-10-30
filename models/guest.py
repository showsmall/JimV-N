#!/usr/bin/env python
# -*- coding: utf-8 -*-


import os
import shutil
import traceback

import guestfs
import libvirt
import threading
from gluster import gfapi
import xml.etree.ElementTree as ET

from initialize import logger, log_emit, guest_event_emit, q_creating_guest, response_emit
from models.status import OperateRuleKind, StorageMode, OSType
from disk import Disk


__author__ = 'James Iter'
__date__ = '2017/3/1'
__contact__ = 'james.iter.cn@gmail.com'
__copyright__ = '(c) 2017 by James Iter.'


class Guest(object):
    jimv_edition = None
    storage_mode = None
    gf = None
    dfs_volume = None
    thread_mutex_lock = threading.Lock()

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
        self.xml = kwargs.get('xml', None)
        # Guest 系统镜像路径，不包含 dfs 卷标
        self.system_image_path = None
        self.g = guestfs.GuestFS(python_return_dict=True)

    @classmethod
    def init_gfapi(cls):
        cls.thread_mutex_lock.acquire()

        if cls.gf is None:
            cls.gf = gfapi.Volume('127.0.0.1', cls.dfs_volume)
            cls.gf.mount()

        cls.thread_mutex_lock.release()

        return cls.gf

    def generate_system_image(self):
        if self.storage_mode in [StorageMode.ceph.value, StorageMode.glusterfs.value]:
            if self.storage_mode == StorageMode.glusterfs.value:
                if not self.gf.isfile(self.template_path):
                    log = u' '.join([u'域', self.name, u', UUID', self.uuid, u'所依赖的模板', self.template_path, u'不存在.'])
                    logger.error(msg=log)
                    log_emit.error(msg=log)
                    return False

                if not self.gf.isdir(os.path.dirname(self.system_image_path)):
                    self.gf.makedirs(os.path.dirname(self.system_image_path), 0755)

                self.gf.copyfile(self.template_path, self.system_image_path)

        elif self.storage_mode in [StorageMode.local.value, StorageMode.shared_mount.value]:
            if not os.path.exists(self.template_path) or not os.path.isfile(self.template_path):
                log = u' '.join([u'域', self.name, u', UUID', self.uuid, u'所依赖的模板', self.template_path, u'不存在.'])
                logger.error(msg=log)
                log_emit.error(msg=log)
                return False

            if not os.access(self.template_path, os.R_OK):
                log = u' '.join([u'域', self.name, u', UUID', self.uuid, u'所依赖的模板', self.template_path, u'无权访问.'])
                logger.error(msg=log)
                log_emit.error(msg=log)
                return False

            system_image_path_dir = os.path.dirname(self.system_image_path)

            if not os.path.exists(system_image_path_dir):
                os.makedirs(system_image_path_dir, 0755)

            elif not os.path.isdir(system_image_path_dir):
                os.rename(system_image_path_dir, system_image_path_dir + '.bak')
                os.makedirs(system_image_path_dir, 0755)

            shutil.copyfile(self.template_path, self.system_image_path)

        else:
            raise

        return True

    def execute_boot_jobs(self, guest=None, boot_jobs=None, os_type=None):
        if not isinstance(boot_jobs, list):
            raise

        if boot_jobs.__len__() < 1:
            return True

        self.xml = guest.XMLDesc()
        root = ET.fromstring(self.xml)

        if self.storage_mode in [StorageMode.ceph.value, StorageMode.glusterfs.value]:
            for dev in root.findall('devices/disk'):
                filename = dev.find('source').get('name')
                _format = dev.find('driver').attrib['type']
                protocol = dev.find('source').get('protocol')
                server = dev.find('source/host').get('name')
                self.g.add_drive(filename=filename, format=_format, protocol=protocol, server=[server])

        elif self.storage_mode in [StorageMode.local.value, StorageMode.shared_mount.value]:
            for dev in root.findall('devices/disk'):
                filename = dev.find('source').get('file')
                _format = dev.find('driver').attrib['type']
                self.g.add_drive(filename=filename, format=_format, protocol='file')

        self.g.launch()
        self.g.mount(self.g.inspect_os()[0], '/')

        for boot_job in boot_jobs:
            if boot_job['kind'] == OperateRuleKind.cmd.value:

                if os_type == OSType.windows.value:
                    continue

                self.g.sh(boot_job['command'])

            elif boot_job['kind'] == OperateRuleKind.write_file.value:

                content = boot_job['content']
                if os_type == OSType.windows.value:
                    content.replace(r'\n', '\r\n')

                self.g.write(boot_job['path'], content)

            elif boot_job['kind'] == OperateRuleKind.append_file.value:

                content = boot_job['content']
                if os_type == OSType.windows.value:
                    content.replace(r'\n', '\r\n')

                self.g.write_append(boot_job['path'], content)

            else:
                continue

        self.g.shutdown()
        self.g.close()

        return True

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

    @staticmethod
    def create(conn, msg):

        try:
            Guest.storage_mode = msg['storage_mode']

            guest = Guest(uuid=msg['uuid'], name=msg['name'], template_path=msg['template_path'],
                          disk=msg['disk'], xml=msg['xml'])

            if Guest.storage_mode == StorageMode.glusterfs.value:
                Guest.dfs_volume = msg['dfs_volume']
                Guest.init_gfapi()

            guest.system_image_path = guest.disk['path']

            q_creating_guest.put({
                'storage_mode': Guest.storage_mode,
                'dfs_volume': Guest.dfs_volume,
                'uuid': guest.uuid,
                'template_path': guest.template_path,
                'system_image_path': guest.system_image_path
            })

            if not guest.generate_system_image():
                raise

            if not guest.define_by_xml(conn=conn):
                raise

            guest_event_emit.creating(uuid=guest.uuid, progress=92)

            disk_info = dict()

            if Guest.storage_mode == StorageMode.glusterfs.value:
                disk_info = Disk.disk_info_by_glusterfs(dfs_volume=guest.dfs_volume,
                                                        image_path=guest.system_image_path)

            elif Guest.storage_mode in [StorageMode.local.value, StorageMode.shared_mount.value]:
                disk_info = Disk.disk_info_by_local(image_path=guest.system_image_path)

            # 由该线程最顶层的异常捕获机制，处理其抛出的异常
            guest.execute_boot_jobs(guest=conn.lookupByUUIDString(uuidstr=guest.uuid),
                                    boot_jobs=msg['boot_jobs'], os_type=msg['os_type'])

            extend_data = dict()
            extend_data.update({'disk_info': disk_info})

            guest_event_emit.creating(uuid=guest.uuid, progress=97)

            if not guest.start_by_uuid(conn=conn):
                raise

            response_emit.success(_object=msg['_object'], action=msg['action'], uuid=msg['uuid'],
                                  data=extend_data, passback_parameters=msg.get('passback_parameters'))

        except:
            logger.error(traceback.format_exc())
            log_emit.error(traceback.format_exc())
            response_emit.failure(_object=msg['_object'], action=msg.get('action'), uuid=msg.get('uuid'),
                                  passback_parameters=msg.get('passback_parameters'))
