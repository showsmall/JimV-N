# JimV-N
[![License](https://img.shields.io/badge/License-GPL3-blue.svg)](http://www.gnu.org/licenses/gpl-3.0.html)
[![Python versions](https://img.shields.io/badge/Python-2.7.10-blue.svg)](https://www.python.org)


## 项目描述
> JimV 的计算节点。


## 未来计划
>
* 参照 VMWare ESXi，做一个安装、 配置的 Shell 控制台


## 安装
### 克隆 JimV-N 项目
``` bash
git clone https://github.com/jamesiter/JimV-N.git
```

### 安装所需库
`Gentoo`
``` bash
# 创建 python 虚拟环境
virtualenv --system-site-packages ~/venv
# 导入 python 虚拟环境
source ~/venv/bin/activate
# 安装 JimV-N 所需扩展库
pip install --upgrade pip -i https://mirrors.aliyun.com/pypi/simple/
pip install -r /opt/JimV-N/requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
emerge libguestfs
```

`CentOS`
``` bash
yum install libvirt libvirt-devel python-devel libguestfs -y
yum install libguestfs libguestfs-{devel,tools,xfs,winsupport,rescue} python-libguestfs -y
pip install --upgrade pip -i https://mirrors.aliyun.com/pypi/simple/
pip install -r /opt/JimV-N/requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```


### 修改配置文件
配置文件路径：`/etc/jimvn.conf`
<br>
**提示：**
> 下表中凸显的配置项，需要用户根据自己的环境手动修改。

|配置项|默认值|说明|
|:--|:--|:--|
|**`redis_host`**|localhost|Redis 数据库地址|
|**`redis_port`**|6379|Redis 数据库端口|
|**`redis_password`**| |Redis 数据库密码|
|redis_dbid|0|选择的 Redis 数据库|
|debug|false|调试模式|
|log_file_dir|logs|日志文件存放目录|
|log_cycle|D|日志轮转周期|
|vm_create_queue|Q:VMCreate|创建虚拟机的队列名称|
|host_event_report_queue|Q:HostEvent|JimV-N 上抛事件消息到 JimV-C 的渠道队列名称|


### 启动服务
``` bash
# 启动 JimV-N
/opt/JimV-N/main.py
```


## 问题反馈
[提交Bug](https://github.com/jamesiter/JimV-N/issues)
<br>
技术交流 QQ 群: 377907881


## 项目成员
<pre>
姓名:    James Iter
E-Mail: james.iter.cn@gmail.com
</pre>

