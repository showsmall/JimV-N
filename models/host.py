#!/usr/bin/env python
# -*- coding: utf-8 -*-


import os
import sys
import time
import libvirt
import json
import jimit as ji
import xml.etree.ElementTree as ET

from jimvn_exception import ConnFailed

from initialize import config, logger, r, log_emit, event_emit, response_emit
from guest import Guest
from guest_disk import GuestDisk
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
        self.guest_mapping_by_uuid = dict()
        self.hostname = ji.Common.get_hostname()

    def init_conn(self):
        self.conn = libvirt.open()

        if self.conn is None:
            raise ConnFailed(u'打开连接失败 --> ' + sys.stderr)

    def refresh_guest_mapping(self):
        # 调用该方法的函数，都为单独的对象实例。即不存在多线程共用该方法，故而不用加多线程锁
        self.guest_mapping_by_uuid.clear()
        for guest in self.conn.listAllDomains():
            self.guest_mapping_by_uuid[guest.UUIDString()] = guest

    def clear_scene(self):

        if self.dirty_scene:

            if self.guest.gf.exists(self.guest.guest_dir):
                self.guest.gf.rmtree(self.guest.guest_dir)

            else:
                log = u'清理现场失败: 不存在的路径 --> ' + self.guest.guest_dir
                logger.warn(msg=log)
                log_emit.warn(msg=log)

            self.dirty_scene = False

    def downstream_queue_process_engine(self):
        while True:
            if Utils.exit_flag:
                Utils.thread_counter -= 1
                print 'Thread downstream_queue_process_engine say bye-bye'
                return

            msg = dict()

            try:
                # 清理上个周期弄脏的现场
                self.clear_scene()
                # 取系统最近 5 分钟的平均负载值
                load_avg = os.getloadavg()[1]
                # sleep 加 1，避免 load_avg 为 0 时，循环过度
                time.sleep(load_avg * 10 + 1)
                if config['debug']:
                    print 'downstream_queue_process_engine alive: ' + ji.JITime.gmt(ts=time.time())

                # 大于 0.6 的系统将不再被分配创建虚拟机
                if load_avg > 0.6:
                    continue

                msg = r.lpop(config['downstream_queue'])
                if msg is None:
                    continue

                try:
                    msg = json.loads(msg)
                except ValueError as e:
                    logger.error(e.message)
                    log_emit.error(e.message)
                    continue

                if msg['action'] == 'create_vm':

                    self.guest = Guest(uuid=msg['uuid'], name=msg['name'], glusterfs_volume=msg['glusterfs_volume'],
                                       template_path=msg['template_path'], disk=msg['guest_disk'],
                                       password=msg['password'], writes=msg['writes'], xml=msg['xml'])
                    if Guest.gf is None:
                        Guest.glusterfs_volume = msg['glusterfs_volume']
                        Guest.init_gfapi()

                    self.guest.generate_guest_dir()

                    # 虚拟机基础环境路径创建后，至虚拟机定义成功前，认为该环境是脏的
                    self.dirty_scene = True

                    if not self.guest.generate_system_image():
                        response_emit.failure(action=msg['action'], uuid=self.guest.uuid,
                                              passback_parameters=msg.get('passback_parameters'))
                        continue

                    # 由该线程最顶层的异常捕获机制，处理其抛出的异常
                    self.guest.init_config()

                    if not self.guest.define_by_xml(conn=self.conn):
                        response_emit.failure(action=msg['action'], uuid=self.guest.uuid,
                                              passback_parameters=msg.get('passback_parameters'))
                        continue

                    # 虚拟机定义成功后，该环境由脏变为干净，重置该变量为 False，避免下个周期被清理现场
                    self.dirty_scene = False
                    response_emit.success(action=msg['action'], uuid=self.guest.uuid,
                                          passback_parameters=msg.get('passback_parameters'))

                    if not self.guest.start_by_uuid(conn=self.conn):
                        # 不清理现场，如需清理，让用户手动通过面板删除
                        continue

                elif msg['action'] == 'create_disk':
                    if Guest.gf is None:
                        Guest.glusterfs_volume = msg['glusterfs_volume']
                        Guest.init_gfapi()

                    if GuestDisk.make_qemu_image_by_glusterfs(gf=Guest.gf, glusterfs_volume=msg['glusterfs_volume'],
                                                              image_path=msg['image_path'], size=msg['size']):
                        response_emit.success(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                    else:
                        response_emit.failure(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                # 离线磁盘扩容
                elif msg['action'] == 'resize_disk':
                    if GuestDisk.resize_qemu_image_by_glusterfs(glusterfs_volume=msg['glusterfs_volume'],
                                                                image_path=msg['image_path'], size=msg['size']):
                        response_emit.success(action=msg['action'], uuid=msg['disk_uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                    else:
                        response_emit.failure(action=msg['action'], uuid=msg['disk_uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                elif msg['action'] == 'delete_disk':
                    if Guest.gf is None:
                        Guest.glusterfs_volume = msg['glusterfs_volume']
                        Guest.init_gfapi()

                    if GuestDisk.delete_qemu_image_by_glusterfs(gf=Guest.gf, image_path=msg['image_path']):
                        response_emit.success(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                    else:
                        response_emit.failure(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                else:
                    pass

            except Exception as e:
                logger.error(e.message)
                log_emit.error(e.message)
                response_emit.failure(action=msg.get('action'), uuid=msg.get('uuid'),
                                      passback_parameters=msg.get('passback_parameters'))

    # 使用时，创建独立的实例来避开 多线程 的问题
    def guest_operate_engine(self):

        ps = r.pubsub(ignore_subscribe_messages=False)
        ps.subscribe(config['instruction_channel'])

        while True:
            if Utils.exit_flag:
                Utils.thread_counter -= 1
                print 'Thread guest_operate_engine say bye-bye'
                return

            try:
                msg = ps.get_message(timeout=1)
                if config['debug']:
                    print 'guest_operate_engine alive: ' + ji.JITime.gmt(ts=time.time())
                if msg is None or 'data' not in msg or not isinstance(msg['data'], basestring):
                    continue

                try:
                    msg = json.loads(msg['data'])
                except ValueError as e:
                    logger.error(e.message)
                    log_emit.error(e.message)
                    continue

                # guest_uuid 与 uuid 一个意思
                if 'guest_uuid' in msg:
                    msg['uuid'] = msg['guest_uuid']

                # 下列语句繁琐写法如 <code>if 'action' not in msg or 'uuid' not in msg:</code>
                if not all([key in msg for key in ['action', 'uuid']]):
                    continue

                self.refresh_guest_mapping()

                if msg['uuid'] not in self.guest_mapping_by_uuid:

                    if config['debug']:
                        log = u' '.join([u'uuid', msg['uuid'], u'在宿主机', self.hostname, u'中未找到.'])
                        logger.debug(log)
                        log_emit.debug(log)

                    continue

                self.guest = self.guest_mapping_by_uuid[msg['uuid']]
                assert isinstance(self.guest, libvirt.virDomain)

                if msg['action'] == 'reboot':
                    if self.guest.reboot() == 0:
                        response_emit.success(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                    else:
                        response_emit.failure(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                elif msg['action'] == 'force_reboot':
                    if self.guest.destroy() == 0 and self.guest.create() == 0:
                        response_emit.success(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                    else:
                        response_emit.failure(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                elif msg['action'] == 'shutdown':
                    if self.guest.shutdown() == 0:
                        response_emit.success(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                    else:
                        response_emit.failure(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                elif msg['action'] == 'force_shutdown':
                    if self.guest.destroy() == 0:
                        response_emit.success(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                    else:
                        response_emit.failure(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                elif msg['action'] == 'boot':
                    if self.guest.create() == 0:
                        response_emit.success(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                    else:
                        response_emit.failure(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                elif msg['action'] == 'suspend':
                    if self.guest.suspend() == 0:
                        response_emit.success(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                    else:
                        response_emit.failure(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                elif msg['action'] == 'resume':
                    if self.guest.resume() == 0:
                        response_emit.success(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                    else:
                        response_emit.failure(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                elif msg['action'] == 'delete':
                    root = ET.fromstring(self.guest.XMLDesc())
                    # 签出系统镜像路径
                    path_list = root.find('devices/disk[0]/source').attrib['name'].split('/')

                    if Guest.gf is None:
                        Guest.glusterfs_volume = path_list[0]
                        Guest.init_gfapi()

                    if self.guest.destroy() == 0 and self.guest.undefine() == 0 and \
                            Guest.gf.exists('/'.join(path_list[1:3])) and \
                            Guest.gf.rmtree('/'.join(path_list[1:3])) is None:
                        response_emit.success(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                    else:
                        response_emit.failure(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                # 在线磁盘扩容
                elif msg['action'] == 'resize_disk':

                    if not all([key in msg for key in ['device_node', 'size']]):
                        log = u'添加磁盘缺少 disk 或 disk["device_node|size"] 参数'
                        raise KeyError(log)

                    # 磁盘大小默认单位为KB，乘以两个 1024，使其单位达到GB
                    msg['size'] = msg['size'] * 1024 * 1024

                    if self.guest.blockResize(disk=msg['device_node'], size=msg['size']) == 0:
                        response_emit.success(action=msg['action'], uuid=msg['disk_uuid'],
                                              passback_parameters=msg.get('passback_parameters'))
                    else:
                        response_emit.failure(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                elif msg['action'] == 'attach_disk':

                    if 'xml' not in msg:
                        log = u'添加磁盘缺少 xml 参数'
                        raise KeyError(log)

                    flags = libvirt.VIR_DOMAIN_AFFECT_CONFIG
                    if self.guest.isActive():
                        flags |= libvirt.VIR_DOMAIN_AFFECT_LIVE

                    # 添加磁盘成功返回时，ret值为0。可参考 Linux 命令返回值规范？
                    if self.guest.attachDeviceFlags(xml=msg['xml'], flags=flags) == 0:
                        response_emit.success(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))
                    else:
                        response_emit.failure(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                elif msg['action'] == 'detach_disk':

                    if 'xml' not in msg:
                        log = u'分离磁盘缺少 xml 参数'
                        raise KeyError(log)

                    flags = libvirt.VIR_DOMAIN_AFFECT_CONFIG
                    if self.guest.isActive():
                        flags |= libvirt.VIR_DOMAIN_AFFECT_LIVE

                    if self.guest.detachDeviceFlags(xml=msg['xml'], flags=flags) == 0:
                        response_emit.success(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))
                    else:
                        response_emit.failure(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                elif msg['action'] == 'migrate':

                    # duri like qemu+ssh://destination_host/system
                    if 'duri' not in msg:
                        log = u'迁移操作缺少 duri 参数'
                        raise KeyError(log)

                    flags = libvirt.VIR_MIGRATE_PEER2PEER | \
                        libvirt.VIR_MIGRATE_TUNNELLED | \
                        libvirt.VIR_MIGRATE_PERSIST_DEST | \
                        libvirt.VIR_MIGRATE_UNDEFINE_SOURCE | \
                        libvirt.VIR_MIGRATE_COMPRESSED

                    if self.guest.isActive() == 0:
                        flags |= libvirt.VIR_MIGRATE_LIVE

                    if self.guest.migrateToURI(duri=msg['duri'], flags=flags) == 0:
                        response_emit.success(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))
                    else:
                        response_emit.failure(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                else:
                    log = u'未支持的 action：' + msg['action']
                    logger.error(log)
                    log_emit.error(log)

            except Exception as e:
                logger.error(e.message)
                log_emit.error(e.message)
                response_emit.failure(action=msg.get('action'), uuid=msg.get('uuid'),
                                      passback_parameters=msg.get('passback_parameters'))

    # 使用时，创建独立的实例来避开 多线程 的问题
    def guest_state_report_engine(self):

        guests_last_state = dict()

        while True:
            if Utils.exit_flag:
                Utils.thread_counter -= 1
                print 'Thread guest_state_report_engine say bye-bye'
                return

            try:
                if config['debug']:
                    print 'guest_state_report_engine alive: ' + ji.JITime.gmt(ts=time.time())

                time.sleep(2)

                self.refresh_guest_mapping()

                for uuid, domain in self.guest_mapping_by_uuid.items():
                    # state 参考链接：
                    # http://libvirt.org/docs/libvirt-appdev-guide-python/en-US/html/libvirt_application_development_guide_using_python-Guest_Domains-Information-State.html
                    # http://stackoverflow.com/questions/4986076/alternative-to-virsh-libvirt

                    state, maxmem, mem, ncpu, cputime = domain.info()

                    # 与 Guest 最后一次的状态做比较后，有差异的上报状态，没有差异的不做任何处理。
                    if uuid in guests_last_state and guests_last_state[uuid] == state:
                        continue

                    guests_last_state[uuid] = state

                    log = u' '.join([u'域', domain.name(), u', UUID', uuid, u'的状态改变为'])

                    if state == libvirt.VIR_DOMAIN_RUNNING:
                        log += u' Running。'
                        event_emit.running(uuid=uuid)

                    elif state == libvirt.VIR_DOMAIN_BLOCKED:
                        log += u' Blocked。'
                        event_emit.blocked(uuid=uuid)

                    elif state == libvirt.VIR_DOMAIN_PAUSED:
                        log += u' Paused。'
                        event_emit.paused(uuid=uuid)

                    elif state == libvirt.VIR_DOMAIN_SHUTDOWN:
                        log += u' Shutdown。'
                        event_emit.shutdown(uuid=uuid)

                    elif state == libvirt.VIR_DOMAIN_SHUTOFF:
                        log += u' Shutoff。'
                        event_emit.shutoff(uuid=uuid)

                    elif state == libvirt.VIR_DOMAIN_CRASHED:
                        log += u' Crashed。'
                        event_emit.crashed(uuid=uuid)

                    elif state == libvirt.VIR_DOMAIN_PMSUSPENDED:
                        log += u' PM_Suspended。'
                        event_emit.pm_suspended(uuid=uuid)

                    else:
                        log += u' NO_State。'

                        event_emit.no_state(uuid=uuid)

                    logger.info(log)
                    log_emit.info(log)

            except Exception as e:
                logger.error(e.message)
                log_emit.error(e.message)

