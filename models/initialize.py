#!/usr/bin/env python
# -*- coding: utf-8 -*-


import logging
from logging.handlers import TimedRotatingFileHandler
import os
import sys
import json
import getopt
import redis

from jimvn_exception import PathNotExist
from utils import LogEmit, GuestEventEmit, ResponseEmit, HostEventEmit, CollectionPerformanceEmit

__author__ = 'James Iter'
__date__ = '2017/3/12'
__contact__ = 'james.iter.cn@gmail.com'
__copyright__ = '(c) 2017 by James Iter.'


class Init(object):

    config = {
        'config_file': '/etc/jimvn.conf'
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
        cls.config['log_file_base'] = '/'.join([sys.path[0], cls.config['log_file_dir'], 'log'])
        log_dir = os.path.dirname(cls.config['log_file_base'])
        if not os.path.isdir(log_dir):
            os.makedirs(log_dir, 0755)

        process_title = 'JimV-N'
        log_file_path = '.'.join([cls.config['log_file_base'], process_title])
        _logger = logging.getLogger(log_file_path)

        if cls.config['debug']:
            cls.config['DEBUG'] = True
            _logger.setLevel(logging.DEBUG)
        else:
            cls.config['DEBUG'] = False
            _logger.setLevel(logging.INFO)

        fh = TimedRotatingFileHandler(log_file_path, when=cls.config['log_cycle'], interval=1, backupCount=7)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s - %(lineno)s - %(message)s')
        fh.setFormatter(formatter)
        _logger.addHandler(fh)
        return _logger

    @classmethod
    def redis_init_conn(cls):
        _r = redis.StrictRedis(host=cls.config.get('redis_host', '127.0.0.1'), port=cls.config.get('redis_port', 6379),
                               db=cls.config.get('redis_dbid', 0), decode_responses=True)

        try:
            _r.ping()
        except redis.exceptions.ResponseError as e:
            logger.warn(e.message)
            _r = redis.StrictRedis(host=cls.config.get('redis_host', '127.0.0.1'), port=cls.config.get('redis_port', 6379),
                                   db=cls.config.get('redis_dbid', 0), password=cls.config.get('redis_password', ''),
                                   decode_responses=True)

        return _r


config = Init.load_config()
logger = Init.init_logger()
r = Init.redis_init_conn()
assert isinstance(r, redis.StrictRedis)

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
