#!/usr/bin/env python
# -*- coding: utf-8 -*-


import os
import errno


__author__ = 'James Iter'
__date__ = '2017/11/18'
__contact__ = 'james.iter.cn@gmail.com'
__copyright__ = '(c) 2017 by James Iter.'


class PidFile(object):
    """
    Manage a PID file.
    """

    def __init__(self, file_name):
        self.file_name = file_name
        self.pid = None

    def create(self, pid):
        old_pid = self.validate()
        if old_pid:
            if old_pid == os.getpid():
                return
            msg = "Already running on PID %s (or pid file '%s' is stale)"
            raise RuntimeError(msg % (old_pid, self.file_name))

        self.pid = pid

        # Write pidfile
        pid_file_dir = os.path.dirname(self.file_name)
        if pid_file_dir and not os.path.isdir(pid_file_dir):
            raise RuntimeError("%s doesn't exist. Can't create pidfile." % pid_file_dir)

        if not os.path.isdir(pid_file_dir):
            os.makedirs(pid_file_dir, 0755)

        with open(file=self.file_name, mode='w') as f:
            f.write(pid)

        # set permissions to -rw-r--r--
        os.chmod(self.file_name, 420)

    def unlink(self):
        """ delete pidfile"""
        try:
            with open(self.file_name, "r") as f:
                pid1 = int(f.read() or 0)

            if pid1 == self.pid:
                os.unlink(self.file_name)
        except:
            pass

    def validate(self):
        """ Validate pidfile and make it stale if needed"""
        if not self.file_name:
            return
        try:
            with open(self.file_name, "r") as f:
                try:
                    wpid = int(f.read())
                except ValueError:
                    return

                try:
                    os.kill(wpid, 0)
                    return wpid
                except OSError as e:
                    if e.args[0] == errno.EPERM:
                        return wpid
                    if e.args[0] == errno.ESRCH:
                        return
                    raise
        except IOError as e:
            if e.args[0] == errno.ENOENT:
                return
            raise

