#!/usr/bin/env python
# -*- coding: utf-8 -*-


import os
import sys
import time
import traceback
import Queue

import libvirt
import json
import jimit as ji
import xml.etree.ElementTree as ET
import uuid

import psutil
import paramiko
import thread

from jimvn_exception import ConnFailed

from initialize import config, logger, r, log_emit, response_emit, host_event_emit, collection_performance_emit, \
    thread_status, host_collection_performance_emit, guest_event_emit, q_creating_guest
from guest import Guest
from disk import Disk
from utils import Utils
from status import StorageMode


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
        self.ssh_client = None

    def init_conn(self):
        self.conn = libvirt.open()

        if self.conn is None:
            raise ConnFailed(u'打开连接失败 --> ' + sys.stderr)

    def init_ssh_client(self, hostname, user):
        self.ssh_client = paramiko.SSHClient()
        self.ssh_client.load_system_host_keys()
        self.ssh_client.set_missing_host_key_policy(paramiko.MissingHostKeyPolicy())
        self.ssh_client.connect(hostname=hostname, username=user)
        return True

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
                # self.clear_scene()
                # 取系统最近 5 分钟的平均负载值
                load_avg = os.getloadavg()[1]
                # sleep 加 1，避免 load_avg 为 0 时，循环过度
                time.sleep(load_avg * 10 + 1)
                if config['DEBUG']:
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

                if config['DEBUG']:
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

                if 'hostname' in msg and msg['hostname'] != self.hostname:
                    continue

                # 下列语句繁琐写法如 <code>if 'action' not in msg or 'uuid' not in msg:</code>
                if not all([key in msg for key in ['_object', 'action', 'uuid']]):
                    continue

                extend_data = dict()

                if msg['_object'] == 'guest':

                    self.refresh_guest_mapping()
                    if msg['action'] not in ['create']:

                        if msg['uuid'] not in self.guest_mapping_by_uuid:

                            if config['DEBUG']:
                                _log = u' '.join([u'uuid', msg['uuid'], u'在宿主机', self.hostname, u'中未找到.'])
                                logger.debug(_log)
                                log_emit.debug(_log)

                            raise

                        self.guest = self.guest_mapping_by_uuid[msg['uuid']]
                        if not isinstance(self.guest, libvirt.virDomain):
                            raise

                    if msg['action'] == 'create':
                        thread.start_new_thread(Guest.create, (self.conn, msg))
                        continue

                    elif msg['action'] == 'reboot':
                        if self.guest.reboot() != 0:
                            raise

                    elif msg['action'] == 'force_reboot':
                        self.guest.destroy()
                        self.guest.create()

                    elif msg['action'] == 'shutdown':
                        if self.guest.shutdown() != 0:
                            raise

                    elif msg['action'] == 'force_shutdown':
                        if self.guest.destroy() != 0:
                            raise

                    elif msg['action'] == 'boot':
                        if not self.guest.isActive():

                            guest = Guest()
                            guest.execute_boot_jobs(guest=self.guest, boot_jobs=msg['boot_jobs'])

                            if self.guest.create() != 0:
                                raise

                    elif msg['action'] == 'suspend':
                        if self.guest.suspend() != 0:
                            raise

                    elif msg['action'] == 'resume':
                        if self.guest.resume() != 0:
                            raise

                    elif msg['action'] == 'delete':
                        root = ET.fromstring(self.guest.XMLDesc())

                        if self.guest.isActive():
                            self.guest.destroy()

                        self.guest.undefine()

                        system_disk = None

                        for _disk in root.findall('devices/disk'):
                            if 'vda' == _disk.find('target').get('dev'):
                                system_disk = _disk

                        if msg['storage_mode'] in [StorageMode.ceph.value, StorageMode.glusterfs.value]:
                            # 签出系统镜像路径
                            path_list = system_disk.find('source').attrib['name'].split('/')

                        if msg['storage_mode'] == StorageMode.glusterfs.value:
                            Guest.dfs_volume = path_list[0]
                            Guest.init_gfapi()

                            try:
                                Guest.gf.remove('/'.join(path_list[1:]))
                            except OSError:
                                pass

                        elif msg['storage_mode'] in [StorageMode.local.value, StorageMode.shared_mount.value]:
                            file_path = system_disk.find('source').attrib['file']
                            try:
                                os.remove(file_path)
                            except OSError:
                                pass

                    elif msg['action'] == 'attach_disk':

                        if 'xml' not in msg:
                            _log = u'添加磁盘缺少 xml 参数'
                            raise KeyError(_log)

                        flags = libvirt.VIR_DOMAIN_AFFECT_CONFIG
                        if self.guest.isActive():
                            flags |= libvirt.VIR_DOMAIN_AFFECT_LIVE

                        # 添加磁盘成功返回时，ret值为0。可参考 Linux 命令返回值规范？
                        if self.guest.attachDeviceFlags(xml=msg['xml'], flags=flags) != 0:
                            raise

                    elif msg['action'] == 'detach_disk':

                        if 'xml' not in msg:
                            _log = u'分离磁盘缺少 xml 参数'
                            raise KeyError(_log)

                        flags = libvirt.VIR_DOMAIN_AFFECT_CONFIG
                        if self.guest.isActive():
                            flags |= libvirt.VIR_DOMAIN_AFFECT_LIVE

                        if self.guest.detachDeviceFlags(xml=msg['xml'], flags=flags) != 0:
                            raise

                    elif msg['action'] == 'migrate':

                        # duri like qemu+ssh://destination_host/system
                        if 'duri' not in msg:
                            _log = u'迁移操作缺少 duri 参数'
                            raise KeyError(_log)

                        # https://rk4n.github.io/2016/08/10/qemu-post-copy-and-auto-converge-features/
                        flags = libvirt.VIR_MIGRATE_PERSIST_DEST | \
                            libvirt.VIR_MIGRATE_UNDEFINE_SOURCE | \
                            libvirt.VIR_MIGRATE_COMPRESSED | \
                            libvirt.VIR_MIGRATE_PEER2PEER | \
                            libvirt.VIR_MIGRATE_AUTO_CONVERGE

                        root = ET.fromstring(self.guest.XMLDesc())

                        if msg['storage_mode'] == StorageMode.local.value:
                            # 需要把磁盘存放路径加入到两边宿主机的存储池中
                            # 不然将会报 no storage pool with matching target path '/opt/Images' 错误
                            flags |= libvirt.VIR_MIGRATE_NON_SHARED_DISK
                            flags |= libvirt.VIR_MIGRATE_LIVE

                            if not self.guest.isActive():
                                _log = u'非共享存储不支持离线迁移。'
                                logger.error(_log)
                                log_emit.error(_log)
                                raise

                            if self.init_ssh_client(hostname=msg['duri'].split('/')[2], user='root'):
                                for _disk in root.findall('devices/disk'):
                                    _file_path = _disk.find('source').get('file')
                                    disk_info = Disk.disk_info_by_local(image_path=_file_path)
                                    disk_size = disk_info['virtual-size']
                                    stdin, stdout, stderr = self.ssh_client.exec_command(
                                        ' '.join(['qemu-img', 'create', '-f', 'qcow2', _file_path, str(disk_size)]))

                                    for line in stdout:
                                        logger.info(line)
                                        log_emit.info(line)

                                    for line in stderr:
                                        logger.error(line)
                                        log_emit.error(line)

                        elif msg['storage_mode'] in [StorageMode.shared_mount.value, StorageMode.ceph.value,
                                                     StorageMode.glusterfs.value]:
                            if self.guest.isActive():
                                flags |= libvirt.VIR_MIGRATE_LIVE
                                flags |= libvirt.VIR_MIGRATE_TUNNELLED

                            else:
                                flags |= libvirt.VIR_MIGRATE_OFFLINE

                        if self.guest.migrateToURI(duri=msg['duri'], flags=flags) == 0:
                            if msg['storage_mode'] == StorageMode.local.value:
                                for _disk in root.findall('devices/disk'):
                                    _file_path = _disk.find('source').get('file')
                                    if _file_path is not None:
                                        os.remove(_file_path)

                        else:
                            raise

                elif msg['_object'] == 'disk':
                    if msg['action'] == 'create':

                        if msg['storage_mode'] == StorageMode.glusterfs.value:
                            Guest.dfs_volume = msg['dfs_volume']
                            Guest.init_gfapi()

                            if not Disk.make_qemu_image_by_glusterfs(gf=Guest.gf, dfs_volume=msg['dfs_volume'],
                                                                     image_path=msg['image_path'], size=msg['size']):
                                raise

                        elif msg['storage_mode'] in [StorageMode.local.value, StorageMode.shared_mount.value]:
                            if not Disk.make_qemu_image_by_local(image_path=msg['image_path'], size=msg['size']):
                                raise

                    elif msg['action'] == 'delete':

                        if msg['storage_mode'] == StorageMode.glusterfs.value:
                            Guest.dfs_volume = msg['dfs_volume']
                            Guest.init_gfapi()

                            if Disk.delete_qemu_image_by_glusterfs(gf=Guest.gf, image_path=msg['image_path']) \
                                    is not None:
                                raise

                        elif msg['storage_mode'] in [StorageMode.local.value, StorageMode.shared_mount.value]:
                            if Disk.delete_qemu_image_by_local(image_path=msg['image_path']) is not None:
                                raise

                    elif msg['action'] == 'resize':

                        if 'size' not in msg:
                            _log = u'添加磁盘缺少 disk 或 disk["size"] 参数'
                            raise KeyError(_log)

                        used = False

                        if msg['guest_uuid'].__len__() == 36:
                            used = True

                        if used:
                            self.refresh_guest_mapping()

                            if msg['guest_uuid'] not in self.guest_mapping_by_uuid:

                                if config['DEBUG']:
                                    _log = u' '.join([u'uuid', msg['uuid'], u'在宿主机', self.hostname, u'中未找到.'])
                                    logger.debug(_log)
                                    log_emit.debug(_log)

                                raise

                            self.guest = self.guest_mapping_by_uuid[msg['guest_uuid']]
                            if not isinstance(self.guest, libvirt.virDomain):
                                raise

                        # 在线磁盘扩容
                        if used and self.guest.isActive():
                                if 'device_node' not in msg:
                                    _log = u'添加磁盘缺少 disk 或 disk["device_node|size"] 参数'
                                    raise KeyError(_log)

                                # 磁盘大小默认单位为KB，乘以两个 1024，使其单位达到GB
                                msg['size'] = int(msg['size']) * 1024 * 1024

                                if self.guest.blockResize(disk=msg['device_node'], size=msg['size']) != 0:
                                    raise

                        # 离线磁盘扩容
                        else:
                            if not all([key in msg for key in ['storage_mode', 'dfs_volume', 'image_path']]):
                                _log = u'添加磁盘缺少 disk 或 disk["storage_mode|dfs_volume|image_path|size"] 参数'
                                raise KeyError(_log)

                            if msg['storage_mode'] == StorageMode.glusterfs.value:
                                if not Disk.resize_qemu_image_by_glusterfs(dfs_volume=msg['dfs_volume'],
                                                                           image_path=msg['image_path'],
                                                                           size=msg['size']):
                                    raise

                            elif msg['storage_mode'] in [StorageMode.local.value, StorageMode.shared_mount.value]:
                                if not Disk.resize_qemu_image_by_local(image_path=msg['image_path'], size=msg['size']):
                                    raise

                else:
                    _log = u'未支持的 _object：' + msg['_object']
                    logger.error(_log)
                    log_emit.error(_log)

                response_emit.success(_object=msg['_object'], action=msg['action'], uuid=msg['uuid'],
                                      data=extend_data, passback_parameters=msg.get('passback_parameters'))

            except:
                logger.error(traceback.format_exc())
                log_emit.error(traceback.format_exc())
                response_emit.failure(_object=msg['_object'], action=msg.get('action'), uuid=msg.get('uuid'),
                                      passback_parameters=msg.get('passback_parameters'))

    @staticmethod
    def guest_creating_progress_report_engine():
        """
        Guest 创建进度上报引擎
        """
        list_creating_guest = list()
        template_size = dict()

        while True:
            if Utils.exit_flag:
                print 'Thread guest_creating_progress_report_engine say bye-bye'
                return

            # noinspection PyBroadException
            try:
                try:
                    payload = q_creating_guest.get(timeout=1)
                    list_creating_guest.append(payload)
                    q_creating_guest.task_done()
                except Queue.Empty as e:
                    pass

                for i, guest in enumerate(list_creating_guest):

                    template_path = guest['template_path']
                    progress = 0

                    if guest['storage_mode'] in [StorageMode.ceph.value, StorageMode.glusterfs.value]:
                        if guest['storage_mode'] == StorageMode.glusterfs.value:
                            if template_path not in template_size:
                                Guest.dfs_volume = guest['dfs_volume']
                                Guest.init_gfapi()

                                template_size[template_path] = float(Guest.gf.getsize(template_path))

                            system_image_size = Guest.gf.getsize(guest['system_image_path'])
                            progress = system_image_size / template_size[template_path]

                    elif guest['storage_mode'] in [StorageMode.local.value, StorageMode.shared_mount.value]:
                        if template_path not in template_size:
                            template_size[template_path] = float(os.path.getsize(template_path))

                        system_image_size = os.path.getsize(guest['system_image_path'])
                        progress = system_image_size / template_size[template_path]

                    else:
                        del list_creating_guest[i]
                        log = u' '.join([u'UUID: ', guest['uuid'], u'未支持的存储模式: ', str(guest['storage_mode'])])
                        logger.error(log)
                        log_emit.error(log)

                    guest_event_emit.creating(uuid=guest['uuid'], progress=int(progress * 90))

                    if progress == 1:
                        del list_creating_guest[i]

            except:
                logger.error(traceback.format_exc())
                log_emit.error(traceback.format_exc())

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
                if config['DEBUG']:
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

            if config['DEBUG']:
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

            if config['DEBUG']:
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

