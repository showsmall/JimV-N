#!/usr/bin/env bash
#
# JimV-N
#
# Copyright (C) 2017 JimV <james.iter.cn@gmail.com>
#
# Author: James Iter <james.iter.cn@gmail.com>
#
#  Shutdown the JimV-N.

kill `cat /run/jimv/jimvn.pid`

sleep 1

# 服务结束后，/run/jimv/jimvn.pid 文件会被 JimV-N 自动清除。如果该文件还存在，则表示服务依然活着。
# 在执行本脚本 2 秒后，若服务任然活着，则强制结束。
if [ -f '/run/jimv/jimvn.pid' ]; then
    sleep 1

    if [ -f '/run/jimv/jimvn.pid' ]; then

        kill -9 `cat /run/jimv/jimvn.pid`
        rm -f /run/jimv/jimvn.pid
        echo 'JimV-N is forced to terminate.';
        exit 1

    fi
fi

if [ ! -e '/run/jimv/jimvn.pid' ]; then
    echo 'JimV-N stopped.';
fi

