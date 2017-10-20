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

### 安装基础设施
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
```

`CentOS`
``` bash
yum install libvirt libvirt-devel python-devel libguestfs -y
yum install libguestfs libguestfs-{devel,tools,xfs,winsupport,rescue} python-libguestfs -y
pip install --upgrade pip -i https://mirrors.aliyun.com/pypi/simple/
pip install -r /opt/JimV-N/requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

## 服务器间实现SSH-KEY互通(为热迁移做铺垫)
### 关闭 SSH 服务器端 Key 校验
``` bash
sed -i 's@.*StrictHostKeyChecking.*@StrictHostKeyChecking no@' /etc/ssh/ssh_config
```

### 生成空密码的SSH使用的密钥对
``` bash
# 一路回车
ssh-keygen
```

### 部署公钥到集群中的其它计算节点上(便于迁移)
``` bash
# 对所有目标主机(包括自身)
ssh-copy-id [*].jimvn.jimv
```

### 复制私钥到集群中的其它计算节点上
``` bash
DHOST=vmhost02.jimvn.jimv; scp ~/.ssh/id_rsa $DHOST:~/.ssh/id_rsa; ssh $DHOST 'chmod 0400 ~/.ssh/id_rsa'; unse
t DHOST
```

## 实现虚拟网络环境
### 安装虚拟网络环境所需工具
`Gentoo`
``` bash
# net-misc/ifenslave            系统网络接口绑定工具
# net-misc/bridge-utils         brctl 以太网桥接工具
# sys-apps/usermode-utilities   tunctl TUN/TAP 设备创建&管理工具
emerge net-misc/ifenslave net-misc/bridge-utils sys-apps/usermode-utilities
```

### 虚拟网络环境配置
`Gentoo`
https://wiki.gentoo.org/wiki/Handbook:X86/Full/Networking#Bonding
`/etc/conf.d/net`
``` bash
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
```

`CentOS`
https://access.redhat.com/documentation/zh-cn/red_hat_enterprise_linux/7/html/networking_guide/
`/etc/sysconfig/network-scripts/ifcfg-br0`
``` bash
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
```

`/etc/sysconfig/network-scripts/ifcfg-bond0`
``` bash
DEVICE=bond0
NAME=bond0
TYPE=Bond
BRIDGE=br0
BONDING_MASTER=yes
ONBOOT=yes
BOOTPROTO=none
BONDING_OPTS="mode=balance-alb xmit_hash_policy=layer3+4"
```

`/etc/sysconfig/network-scripts/ifcfg-eth0`
``` bash
DEVICE=eth0
NAME=eth0
TYPE=Ethernet
BOOTPROTO=none
ONBOOT=yes
MASTER=bond0
SLAVE=yes
```

`/etc/sysconfig/network-scripts/ifcfg-eth1`
``` bash
DEVICE=eth1
NAME=eth1
TYPE=Ethernet
BOOTPROTO=none
ONBOOT=yes
MASTER=bond0
SLAVE=yes
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

### 配置 Libvirtd
`Gentoo`


`CentOS`
``` bash
systemctl stop dnsmasq
systemctl disable dnsmasq
rm -f /etc/libvirt/qemu/networks/default.xml /etc/libvirt/qemu/networks/autostart/default.xml
```

### 启动服务
`Gentoo`
``` bash
/etc/init.d/libvirtd start
```

`CentOS`
``` bash
systemctl start libvirtd
```

### 修改配置文件
配置文件路径：`/etc/jimvn.conf`
<br>
**提示：**
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

