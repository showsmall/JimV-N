# 手动安装


[TOC]: # "手动安装"

# 手动安装
- [[安装、初始化 JimV-C](https://github.com/jamesiter/JimV-C#%E5%AE%89%E8%A3%85)](#安装初始化-jimv-c)
- [开启 NTP 同步](#开启-ntp-同步)
- [安装必要软件](#安装必要软件)
- [声明全局变量](#声明全局变量)
- [环境检测](#环境检测)
- [整理环境](#整理环境)
- [安装 Libvirt](#安装-libvirt)
- [为虚拟化配置`绑定+桥接`的网络环境](#为虚拟化配置绑定桥接的网络环境)
- [Libvirtd 中定义新网桥](#libvirtd-中定义新网桥)
- [启动 Libvirtd 服务](#启动-libvirtd-服务)
- [克隆、签出 JimV-N 项目](#克隆签出-jimv-n-项目)
- [修改配置文件](#修改配置文件)
- [启动 JimV-N 服务](#启动-jimv-n-服务)


## [安装、初始化 JimV-C](https://github.com/jamesiter/JimV-C#%E5%AE%89%E8%A3%85)


## 开启 NTP 同步

``` bash
timedatectl set-timezone Asia/Shanghai
timedatectl set-ntp true
timedatectl status
```


## 安装必要软件

``` bash
yum install epel-release -y
yum install redis -y
yum install python2-pip git net-tools bind-utils gcc -y
```


## 声明全局变量

``` bash
export PYPI='https://mirrors.aliyun.com/pypi/simple/'
export JIMVN_REPOSITORY_URL='https://raw.githubusercontent.com/jamesiter/JimV-N'
export EDITION='master'
export GLOBAL_CONFIG_KEY='H:GlobalConfig'
export COMPUTE_NODES_HOSTNAME_KEY='S:ComputeNodesHostname'
export VM_NETWORK_KEY='vm_network'
export VM_NETWORK_MANAGE_KEY='vm_manage_network'

# 代替语句 ifconfig | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1'
export SERVER_IP=`hostname -I`
export SERVER_NETMASK=`ifconfig | grep ${SERVER_IP} | grep -Eo 'netmask ?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*'`
export GATEWAY=`route -n | grep '^0.0.0.0' | awk '{ print $2; }'`
export DNS1=`nslookup 127.0.0.1 | grep Server | grep -Eo '([0-9]*\.){3}[0-9]*'`
export NIC=`ifconfig | grep ${SERVER_IP} -B 1 | head -1 | cut -d ':' -f 1`
export HOST_NAME=`grep ${SERVER_IP} /etc/hosts | awk '{ print $2; }'`
export REDIS_HOST=`hostname`
export REDIS_PORT='6379'
export REDIS_PSWD=''

if [ ! ${REDIS_HOST} ] || [ ${#REDIS_HOST} -eq 0 ]; then
    echo "你需要指定参数 REDIS_HOST"
fi
```


## 环境检测

``` bash
if [ `egrep -c '(vmx|svm)' /proc/cpuinfo` -eq 0 ]; then
    echo "需要 CPU 支持 vmx 或 svm, 该 CPU 不支持。"
fi
if [ 'x_'${HOST_NAME} = 'x_' ]; then
    echo "计算节点 IP 地址未在 /etc/hosts 文件中被发现。请完整安装、初始化 JimV-C 后，再安装 JimV-N。"
fi

REDIS_RESPONSE='x_'`redis-cli -h ${REDIS_HOST} -a ${REDIS_PSWD} -p ${REDIS_PORT} --raw ping`

if [ ${REDIS_RESPONSE} != 'x_PONG' ]; then
    echo "Redis 连接失败，请检查全局变量 REDIS_HOST, REDIS_PSWD, REDIS_PORT 是否正确声明。"
fi

REDIS_RESPONSE='x_'`redis-cli -h ${REDIS_HOST} -a ${REDIS_PSWD} -p ${REDIS_PORT} --raw EXISTS ${GLOBAL_CONFIG_KEY}`
if [ ${REDIS_RESPONSE} = 'x_0' ]; then
    echo "安装 JimV-N 之前，你需要先初始化 JimV-C。"
fi

REDIS_RESPONSE='x_'`redis-cli -h ${REDIS_HOST} -a ${REDIS_PSWD} -p ${REDIS_PORT} --raw HEXISTS ${GLOBAL_CONFIG_KEY} ${VM_NETWORK_KEY}`
if [ ${REDIS_RESPONSE} = 'x_0' ]; then
    echo "未在 JimV-C 的配置中发现 key ${VM_NETWORK_KEY}，请重新配置 JimV-C。"
else
    export VM_NETWORK=`redis-cli -h ${REDIS_HOST} -a ${REDIS_PSWD} -p ${REDIS_PORT} --raw HGET ${GLOBAL_CONFIG_KEY} ${VM_NETWORK_KEY}`
fi

REDIS_RESPONSE='x_'`redis-cli -h ${REDIS_HOST} -a ${REDIS_PSWD} -p ${REDIS_PORT} --raw HEXISTS ${GLOBAL_CONFIG_KEY} ${VM_NETWORK_MANAGE_KEY}`
if [ ${REDIS_RESPONSE} = 'x_0' ]; then
    echo "未在 JimV-C 的配置中发现 key ${VM_NETWORK_MANAGE_KEY}，请重新配置 JimV-C。"
else
    export VM_NETWORK_MANAGE=`redis-cli -h ${REDIS_HOST} -a ${REDIS_PSWD} -p ${REDIS_PORT} --raw HGET ${GLOBAL_CONFIG_KEY} ${VM_NETWORK_MANAGE_KEY}`
fi

REDIS_RESPONSE='x_'`redis-cli -h ${REDIS_HOST} -a ${REDIS_PSWD} -p ${REDIS_PORT} --raw SISMEMBER ${COMPUTE_NODES_HOSTNAME_KEY} ${HOST_NAME}`
if [ ${REDIS_RESPONSE} != 'x_0' ]; then
    echo "计算节点 ${HOST_NAME} 已存在，请清除冲突的计算节点。"
else
    hostname ${HOST_NAME}
    echo ${HOST_NAME} > /etc/hostname
fi
```


## 整理环境

``` bash
systemctl stop firewalld
systemctl disable firewalld
systemctl stop NetworkManager
systemctl disable NetworkManager

sed -i 's@SELINUX=enforcing@SELINUX=disabled@g' /etc/sysconfig/selinux
sed -i 's@SELINUX=enforcing@SELINUX=disabled@g' /etc/selinux/config
setenforce 0
```


## 安装 Libvirt

``` bash
yum install libvirt libvirt-devel python-devel libguestfs -y
yum install libguestfs libguestfs-{devel,tools,xfs,winsupport,rescue} python-libguestfs -y
```


## 为虚拟化配置`绑定+桥接`的网络环境

``` bash
# 参考地址: https://access.redhat.com/documentation/zh-cn/red_hat_enterprise_linux/7/html/networking_guide/
cat > /etc/sysconfig/network-scripts/ifcfg-${VM_NETWORK} << EOF
DEVICE=${VM_NETWORK}
NAME=${VM_NETWORK}
TYPE=Bridge
BOOTPROTO=static
ONBOOT=yes
DELAY=0
IPADDR=${SERVER_IP}
NETMASK=${SERVER_NETMASK}
GATEWAY=${GATEWAY}
DNS1=${DNS1}
DNS2=8.8.8.8
IPV6INIT=no
EOF

cat > /etc/sysconfig/network-scripts/ifcfg-bond0 << EOF
DEVICE=bond0
NAME=bond0
TYPE=Bond
BRIDGE=${VM_NETWORK}
BONDING_MASTER=yes
ONBOOT=yes
BOOTPROTO=none
BONDING_OPTS="mode=balance-alb xmit_hash_policy=layer3+4"
EOF

# 如果有多个物理接口，其它接口配置与其类似，照猫画虎即可。
cat > /etc/sysconfig/network-scripts/ifcfg-${NIC} << EOF
DEVICE=${NIC}
NAME=${NIC}
TYPE=Ethernet
BOOTPROTO=none
ONBOOT=yes
MASTER=bond0
SLAVE=yes
EOF

# 重启网络使之生效
/etc/init.d/network restart
```


## Libvirtd 中定义新网桥

``` bash
cat > /etc/libvirt/qemu/networks/${VM_NETWORK}.xml << EOF
<network>
    <uuid>the_uuid</uuid>
    <name>${VM_NETWORK}</name>
    <forward mode="bridge"/>
    <bridge name="${VM_NETWORK}"/>
</network>
EOF

sed -i "s@the_uuid@`uuidgen`@" /etc/libvirt/qemu/networks/${VM_NETWORK}.xml

# 去除默认的 default 网络定义
rm -f /etc/libvirt/qemu/networks/default.xml /etc/libvirt/qemu/networks/autostart/default.xml

# 使其随服务自动创建
cd /etc/libvirt/qemu/networks/autostart/
ln -s ../${VM_NETWORK}.xml ${VM_NETWORK}.xml
```


## 启动 Libvirtd 服务

``` bash
systemctl stop dnsmasq
systemctl disable dnsmasq
systemctl enable libvirtd
systemctl start libvirtd
virsh net-destroy default && virsh net-undefine default
```


## 克隆、签出 JimV-N 项目

``` bash
# 更新到最新版本 pip
pip install --upgrade pip -i ${PYPI}

# 克隆并签出目标版本的 JimV-N
git clone https://github.com/jamesiter/JimV-N.git /opt/JimV-N

# 安装 JimV-N 所需扩展库
pip install -r /opt/JimV-N/requirements.txt -i ${PYPI}
```


## 修改配置文件

配置文件的默认读取路径：`/etc/jimvn.conf`
``` bash
cp -v /opt/JimV-N/jimvn.conf /etc/jimvn.conf
sed -i "s/\"redis_host\".*$/\"redis_host\": \"${REDIS_HOST}\",/" /etc/jimvn.conf
sed -i "s/\"redis_password\".*$/\"redis_password\": \"${REDIS_PSWD}\",/" /etc/jimvn.conf
sed -i "s/\"redis_port\".*$/\"redis_port\": \"${REDIS_PORT}\",/" /etc/jimvn.conf
```

**提示：**
> 下表中凸显的配置项，需要用户根据自己的环境手动修改。

| 配置项                | 默认值                   | 说明               |
|:---------------------|:------------------------|:------------------|
| **`redis_host`**     | localhost               | Redis 数据库地址   |
| **`redis_port`**     | 6379                    | Redis 数据库端口   |
| **`redis_password`** |                         | Redis 数据库密码   |
| redis_dbid           | 0                       | 选择的 Redis 数据库 |
| DEBUG                | false                   | 调试模式。区分大小写 |
| daemon               | false                   | 守护进程模式        |
| log_file_path        | /var/log/jimv/jimvn.log | 日志文件存放目录    |


## 启动 JimV-N 服务

``` bash
# 启动 JimV-N
cd /opt/JimV-N && ./startup.sh
```

