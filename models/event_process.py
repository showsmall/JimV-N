#!/usr/bin/env python
# -*- coding: utf-8 -*-


import libvirt

from models.event_loop import vir_event_loop_poll_start
from models.initialize import guest_event_emit, logger
from models import Guest


__author__ = 'James Iter'
__date__ = '2017/6/15'
__contact__ = 'james.iter.cn@gmail.com'
__copyright__ = '(c) 2017 by James Iter.'


class EventProcess(object):
    conn = None
    guest_callbacks = list()

    VIR_DOMAIN_EVENT_SHUTDOWN_GUEST = 1
    VIR_DOMAIN_EVENT_SHUTDOWN_HOST = 2

    def __init__(self):
        pass

    @classmethod
    def guest_event_callback(cls, conn, guest, event, detail, opaque):

        if not isinstance(guest, libvirt.virDomain):
            # 跳过已经不再本宿主机的 guest
            return

        if event == libvirt.VIR_DOMAIN_EVENT_STOPPED and detail == libvirt.VIR_DOMAIN_EVENT_STOPPED_MIGRATED:
            # Guest 从本宿主机迁出完成后不做状态通知
            return

        Guest.guest_state_report(guest=guest)

        if event == libvirt.VIR_DOMAIN_EVENT_DEFINED:
            if detail == libvirt.VIR_DOMAIN_EVENT_DEFINED_ADDED:
                # 创建出一个 Guest 后被触发
                pass
            elif detail == libvirt.VIR_DOMAIN_EVENT_DEFINED_UPDATED:
                # 更新 Guest 配置后被触发
                pass
            elif detail == libvirt.VIR_DOMAIN_EVENT_DEFINED_RENAMED:
                # 变更 Guest 名称，待测试。猜测为 Guest 变更为新名称时触发
                pass
            elif detail == libvirt.VIR_DOMAIN_EVENT_DEFINED_FROM_SNAPSHOT:
                # Config was restored from a snapshot 待测试。猜测为，依照一个 Guest 快照的当前配置，创建一个新的  Guest
                pass
            else:
                pass

        elif event == libvirt.VIR_DOMAIN_EVENT_UNDEFINED:
            if detail == libvirt.VIR_DOMAIN_EVENT_UNDEFINED_REMOVED:
                # 删除一个 Guest 定义
                pass
            elif detail == libvirt.VIR_DOMAIN_EVENT_UNDEFINED_RENAMED:
                # 变更 Guest 名称，待测试。猜测为 Guest 旧名称消失时触发
                pass
            else:
                pass

        elif event == libvirt.VIR_DOMAIN_EVENT_STARTED:
            if detail == libvirt.VIR_DOMAIN_EVENT_STARTED_BOOTED:
                # 正常启动
                pass
            elif detail == libvirt.VIR_DOMAIN_EVENT_STARTED_MIGRATED:
                # Guest 从另一个宿主机迁入时触发
                pass
            elif detail == libvirt.VIR_DOMAIN_EVENT_STARTED_RESTORED:
                # 从一个状态文件中恢复 Guest
                pass
            elif detail == libvirt.VIR_DOMAIN_EVENT_STARTED_FROM_SNAPSHOT:
                # 从快照中恢复 Guest 时触发
                pass
            elif detail == libvirt.VIR_DOMAIN_EVENT_STARTED_WAKEUP:
                # 唤醒时触发，待测试。
                pass
            else:
                pass

        elif event == libvirt.VIR_DOMAIN_EVENT_SUSPENDED:
            if detail == libvirt.VIR_DOMAIN_EVENT_SUSPENDED_PAUSED:
                # 管理员暂停 Guest 时触发
                pass
            elif detail == libvirt.VIR_DOMAIN_EVENT_SUSPENDED_MIGRATED:
                # 为了在线迁移，临时暂停当前准备迁出的 Guest 时触发
                pass
            elif detail == libvirt.VIR_DOMAIN_EVENT_SUSPENDED_IOERROR:
                # 磁盘 IO 错误时，被暂停时触发，待测试
                pass
            elif detail == libvirt.VIR_DOMAIN_EVENT_SUSPENDED_WATCHDOG:
                # 触发看门狗时触发，待测试
                pass
            elif detail == libvirt.VIR_DOMAIN_EVENT_SUSPENDED_RESTORED:
                # 从暂停的 Guest 状态文件恢复时触发
                pass
            elif detail == libvirt.VIR_DOMAIN_EVENT_SUSPENDED_FROM_SNAPSHOT:
                # 从暂停的 Guest 快照恢复时触发
                pass
            elif detail == libvirt.VIR_DOMAIN_EVENT_SUSPENDED_API_ERROR:
                # 调用 libvirt API 失败后触发
                pass
            elif detail == libvirt.VIR_DOMAIN_EVENT_SUSPENDED_POSTCOPY:
                # 以 post-copy 模式迁移 Guest，被暂停时触发
                pass
            elif detail == libvirt.VIR_DOMAIN_EVENT_SUSPENDED_POSTCOPY_FAILED:
                # post-copy 模式迁移失败时触发
                pass
            else:
                pass

        elif event == libvirt.VIR_DOMAIN_EVENT_RESUMED:
            if detail == libvirt.VIR_DOMAIN_EVENT_RESUMED_UNPAUSED:
                # 取消暂停，正常恢复时触发
                pass
            elif detail == libvirt.VIR_DOMAIN_EVENT_RESUMED_MIGRATED:
                # Guest 迁移的目标宿主机，迁移完成时触发
                pass
            elif detail == libvirt.VIR_DOMAIN_EVENT_RESUMED_FROM_SNAPSHOT:
                # 从快照恢复时触发
                pass
            elif detail == libvirt.VIR_DOMAIN_EVENT_RESUMED_POSTCOPY:
                # 恢复，但迁移任然在 post-copy 模式下进行，待测试
                pass
            else:
                pass

        elif event == libvirt.VIR_DOMAIN_EVENT_STOPPED:
            if detail == libvirt.VIR_DOMAIN_EVENT_STOPPED_SHUTDOWN:
                # 正常关机时触发
                pass
            elif detail == libvirt.VIR_DOMAIN_EVENT_STOPPED_DESTROYED:
                # 从宿主机中强行断开 Guest 电源时触发
                pass
            elif detail == libvirt.VIR_DOMAIN_EVENT_STOPPED_CRASHED:
                # Guest 崩溃时触发
                pass
            elif detail == libvirt.VIR_DOMAIN_EVENT_STOPPED_MIGRATED:
                # Guest 从本宿主机迁出完成后触发
                pass
            elif detail == libvirt.VIR_DOMAIN_EVENT_STOPPED_SAVED:
                # 保存 Guest 为状态文件后触发
                pass
            elif detail == libvirt.VIR_DOMAIN_EVENT_STOPPED_FAILED:
                # 宿主机上的模拟器或管理器失败时触发
                pass
            elif detail == libvirt.VIR_DOMAIN_EVENT_STOPPED_FROM_SNAPSHOT:
                # 加载完离线快照后触发，待测试
                pass

        elif event == libvirt.VIR_DOMAIN_EVENT_SHUTDOWN:
            if detail == libvirt.VIR_DOMAIN_EVENT_SHUTDOWN_FINISHED:
                # Guest 正常关机后触发
                pass
            elif detail == cls.VIR_DOMAIN_EVENT_SHUTDOWN_GUEST:
                # Guest 自己触发关机信号后触发(即，此时硬件还运行着，系统已经被关闭。有别于 poweroff)，待测试
                pass
            elif detail == cls.VIR_DOMAIN_EVENT_SHUTDOWN_HOST:
                # 从宿主机通过信号方式关闭 Guest 后触发
                pass
            else:
                pass

        elif event == libvirt.VIR_DOMAIN_EVENT_PMSUSPENDED:
            if detail == libvirt.VIR_DOMAIN_EVENT_PMSUSPENDED_MEMORY:
                # Guest 的内存被电源管理器暂停
                pass
            elif detail == libvirt.VIR_DOMAIN_EVENT_PMSUSPENDED_DISK:
                # Guest 的磁盘被电源管理器暂停
                pass
            else:
                pass

        elif event == libvirt.VIR_DOMAIN_EVENT_CRASHED:
            if detail == libvirt.VIR_DOMAIN_EVENT_CRASHED_PANICKED:
                # Guest 奔溃时触发
                pass
            else:
                pass

        else:
            pass

    @staticmethod
    def guest_event_migration_iteration_callback(conn, guest, iteration, opaque):
        try:
            migrate_info = dict()
            migrate_info['type'], migrate_info['time_elapsed'], migrate_info['time_remaining'], \
                migrate_info['data_total'], migrate_info['data_processed'], migrate_info['data_remaining'], \
                migrate_info['mem_total'], migrate_info['mem_processed'], migrate_info['mem_remaining'], \
                migrate_info['file_total'], migrate_info['file_processed'], migrate_info['file_remaining'] = \
                guest.jobInfo()

            guest_event_emit.migrating(uuid=guest.UUIDString(), migrating_info=migrate_info)

        except libvirt.libvirtError as e:
            pass

    @staticmethod
    def guest_event_device_added_callback(conn, guest, dev, opaque):
        Guest.update_xml(guest=guest)

    @staticmethod
    def guest_event_device_removed_callback(conn, guest, dev, opaque):
        Guest.update_xml(guest=guest)

    @classmethod
    def guest_event_register(cls):
        cls.conn = libvirt.open()
        cls.conn.domainEventRegister(cls.guest_event_callback, None)

        # 参考地址：https://libvirt.org/html/libvirt-libvirt-domain.html#virDomainEventID
        cls.guest_callbacks.append(cls.conn.domainEventRegisterAny(
            None, libvirt.VIR_DOMAIN_EVENT_ID_MIGRATION_ITERATION,
            cls.guest_event_migration_iteration_callback, None))

        cls.guest_callbacks.append(cls.conn.domainEventRegisterAny(
            None, libvirt.VIR_DOMAIN_EVENT_ID_DEVICE_ADDED,
            cls.guest_event_device_added_callback, None))

        cls.guest_callbacks.append(cls.conn.domainEventRegisterAny(
            None, libvirt.VIR_DOMAIN_EVENT_ID_DEVICE_REMOVED,
            cls.guest_event_device_removed_callback, None))

    @classmethod
    def guest_event_deregister(cls):
        cls.conn.domainEventDeregister(cls.guest_event_callback)
        for eid in cls.guest_callbacks:
            cls.conn.domainEventDeregisterAny(eid)


