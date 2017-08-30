#!/usr/bin/env python
# -*- coding: utf-8 -*-


import os
import sys
import time
import traceback

import libvirt
import json
import jimit as ji
import xml.etree.ElementTree as ET
import uuid

import psutil

from jimvn_exception import ConnFailed

from initialize import config, logger, r, log_emit, response_emit, host_event_emit, collection_performance_emit, \
    thread_status, host_collection_performance_emit
from guest import Guest
from disk import Disk
from utils import Utils
from status import JimVEdition, DFS


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
        self.node_id = uuid.getnode()
        self.cpu = psutil.cpu_count()
        self.memory = psutil.virtual_memory().total
        self.interfaces = dict()
        self.disks = dict()
        self.guest_callbacks = list()
        self.interval = 60
        # self.last_host_cpu_time = dict()
        self.last_host_traffic = dict()
        self.last_host_disk_io = dict()
        self.last_guest_cpu_time = dict()
        self.last_guest_traffic = dict()
        self.last_guest_disk_io = dict()
        self.ts = ji.Common.ts()

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
            self.dirty_scene = False

            if self.guest.gf.exists(self.guest.system_image_path):
                self.guest.gf.remove(self.guest.system_image_path)

            else:
                log = u'清理现场失败: 不存在的路径 --> ' + self.guest.guest_dir
                logger.warn(msg=log)
                log_emit.warn(msg=log)

    def downstream_queue_process_engine(self):
        while True:
            if Utils.exit_flag:
                print 'Thread downstream_queue_process_engine say bye-bye'
                return

            thread_status['downstream_queue_process_engine'] = ji.JITime.now_date_time()
            msg = dict()

            # noinspection PyBroadException
            try:
                # 清理上个周期弄脏的现场
                self.clear_scene()
                # 取系统最近 5 分钟的平均负载值
                load_avg = os.getloadavg()[1]
                # sleep 加 1，避免 load_avg 为 0 时，循环过度
                time.sleep(load_avg * 10 + 1)
                if config['debug']:
                    print 'downstream_queue_process_engine alive: ' + ji.JITime.gmt(ts=time.time())

                msg = r.lpop(config['downstream_queue'])
                if msg is None:
                    continue

                try:
                    msg = json.loads(msg)
                except ValueError as e:
                    logger.error(e.message)
                    log_emit.error(e.message)
                    continue

                if msg['action'] == 'create_disk':
                    if Guest.gf is None:
                        Guest.dfs_volume = msg['glusterfs_volume']
                        Guest.init_gfapi()

                    if Disk.make_qemu_image_by_glusterfs(gf=Guest.gf, glusterfs_volume=msg['glusterfs_volume'],
                                                         image_path=msg['image_path'], size=msg['size']):
                        response_emit.success(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                    else:
                        response_emit.failure(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                # 离线磁盘扩容
                elif msg['action'] == 'resize_disk':
                    if Disk.resize_qemu_image_by_glusterfs(glusterfs_volume=msg['glusterfs_volume'],
                                                           image_path=msg['image_path'], size=msg['size']):
                        response_emit.success(action=msg['action'], uuid=msg['disk_uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                    else:
                        response_emit.failure(action=msg['action'], uuid=msg['disk_uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                elif msg['action'] == 'delete_disk':
                    if Guest.gf is None:
                        Guest.dfs_volume = msg['glusterfs_volume']
                        Guest.init_gfapi()

                    if Disk.delete_qemu_image_by_glusterfs(gf=Guest.gf, image_path=msg['image_path']):
                        response_emit.success(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                    else:
                        response_emit.failure(action=msg['action'], uuid=msg['uuid'],
                                              passback_parameters=msg.get('passback_parameters'))

                else:
                    pass

            except:
                logger.error(traceback.format_exc())
                log_emit.error(traceback.format_exc())
                response_emit.failure(action=msg.get('action'), uuid=msg.get('uuid'),
                                      passback_parameters=msg.get('passback_parameters'))

    # 使用时，创建独立的实例来避开 多线程 的问题
    def guest_operate_engine(self):

        ps = r.pubsub(ignore_subscribe_messages=False)
        ps.subscribe(config['instruction_channel'])

        while True:
            if Utils.exit_flag:
                print 'Thread guest_operate_engine say bye-bye'
                return

            thread_status['guest_operate_engine'] = ji.JITime.now_date_time()

            # noinspection PyBroadException
            try:
                msg = ps.get_message(timeout=1)

                if config['debug']:
                    print 'guest_operate_engine alive: ' + ji.JITime.gmt(ts=time.time())

                if msg is None or 'data' not in msg or not isinstance(msg['data'], basestring):
                    continue

                try:
                    msg = json.loads(msg['data'])

                    if msg['action'] == 'pong':
                        continue

                    if msg['action'] == 'ping':
                        # 通过 ping pong 来刷存在感。因为经过实际测试发现，当订阅频道长时间没有数据来往，那么订阅者会被自动退出。
                        r.publish(config['instruction_channel'], message=json.dumps({'action': 'pong'}))
                        continue

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

                if msg['action'] not in ['create']:

                    if msg['uuid'] not in self.guest_mapping_by_uuid:

                        if config['debug']:
                            log = u' '.join([u'uuid', msg['uuid'], u'在宿主机', self.hostname, u'中未找到.'])
                            logger.debug(log)
                            log_emit.debug(log)

                        continue

                    self.guest = self.guest_mapping_by_uuid[msg['uuid']]
                    if not isinstance(self.guest, libvirt.virDomain):
                        log = u' '.join([u'uuid', msg['uuid'], u'已不存在于', self.hostname, u'在宿主机中。'])
                        logger.warning(log)
                        log_emit.warn(log)
                        continue

                if msg['action'] == 'create':
                    if msg['hostname'] != self.hostname:
                        continue

                    Guest.jimv_edition = msg['jimv_edition']

                    self.guest = Guest(uuid=msg['uuid'], name=msg['name'], template_path=msg['template_path'],
                                       disk=msg['disk'], xml=msg['xml'])

                    if Guest.jimv_edition == JimVEdition.hyper_convergence.value:
                        Guest.dfs = msg['dfs']
                        if Guest.dfs == DFS.glusterfs.value:
                            if Guest.gf is None:
                                Guest.dfs_volume = msg['glusterfs_volume']
                                Guest.init_gfapi()

                    self.guest.system_image_path = self.guest.disk['path']

                    # 虚拟机基础环境路径创建后，至虚拟机定义成功前，认为该环境是脏的
                    self.dirty_scene = True

                    if not self.guest.generate_system_image():
                        response_emit.failure(action=msg['action'], uuid=self.guest.uuid,
                                              passback_parameters=msg.get('passback_parameters'))
                        continue

                    if not self.guest.define_by_xml(conn=self.conn):
                        response_emit.failure(action=msg['action'], uuid=self.guest.uuid,
                                              passback_parameters=msg.get('passback_parameters'))
                        continue

                    # 虚拟机定义成功后，该环境由脏变为干净，重置该变量为 False，避免下个周期被清理现场
                    self.dirty_scene = False

                    disk_info = dict()

                    if Guest.jimv_edition == JimVEdition.hyper_convergence.value:
                        if Guest.dfs == DFS.glusterfs.value:
                            disk_info = Disk.disk_info_by_glusterfs(glusterfs_volume=self.guest.glusterfs_volume,
                                                                    image_path=self.guest.system_image_path)

                    else:
                        disk_info = Disk.disk_info(image_path=self.guest.system_image_path)

                    # 由该线程最顶层的异常捕获机制，处理其抛出的异常
                    self.guest.execute_boot_jobs(guest=self.conn.lookupByUUIDString(uuidstr=self.guest.uuid),
                                                 boot_jobs=msg['boot_jobs'])

                    response_emit.success(action=msg['action'], uuid=self.guest.uuid, data={'disk_info': disk_info},
                                          passback_parameters=msg.get('passback_parameters'))

                    if not self.guest.start_by_uuid(conn=self.conn):
                        # 不清理现场，如需清理，让用户手动通过面板删除
                        continue

                elif msg['action'] == 'reboot':
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
                    if not self.guest.isActive():

                        guest = Guest()
                        guest.execute_boot_jobs(guest=self.guest, boot_jobs=msg['boot_jobs'])

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

                elif msg['action'] == 'delete_guest':
                    root = ET.fromstring(self.guest.XMLDesc())
                    # 签出系统镜像路径
                    path_list = root.find('devices/disk[0]/source').attrib['name'].split('/')

                    if Guest.gf is None:
                        Guest.dfs_volume = path_list[0]
                        Guest.init_gfapi()

                    if self.guest.isActive():
                        self.guest.destroy()

                    if self.guest.undefine() == 0 and \
                            Guest.gf.exists('/'.join(path_list[1:])) and \
                            Guest.gf.remove('/'.join(path_list[1:])) is None:
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
                    msg['size'] = int(msg['size']) * 1024 * 1024

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
                        libvirt.VIR_MIGRATE_PERSIST_DEST | \
                        libvirt.VIR_MIGRATE_UNDEFINE_SOURCE | \
                        libvirt.VIR_MIGRATE_COMPRESSED

                    if self.guest.isActive():
                        flags |= libvirt.VIR_MIGRATE_LIVE
                        flags |= libvirt.VIR_MIGRATE_TUNNELLED
                    else:
                        flags |= libvirt.VIR_MIGRATE_OFFLINE

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

            except:
                logger.error(traceback.format_exc())
                log_emit.error(traceback.format_exc())
                response_emit.failure(action=msg.get('action'), uuid=msg.get('uuid'),
                                      passback_parameters=msg.get('passback_parameters'))

    def update_interfaces(self):
        self.interfaces.clear()
        for nic_name, nic_s in psutil.net_if_addrs().items():
            for nic in nic_s:
                # 参考链接：https://github.com/torvalds/linux/blob/5518b69b76680a4f2df96b1deca260059db0c2de/include/linux/socket.h
                if nic.family == 2:
                    for _nic in nic_s:
                        if _nic.family == 2:
                            self.interfaces[nic_name] = {'ip': _nic.address, 'netmask': _nic.netmask}

                        if _nic.family == 17:
                            self.interfaces[nic_name]['mac'] = _nic.address

    def update_disks(self):
        self.disks.clear()
        for disk in psutil.disk_partitions(all=False):
            disk_usage = psutil.disk_usage(disk.mountpoint)
            self.disks[disk.mountpoint] = {'device': disk.device, 'real_device': disk.device, 'fstype': disk.fstype,
                                           'opts': disk.opts, 'total': disk_usage.total, 'used': disk_usage.used,
                                           'free': disk_usage.free, 'percent': disk_usage.percent}

            if os.path.islink(disk.device):
                self.disks[disk.mountpoint]['real_device'] = os.path.realpath(disk.device)

    # 使用时，创建独立的实例来避开 多线程 的问题
    def state_report_engine(self):
        """
        宿主机状态上报引擎
        """

        # 首次启动时，做数据初始化
        self.update_interfaces()
        self.update_disks()

        while True:
            if Utils.exit_flag:
                print 'Thread state_report_engine say bye-bye'
                return

            thread_status['state_report_engine'] = ji.JITime.now_date_time()

            # noinspection PyBroadException
            try:
                if config['debug']:
                    print 'state_report_engine alive: ' + ji.JITime.gmt(ts=time.time())

                time.sleep(2)

                # 一分钟做一次更新
                if ji.Common.ts() % 60 == 0:
                    self.update_interfaces()
                    self.update_disks()

                host_event_emit.heartbeat(message={'node_id': self.node_id, 'cpu': self.cpu, 'memory': self.memory,
                                                   'interfaces': self.interfaces, 'disks': self.disks,
                                                   'system_load': os.getloadavg(),
                                                   'memory_available': psutil.virtual_memory().available})

            except:
                logger.error(traceback.format_exc())
                log_emit.error(traceback.format_exc())

    def refresh_guest_state(self):
        self.refresh_guest_mapping()

        for guest in self.guest_mapping_by_uuid.values():
            Guest.guest_state_report(guest)

    def cpu_memory_performance_report(self):

        data = list()

        for _uuid, guest in self.guest_mapping_by_uuid.items():

            if not guest.isActive():
                continue

            _, _, _, cpu_count, _ = guest.info()
            cpu_time2 = guest.getCPUStats(True)[0]['cpu_time']

            cpu_memory = dict()

            if _uuid in self.last_guest_cpu_time:
                cpu_load = (cpu_time2 - self.last_guest_cpu_time[_uuid]['cpu_time']) / self.interval / 1000 ** 3. \
                           * 100 / cpu_count
                # 计算 cpu_load 的公式：
                # (cpu_time2 - cpu_time1) / interval_N / 1000**3.(nanoseconds to seconds) * 100(percent) /
                # cpu_count
                # cpu_time == user_time + system_time + guest_time
                #
                # 参考链接：
                # https://libvirt.org/html/libvirt-libvirt-domain.html#VIR_DOMAIN_STATS_CPU_TOTAL
                # https://stackoverflow.com/questions/40468370/what-does-cpu-time-represent-exactly-in-libvirt
                cpu_memory = {
                    'guest_uuid': _uuid,
                    'cpu_load': cpu_load if cpu_load <= 100 else 100,
                    'memory_available': 0,
                    'memory_unused': 0
                }

            else:
                self.last_guest_cpu_time[_uuid] = dict()

            self.last_guest_cpu_time[_uuid]['cpu_time'] = cpu_time2
            self.last_guest_cpu_time[_uuid]['timestamp'] = self.ts

            if cpu_memory.__len__() > 0:
                data.append(cpu_memory)

        if data.__len__() > 0:
            collection_performance_emit.cpu_memory(data=data)

    def traffic_performance_report(self):

        data = list()

        for _uuid, guest in self.guest_mapping_by_uuid.items():

            if not guest.isActive():
                continue

            root = ET.fromstring(guest.XMLDesc())

            for interface in root.findall('devices/interface'):
                dev = interface.find('target').get('dev')
                name = interface.find('alias').get('name')
                interface_state = guest.interfaceStats(dev)

                interface_id = '_'.join([_uuid, dev])

                traffic = dict()

                if interface_id in self.last_guest_traffic:

                    traffic = {
                        'guest_uuid': _uuid,
                        'name': name,
                        'rx_bytes':
                            (interface_state[0] - self.last_guest_traffic[interface_id]['rx_bytes']) / self.interval,
                        'rx_packets':
                            (interface_state[1] - self.last_guest_traffic[interface_id]['rx_packets']) / self.interval,
                        'rx_errs': interface_state[2],
                        'rx_drop': interface_state[3],
                        'tx_bytes':
                            (interface_state[4] - self.last_guest_traffic[interface_id]['tx_bytes']) / self.interval,
                        'tx_packets':
                            (interface_state[5] - self.last_guest_traffic[interface_id]['tx_packets']) / self.interval,
                        'tx_errs': interface_state[6],
                        'tx_drop': interface_state[7]
                    }

                else:
                    self.last_guest_traffic[interface_id] = dict()

                self.last_guest_traffic[interface_id]['rx_bytes'] = interface_state[0]
                self.last_guest_traffic[interface_id]['rx_packets'] = interface_state[1]
                self.last_guest_traffic[interface_id]['tx_bytes'] = interface_state[4]
                self.last_guest_traffic[interface_id]['tx_packets'] = interface_state[5]
                self.last_guest_traffic[interface_id]['timestamp'] = self.ts

                if traffic.__len__() > 0:
                    data.append(traffic)

        if data.__len__() > 0:
            collection_performance_emit.traffic(data=data)

    def disk_io_performance_report(self):

        data = list()

        for _uuid, guest in self.guest_mapping_by_uuid.items():

            if not guest.isActive():
                continue

            root = ET.fromstring(guest.XMLDesc())

            for disk in root.findall('devices/disk'):
                dev = disk.find('target').get('dev')
                protocol = disk.find('source').get('protocol')

                dev_path = None

                if protocol in [None, 'file']:
                    dev_path = disk.find('source').get('file')

                elif protocol == 'gluster':
                    dev_path = disk.find('source').get('name')

                if dev_path is None:
                    continue

                disk_uuid = dev_path.split('/')[-1].split('.')[0]
                disk_state = guest.blockStats(dev)

                disk_io = dict()

                if disk_uuid in self.last_guest_disk_io:

                    disk_io = {
                        'disk_uuid': disk_uuid,
                        'rd_req': (disk_state[0] - self.last_guest_disk_io[disk_uuid]['rd_req']) / self.interval,
                        'rd_bytes': (disk_state[1] - self.last_guest_disk_io[disk_uuid]['rd_bytes']) / self.interval,
                        'wr_req': (disk_state[2] - self.last_guest_disk_io[disk_uuid]['wr_req']) / self.interval,
                        'wr_bytes': (disk_state[3] - self.last_guest_disk_io[disk_uuid]['wr_bytes']) / self.interval
                    }

                else:
                    self.last_guest_disk_io[disk_uuid] = dict()

                self.last_guest_disk_io[disk_uuid]['rd_req'] = disk_state[0]
                self.last_guest_disk_io[disk_uuid]['rd_bytes'] = disk_state[1]
                self.last_guest_disk_io[disk_uuid]['wr_req'] = disk_state[2]
                self.last_guest_disk_io[disk_uuid]['wr_bytes'] = disk_state[3]
                self.last_guest_disk_io[disk_uuid]['timestamp'] = self.ts

                if disk_io.__len__() > 0:
                    data.append(disk_io)

        if data.__len__() > 0:
            collection_performance_emit.disk_io(data=data)

    def collection_performance_process_engine(self):

        while True:
            if Utils.exit_flag:
                print 'Thread collection_performance_process_engine say bye-bye'
                return

            if config['debug']:
                print 'collection_performance_process_engine alive: ' + ji.JITime.gmt(ts=time.time())

            thread_status['collection_performance_process_engine'] = ji.JITime.now_date_time()
            time.sleep(1)
            self.ts = ji.Common.ts()

            # noinspection PyBroadException
            try:

                if self.ts % self.interval != 0:
                    continue

                if self.ts % 3600 == 0:
                    # 一小时做一次 垃圾回收 操作
                    for k, v in self.last_guest_cpu_time.items():
                        if (self.ts - v['timestamp']) > self.interval * 2:
                            del self.last_guest_cpu_time[k]

                    for k, v in self.last_guest_traffic.items():
                        if (self.ts - v['timestamp']) > self.interval * 2:
                            del self.last_guest_traffic[k]

                    for k, v in self.last_guest_disk_io.items():
                        if (self.ts - v['timestamp']) > self.interval * 2:
                            del self.last_guest_disk_io[k]

                self.refresh_guest_mapping()

                self.cpu_memory_performance_report()
                self.traffic_performance_report()
                self.disk_io_performance_report()

            except:
                print traceback.format_exc()
                logger.error(traceback.format_exc())
                log_emit.error(traceback.format_exc())

    def host_cpu_memory_performance_report(self):

        cpu_memory = {
            'node_id': self.node_id,
            'cpu_load': psutil.cpu_percent(interval=None, percpu=False),
            'memory_available': psutil.virtual_memory().available,
        }

        host_collection_performance_emit.cpu_memory(data=cpu_memory)

    def host_traffic_performance_report(self):

        data = list()
        net_io = psutil.net_io_counters(pernic=True)

        for nic_name in self.interfaces.keys():
            nic = net_io.get(nic_name, None)
            if nic is None:
                continue

            traffic = list()

            if nic_name in self.last_host_traffic:
                traffic = {
                    'node_id': self.node_id,
                    'name': nic_name,
                    'rx_bytes': (nic.bytes_recv - self.last_host_traffic[nic_name].bytes_recv) / self.interval,
                    'rx_packets':
                        (nic.packets_recv - self.last_host_traffic[nic_name].packets_recv) / self.interval,
                    'rx_errs': (nic.errin - self.last_host_traffic[nic_name].errin),
                    'rx_drop': (nic.dropin - self.last_host_traffic[nic_name].dropin),
                    'tx_bytes': (nic.bytes_sent - self.last_host_traffic[nic_name].bytes_sent) / self.interval,
                    'tx_packets':
                        (nic.packets_sent - self.last_host_traffic[nic_name].packets_sent) / self.interval,
                    'tx_errs': (nic.errout - self.last_host_traffic[nic_name].errout),
                    'tx_drop': (nic.dropout - self.last_host_traffic[nic_name].dropout)
                }
            elif not isinstance(self.last_host_disk_io, dict):
                self.last_host_traffic = dict()

            self.last_host_traffic[nic_name] = nic

            if traffic.__len__() > 0:
                data.append(traffic)

        if data.__len__() > 0:
            host_collection_performance_emit.traffic(data=data)

    def host_disk_usage_io_performance_report(self):

        data = list()
        disk_io_counters = psutil.disk_io_counters(perdisk=True)

        for mountpoint, disk in self.disks.items():
            dev = os.path.basename(disk['real_device'])
            disk_usage_io = list()
            if dev in self.last_host_disk_io:
                disk_usage_io = {
                    'node_id': self.node_id,
                    'mountpoint': mountpoint,
                    'used': psutil.disk_usage(mountpoint).used,
                    'rd_req':
                        (disk_io_counters[dev].read_count - self.last_host_disk_io[dev].read_count) / self.interval,
                    'rd_bytes':
                        (disk_io_counters[dev].read_bytes - self.last_host_disk_io[dev].read_bytes) / self.interval,
                    'wr_req':
                        (disk_io_counters[dev].write_count - self.last_host_disk_io[dev].write_count) / self.interval,
                    'wr_bytes':
                        (disk_io_counters[dev].write_bytes - self.last_host_disk_io[dev].write_bytes) / self.interval
                }

            elif not isinstance(self.last_host_disk_io, dict):
                self.last_host_disk_io = dict()

            self.last_host_disk_io[dev] = disk_io_counters[dev]

            if disk_usage_io.__len__() > 0:
                data.append(disk_usage_io)

        if data.__len__() > 0:
            host_collection_performance_emit.disk_usage_io(data=data)

    def host_collection_performance_process_engine(self):

        while True:
            if Utils.exit_flag:
                print 'Thread host_collection_performance_process_engine say bye-bye'
                return

            if config['debug']:
                print 'host_collection_performance_process_engine alive: ' + ji.JITime.gmt(ts=time.time())

            thread_status['host_collection_performance_process_engine'] = ji.JITime.now_date_time()
            time.sleep(1)
            self.ts = ji.Common.ts()

            # noinspection PyBroadException
            try:

                if self.ts % self.interval != 0:
                    continue

                self.update_interfaces()
                self.update_disks()
                self.host_cpu_memory_performance_report()
                self.host_traffic_performance_report()
                self.host_disk_usage_io_performance_report()

            except:
                print traceback.format_exc()
                logger.error(traceback.format_exc())
                log_emit.error(traceback.format_exc())

