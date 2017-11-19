#!/usr/bin/env python
# -*- coding: utf-8 -*-


import logging
import multiprocessing
from logging.handlers import TimedRotatingFileHandler
import os
import sys
import json
import getopt
import redis
import jimit as ji
import Queue
import errno

from jimvn_exception import PathNotExist
from utils import LogEmit, GuestEventEmit, ResponseEmit, HostEventEmit
from utils import CollectionPerformanceEmit, HostCollectionPerformanceEmit


__author__ = 'James Iter'
__date__ = '2017/3/12'
__contact__ = 'james.iter.cn@gmail.com'
__copyright__ = '(c) 2017 by James Iter.'


class Init(object):

    config = {
        'config_file': '/etc/jimvn.conf',
        'log_cycle': 'D',
        'instruction_channel': 'C:Instruction',
        'downstream_queue': 'Q:Downstream',
        'upstream_queue': 'Q:Upstream',
        'DEBUG': False,
        'daemon': True,
        'pidfile': '/run/jimv/jimvn.pid'
    }

    @classmethod
    def load_config(cls):

        def usage():
            print "Usage:%s [-c] [--config]" % sys.argv[0]

        opts = None
        try:
            opts, args = getopt.getopt(sys.argv[1:], 'hc:',
                                       ['help', 'config='])
        except getopt.GetoptError as e:
            print str(e)
            usage()
            exit(e.message.__len__())

        for k, v in opts:
            if k in ("-h", "--help"):
                usage()
                exit()
            elif k in ("-c", "--config"):
                cls.config['config_file'] = v
            else:
                print "unhandled option"

        if not os.path.isfile(cls.config['config_file']):
            raise PathNotExist(u'配置文件不存在, 请配置 --> ', cls.config['config_file'])

        with open(cls.config['config_file'], 'r') as f:
            cls.config.update(json.load(f))

        return cls.config

    @classmethod
    def init_logger(cls):
        log_dir = os.path.dirname(cls.config['log_file_path'])
        if not os.path.isdir(log_dir):
            try:
                os.makedirs(log_dir, 0755)
            except OSError as e:
                # 如果配置文件中的日志目录无写入权限，则调整日志路径到本项目目录下
                if e.errno != errno.EACCES:
                    raise

                cls.config['log_file_path'] = './logs/jimvc.log'
                log_dir = os.path.dirname(cls.config['log_file_path'])

                if not os.path.isdir(log_dir):
                    os.makedirs(log_dir, 0755)

                print u'日志路径自动调整为 ' + cls.config['log_file_path']

        _logger = logging.getLogger(cls.config['log_file_path'])

        if cls.config['DEBUG']:
            _logger.setLevel(logging.DEBUG)
        else:
            _logger.setLevel(logging.INFO)

        fh = TimedRotatingFileHandler(cls.config['log_file_path'], when=cls.config['log_cycle'],
                                      interval=1, backupCount=7)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s - %(lineno)s - %(message)s')
        fh.setFormatter(formatter)
        _logger.addHandler(fh)
        return _logger

    @classmethod
    def redis_init_conn(cls):
        """
          * Added TCP Keep-alive support by passing use the socket_keepalive=True
            option. Finer grain control can be achieved using the
            socket_keepalive_options option which expects a dictionary with any of
            the keys (socket.TCP_KEEPIDLE, socket.TCP_KEEPCNT, socket.TCP_KEEPINTVL)
            and integers for values. Thanks Yossi Gottlieb.
            TCP_KEEPDILE 设置连接上如果没有数据发送的话，多久后发送keepalive探测分组，单位是秒
            TCP_KEEPINTVL 前后两次探测之间的时间间隔，单位是秒
            TCP_KEEPCNT 关闭一个非活跃连接之前的最大重试次数
        """
        import socket
        _r = redis.StrictRedis(host=cls.config.get('redis_host', '127.0.0.1'), port=cls.config.get('redis_port', 6379),
                               db=cls.config.get('redis_dbid', 0), decode_responses=True, socket_timeout=5,
                               socket_connect_timeout=5, socket_keepalive=True,
                               socket_keepalive_options={socket.TCP_KEEPIDLE: 2, socket.TCP_KEEPINTVL: 5,
                                                         socket.TCP_KEEPCNT: 10},
                               retry_on_timeout=True)

        try:
            _r.ping()
        except redis.exceptions.ResponseError as e:
            logger.warn(e.message)
            _r = redis.StrictRedis(
                host=cls.config.get('redis_host', '127.0.0.1'), port=cls.config.get('redis_port', 6379),
                db=cls.config.get('redis_dbid', 0), password=cls.config.get('redis_password', ''),
                decode_responses=True, socket_timeout=5, socket_connect_timeout=5, socket_keepalive=True,
                socket_keepalive_options={socket.TCP_KEEPIDLE: 2, socket.TCP_KEEPINTVL: 5,
                                          socket.TCP_KEEPCNT: 10},
                retry_on_timeout=True)

        _r.client_setname(ji.Common.get_hostname())
        return _r


config = Init.load_config()
logger = Init.init_logger()

r = Init.redis_init_conn()
assert isinstance(r, redis.StrictRedis)
q_creating_guest = Queue.Queue()

host_cpu_count = multiprocessing.cpu_count()

# 创建 JimV-N 向 JimV-C 推送事件消息的发射器
log_emit = LogEmit()
log_emit.upstream_queue = config['upstream_queue']
log_emit.r = r

guest_event_emit = GuestEventEmit()
guest_event_emit.upstream_queue = config['upstream_queue']
guest_event_emit.r = r

host_event_emit = HostEventEmit()
host_event_emit.upstream_queue = config['upstream_queue']
host_event_emit.r = r

response_emit = ResponseEmit()
response_emit.upstream_queue = config['upstream_queue']
response_emit.r = r

collection_performance_emit = CollectionPerformanceEmit()
collection_performance_emit.upstream_queue = config['upstream_queue']
collection_performance_emit.r = r

host_collection_performance_emit = HostCollectionPerformanceEmit()
host_collection_performance_emit.upstream_queue = config['upstream_queue']
host_collection_performance_emit.r = r

thread_status = dict()

