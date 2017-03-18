#!/usr/bin/env python
# -*- coding: utf-8 -*-


import os
import guestfs

from initialize import logger, emit
from utils import Utils


__author__ = 'James Iter'
__date__ = '2017/3/1'
__contact__ = 'james.iter.cn@gmail.com'
__copyright__ = '(c) 2017 by James Iter.'


class Guest(object):
    def __init__(self, **kwargs):
        self.uuid = kwargs.get('uuid', '')
        # 模板镜像路径
        self.template_path = kwargs.get('template_path', '')
        # 不提供链接克隆(完整克隆，后期可以在模板目录，直接删除模板文件。从理论上讲，基于完整克隆的 Guest 读写速度、快照都应该快于链接克隆。)
        # self.clone = True
        # Guest 系统镜像路径
        self.system_image_path = kwargs.get('system_image_path', '')
        self.base_dir = os.path.dirname(self.system_image_path)
        # Guest 数据磁盘
        self.data_disks = kwargs.get('data_disks', list())
        self.writes = kwargs.get('writes', list())
        self.xml = kwargs.get('xml', None)
        self.g = guestfs.GuestFS(python_return_dict=True)

    def generate_base_dir(self):
        if not os.path.isdir(self.base_dir):
            os.makedirs(self.base_dir, 0755)

        return True

    def generate_system_image(self):
        if not os.path.isfile(self.template_path):
            log = u'模板不存在: ' + self.template_path
            logger.error(msg=log)
            emit.error(msg=log)
            return False

        cmd = ' '.join(['cp', self.template_path, self.system_image_path])
        exit_status, output = Utils.shell_cmd(cmd=cmd)
        if exit_status != 0:
            log = u'命令执行退出异常: ' + str(output)
            logger.error(msg=log)
            emit.error(msg=log)
            return False

        return True

    def generate_disk_image(self):
        # 最多3块数据盘
        for data_disk in self.data_disks[:3]:

            cmd = ' '.join(['/usr/bin/qemu-img', 'create', '-f', 'qcow2', data_disk['path'], data_disk['size']])
            exit_status, output = Utils.shell_cmd(cmd)

            if exit_status != 0:
                log = u'命令执行退出异常: ' + str(output)
                logger.error(msg=log)
                emit.error(msg=log)
                return False

        return True

    def init_config(self):
        self.g.add_drive(filename=self.system_image_path)
        self.g.launch()
        self.g.mount(self.g.inspect_os(), '/')

        for item in self.writes:
            self.g.write(item['path'], item['content'])

        self.g.shutdown()
        self.g.close()

