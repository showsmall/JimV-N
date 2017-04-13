#!/usr/bin/env python
# -*- coding: utf-8 -*-


import traceback
import thread
import signal
import time

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
        signal.signal(signal.SIGTERM, Utils.signal_handle)
        signal.signal(signal.SIGINT, Utils.signal_handle)

        host_use_for_create_guest_engine = Host()
        host_use_for_create_guest_engine.init_conn()
        thread.start_new_thread(host_use_for_create_guest_engine.create_guest_engine, ())
        Utils.thread_counter += 1

        host_use_for_guest_operate_engine = Host()
        host_use_for_guest_operate_engine.init_conn()
        thread.start_new_thread(host_use_for_guest_operate_engine.guest_operate_engine, ())
        Utils.thread_counter += 1

        while Utils.thread_counter > 0:
            time.sleep(1)

        print 'Main say bye-bye!'

    except:
        logger.error(traceback.format_exc())
        exit(-1)
