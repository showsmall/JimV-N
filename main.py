#!/usr/bin/env python
# -*- coding: utf-8 -*-


import threading
import traceback
import signal

import time

from models.event_process import EventProcess
from models.initialize import logger
from models import Host
from models import Utils


__author__ = 'James Iter'
__date__ = '2017/3/12'
__contact__ = 'james.iter.cn@gmail.com'
__copyright__ = '(c) 2017 by James Iter.'


if __name__ == '__main__':

    # noinspection PyBroadException
    try:

        EventProcess.guest_event_register()

        signal.signal(signal.SIGTERM, Utils.signal_handle)
        signal.signal(signal.SIGINT, Utils.signal_handle)

        threads = []

        host_use_for_downstream_queue_process_engine = Host()
        host_use_for_downstream_queue_process_engine.init_conn()
        t_ = threading.Thread(target=host_use_for_downstream_queue_process_engine.downstream_queue_process_engine,
                              args=())
        threads.append(t_)

        host_use_for_guest_operate_engine = Host()
        host_use_for_guest_operate_engine.init_conn()
        t_ = threading.Thread(target=host_use_for_guest_operate_engine.guest_operate_engine, args=())
        threads.append(t_)

        host_use_for_host_state_report_engine = Host()
        host_use_for_host_state_report_engine.init_conn()
        t_ = threading.Thread(target=host_use_for_host_state_report_engine.state_report_engine, args=())
        threads.append(t_)

        host_use_for_collection_performance_process_engine = Host()
        host_use_for_collection_performance_process_engine.init_conn()
        t_ = threading.Thread(
            target=host_use_for_collection_performance_process_engine.collection_performance_process_engine, args=())
        threads.append(t_)

        host_use_for_host_state_report_engine.refresh_guest_state()

        for t in threads:
            t.start()

        while True:
            if Utils.exit_flag:
                # 主线程即将结束
                EventProcess.guest_event_deregister()
                break
            time.sleep(1)

        # 等待子线程结束
        for t in threads:
            t.join()

        print 'Main say bye-bye!'

    except:
        logger.error(traceback.format_exc())
        exit(-1)

