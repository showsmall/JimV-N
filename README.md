[![License](https://img.shields.io/badge/License-GPL3-blue.svg)](http://www.gnu.org/licenses/gpl-3.0.html)
[![Python versions](https://img.shields.io/badge/Python-2.7.10-blue.svg)](https://www.python.org)

[TOC]: # "目录"

# 目录
- [项目描述](#项目描述)
- [未来计划](#未来计划)
- [部署](#部署)
    - [基础设施建设](#基础设施建设)
    - [服务器间实现SSH-KEY互通(为热迁移做铺垫)](#服务器间实现ssh-key互通为热迁移做铺垫)
    - [为虚拟化配置`绑定+桥接`的网络环境](#为虚拟化配置绑定桥接的网络环境)
    - [Libvirtd 中定义新网桥](#libvirtd-中定义新网桥)
    - [启动虚拟化网络](#启动虚拟化网络)
    - [启动服务](#启动服务)
    - [克隆 JimV-N 项目](#克隆-jimv-n-项目)
    - [修改配置文件](#修改配置文件)
    - [启动服务](#启动服务)
- [问题反馈](#问题反馈)
- [项目成员](#项目成员)



## 项目描述

> JimV 的计算节点。


## 未来计划

>* 参照 VMWare ESXi，做一个安装、 配置的 Shell 控制台


## 部署

### 基础设施建设

`Gentoo`

``` bash
# 安装 Qemu
USE="aio caps curl fdt filecaps jpeg ncurses nls pin-upstream-blobs png seccomp threads uuid vhost-net vnc xattr iscsi nfs spice ssh virtfs xfs" emerge app-emulation/qemu

# 安装 Libvirtd
USE="caps libvirtd macvtap nls qemu udev vepa iscsi nfs virt-network" emerge app-emulation/libvirt
 
# 安装 JimV-N 所需扩展库
pip install --upgrade pip -i https://mirrors.aliyun.com/pypi/simple/
pip install -r /opt/JimV-N/requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
emerge libguestfs
emerge screen
```

`CentOS`

``` bash
yum install libvirt libvirt-devel python-devel libguestfs -y
yum install libguestfs libguestfs-{devel,tools,xfs,winsupport,rescue} python-libguestfs -y
yum install screen -y
pip install --upgrade pip -i https://mirrors.aliyun.com/pypi/simple/
pip install -r /opt/JimV-N/requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

### 服务器间实现SSH-KEY互通(为热迁移做铺垫)

``` bash
# 关闭 SSH 服务器端 Key 校验
sed -i 's@.*StrictHostKeyChecking.*@StrictHostKeyChecking no@' /etc/ssh/ssh_config

# 生成空密码的SSH使用的密钥对
# 一路回车
ssh-keygen

# 分发公钥到集群中的其它计算节点上(便于迁移)
# 对所有目标主机(包括自身)
ssh-copy-id [*].jimvn.jimv

# 复制私钥到集群中的其它计算节点上
DHOST=[*].jimvn.jimv; scp ~/.ssh/id_rsa $DHOST:~/.ssh/id_rsa; ssh $DHOST 'chmod 0400 ~/.ssh/id_rsa'; unse
t DHOST
```

### 为虚拟化配置`绑定+桥接`的网络环境

`Gentoo`

``` bash
# 安装虚拟网络环境所需工具
# net-misc/ifenslave            系统网络接口绑定工具
# net-misc/bridge-utils         brctl 以太网桥接工具
# sys-apps/usermode-utilities   tunctl TUN/TAP 设备创建&管理工具
emerge net-misc/ifenslave net-misc/bridge-utils sys-apps/usermode-utilities

# 虚拟网络环境配置
# 参考地址: https://wiki.gentoo.org/wiki/Handbook:X86/Full/Networking#Bonding
cat > /etc/conf.d/net << "EOF"
config_eno1="null"
config_eno2="null"

slaves_bond0="eno1 eno2"
config_bond0="null"
# Pick a correct mode and additional configuration options which suit your needs
mode_bond0="balance-alb"
rc_need_bond0="net.eno1 net.eno2"

brctl_br0="stp off"
bridge_br0="bond0"
config_br0="10.10.1.254/20"
routes_br0="default via 10.10.15.254"
rc_need_br0="net.bond0"
EOF
```

`CentOS`

``` bash
# 参考地址: https://access.redhat.com/documentation/zh-cn/red_hat_enterprise_linux/7/html/networking_guide/
cat > /etc/sysconfig/network-scripts/ifcfg-br0 << "EOF"
DEVICE=br0
NAME=br0
TYPE=Bridge
BOOTPROTO=static
ONBOOT=yes
DELAY=0
IPADDR=10.10.6.16
NETMASK=255.255.240.0
GATEWAY=10.10.15.254
DNS1=223.5.5.5
DNS2=8.8.8.8
IPV6INIT=no
EOF

cat > /etc/sysconfig/network-scripts/ifcfg-bond0 << "EOF"
DEVICE=bond0
NAME=bond0
TYPE=Bond
BRIDGE=br0
BONDING_MASTER=yes
ONBOOT=yes
BOOTPROTO=none
BONDING_OPTS="mode=balance-alb xmit_hash_policy=layer3+4"
EOF

cat > /etc/sysconfig/network-scripts/ifcfg-eth0 << "EOF"
DEVICE=eth0
NAME=eth0
TYPE=Ethernet
BOOTPROTO=none
ONBOOT=yes
MASTER=bond0
SLAVE=yes
EOF

cat > /etc/sysconfig/network-scripts/ifcfg-eth1 << "EOF"
DEVICE=eth1
NAME=eth1
TYPE=Ethernet
BOOTPROTO=none
ONBOOT=yes
MASTER=bond0
SLAVE=yes
EOF
```

### Libvirtd 中定义新网桥

``` bash
cat > /etc/libvirt/qemu/networks/net-br0.xml << "EOF"
<network>
    <uuid>the_uuid</uuid>
    <name>net-br0</name>
    <forward mode="bridge"/>
    <bridge name="br0"/>
</network>
EOF
sed -i "s@the_uuid@`uuidgen`@" /etc/libvirt/qemu/networks/net-br0.xml

# 去除默认的 default 网络定义
rm -f /etc/libvirt/qemu/networks/default.xml /etc/libvirt/qemu/networks/autostart/default.xml

# 使其随服务自动创建
cd /etc/libvirt/qemu/networks/autostart/
ln -s ../net-br0.xml net-br0.xml
```

### 启动虚拟化网络

`Gentoo`

``` bash
ln -s /etc/init.d/net.lo /etc/init.d/net.eno1
ln -s /etc/init.d/net.lo /etc/init.d/net.eno2
ln -s /etc/init.d/net.lo /etc/init.d/net.bond1
ln -s /etc/init.d/net.lo /etc/init.d/net.br0
rc-update add net.br0 default
/etc/init.d/net.br0 start
```

`CentOS`

``` bash
/etc/init.d/network restart
```

### 启动服务

`Gentoo`

``` bash
rc-update del dnsmasq
rc-update add libvirtd
/etc/init.d/libvirtd start
```

`CentOS`

``` bash
systemctl stop dnsmasq
systemctl disable dnsmasq
systemctl enable libvirtd
systemctl start libvirtd
```

### 克隆 JimV-N 项目

``` bash
git clone https://github.com/jamesiter/JimV-N.git /opt/JimV-N
```

### 修改配置文件

配置文件的默认读取路径：`/etc/jimvn.conf`
``` bash
cp /opt/JimV-N/jimvn.conf /etc/jimvn.conf
```
<br> **提示：**
> 下表中凸显的配置项，需要用户根据自己的环境手动修改。

| 配置项                | 默认值                   | 说明               |
|:---------------------|:------------------------|:------------------|
| **`redis_host`**     | localhost               | Redis 数据库地址   |
| **`redis_port`**     | 6379                    | Redis 数据库端口   |
| **`redis_password`** |                         | Redis 数据库密码   |
| redis_dbid           | 0                       | 选择的 Redis 数据库 |
| DEBUG                | false                   | 调试模式           |
| log_file_path        | /var/log/jimv/jimvn.log | 日志文件存放目录    |


### 启动服务

``` bash
# 启动 JimV-N
screen -dmS JimV-N /usr/bin/python2.7 /opt/JimV-N/main.py
```


## 问题反馈

[提交Bug](https://github.com/jamesiter/JimV-N/issues) <br> 技术交流 QQ 群:
377907881


## 项目成员

<pre>
姓名:    James Iter
E-Mail: james.iter.cn@gmail.com
</pre>

