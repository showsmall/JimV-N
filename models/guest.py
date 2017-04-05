#!/usr/bin/env python
# -*- coding: utf-8 -*-


import guestfs
from gluster import gfapi

from initialize import logger, emit
from utils import Utils


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
        self.disks = kwargs.get('disks', None)
        self.writes = kwargs.get('writes', None)
        self.xml = kwargs.get('xml', None)
        self.guest_dir = None
        # Guest 系统镜像路径，不包含 glusterfs 卷标
        self.system_image_path = None
        self.g = guestfs.GuestFS(python_return_dict=True)

    @classmethod
    def init_gfapi(cls):
        cls.gf = gfapi.Volume('127.0.0.1', cls.glusterfs_volume)
        cls.gf.mount()

    def generate_guest_dir(self):
        self.guest_dir = '/'.join(['VMs', self.name])

        if not self.gf.isdir(self.guest_dir):
            self.gf.makedirs(self.guest_dir, 0755)

        return True

    def generate_system_image(self):
        if not self.gf.isfile(self.template_path):
            log = u'模板不存在: ' + self.template_path
            logger.error(msg=log)
            emit.error(msg=log)
            return False

        self.system_image_path = self.guest_dir + '/' + self.disks[0]['label'] + '.' + self.disks[0]['format']

        self.gf.copy(self.template_path, self.system_image_path)

        return True

    def generate_disk_image(self):
        # 最多3块数据盘
        for disk in self.disks[1:4]:

            disk_path = '/'.join(['gluster://127.0.0.1', self.glusterfs_volume, self.guest_dir,
                                  disk['label'] + '.' + disk['format']])

            cmd = ' '.join(['/usr/bin/qemu-img', 'create', '-f', 'qcow2', disk_path, disk['size'].__str__() + 'G'])
            exit_status, output = Utils.shell_cmd(cmd)

            if exit_status != 0:
                log = u'命令执行退出异常: ' + str(output)
                logger.error(msg=log)
                emit.error(msg=log)
                return False

        return True

    def init_config(self):
        self.g.add_drive(filename=self.glusterfs_volume + '/' + self.system_image_path, format=self.disks[0]['format'],
                         protocol='gluster', server=['127.0.0.1'])
        self.g.launch()
        self.g.mount(self.g.inspect_os()[0], '/')

        for item in self.writes:
            self.g.write(item['path'], item['content'])

        self.g.sh('echo "{user}:{password}" | chpasswd'.format(user='root', password=self.password))

        self.g.shutdown()
        self.g.close()

