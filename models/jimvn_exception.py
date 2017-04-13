#!/usr/bin/env python
# -*- coding: utf-8 -*-

__author__ = 'James Iter'
__date__ = '2017/3/12'
__contact__ = 'james.iter.cn@gmail.com'
__copyright__ = '(c) 2017 by James Iter.'


class JimVNException(Exception):
    pass


class PathExist(JimVNException):
    pass


class PathNotExist(JimVNException):
    pass


class ConnFailed(JimVNException):
    pass


class AlreadyUsed(JimVNException):
    pass


class DomainNotExist(JimVNException):
    pass


class CommandExecFailed(JimVNException):
    pass

