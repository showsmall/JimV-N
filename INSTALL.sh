#!/usr/bin/env bash
#
# JimV-N
#
# Copyright (C) 2017 JimV <james.iter.cn@gmail.com>
#
# Author: James Iter <james.iter.cn@gmail.com>
#
#  This script will help you to automation installed JimV-N.
#

export PYPI='https://mirrors.aliyun.com/pypi/simple/'
export JIMVN_REPOSITORY_URL='https://raw.githubusercontent.com/jamesiter/JimV-N'
export EDITION='master'
export GLOBAL_CONFIG_KEY='H:GlobalConfig'
export COMPUTE_NODES_HOSTNAME_KEY='S:ComputeNodesHostname'
export VM_NETWORK_KEY='vm_network'
export VM_NETWORK_MANAGE_KEY='vm_manage_network'


ARGS=`getopt -o h --long redis_host:,redis_password:,redis_port:,help -n 'INSTALL.sh' -- "$@"`

eval set -- "${ARGS}"

while true
do
    case "$1" in
        --redis_host)
            export REDIS_HOST=$2
            shift 2
            ;;
        --redis_port)
            export REDIS_PORT=$2
            shift 2
            ;;
        --redis_password)
            export REDIS_PSWD=$2
            shift 2
            ;;
        -h|--help)
            echo 'INSTALL.sh [-h|--help] {--redis_host,--redis_password,--redis_port}'
            echo '如果忘记了 redis_password, redis_port 信息，可以在 JimV-C 的 /etc/jimvn.conf 文件中获得。'
            exit 0
            ;;
        --)
            shift
            break
            ;;
        *)
            echo "Internal error!"
            exit 1
            ;;
    esac
done

function check_precondition() {
    source /etc/os-release
    case ${ID} in
    centos|fedora|rhel)
        if [ ${VERSION_ID} -lt 7 ]; then
            echo "系统版本号必须大于等于 7，检测到当前的系统版本号为 ${VERSION_ID}."
	        exit 1
        fi
        ;;
    *)
        echo "系统发行版 ${ID} 未被支持，请手动完成安装。"
	    exit 1
        ;;
    esac

    yum install epel-release -y
    yum install redis -y
    yum install python2-pip git net-tools bind-utils gcc -y
    pip install --upgrade pip -i ${PYPI}

    if [ `egrep -c '(vmx|svm)' /proc/cpuinfo` -eq 0 ]; then
        echo "需要 CPU 支持 vmx 或 svm, 该 CPU 不支持。"
        exit 1
    fi

    if [ ! ${REDIS_HOST} ] || [ ${#REDIS_HOST} -eq 0 ]; then
        echo "你需要指定参数 '--redis_host'"
        exit 1
    fi

    if [ ! ${REDIS_PORT} ]; then
        export REDIS_PORT='6379'
    fi

    if [ ! ${REDIS_PSWD} ]; then
        export REDIS_PSWD=''
    fi

    # 代替语句 ifconfig | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1'
    export SERVER_IP=`hostname -I`
    export SERVER_NETMASK=`ifconfig | grep ${SERVER_IP} | grep -Eo 'netmask ?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*'`
    export GATEWAY=`route -n | grep '^0.0.0.0' | awk '{ print $2; }'`
    export DNS1=`nslookup 127.0.0.1 | grep Server | grep -Eo '([0-9]*\.){3}[0-9]*'`
    export NIC=`ifconfig | grep ${SERVER_IP} -B 1 | head -1 | cut -d ':' -f 1`
    export HOST_NAME=`grep ${SERVER_IP} /etc/hosts | awk '{ print $2; }'`

    if [ 'x_'${HOST_NAME} = 'x_' ]; then
        echo "计算节点 IP 地址未在 /etc/hosts 文件中被发现。请完整安装、初始化 JimV-C 后，再安装 JimV-N。"
        exit 1
    fi

    REDIS_RESPONSE='x_'`redis-cli -h ${REDIS_HOST} -a ${REDIS_PSWD} -p ${REDIS_PORT} --raw ping`

    if [ ${REDIS_RESPONSE} != 'x_PONG' ]; then
        echo "Redis 连接失败，请检查参数 --redis_host, --redis_password, --redis_port 是否正确。"
        exit 1
    fi

    REDIS_RESPONSE='x_'`redis-cli -h ${REDIS_HOST} -a ${REDIS_PSWD} -p ${REDIS_PORT} --raw EXISTS ${GLOBAL_CONFIG_KEY}`
    if [ ${REDIS_RESPONSE} = 'x_0' ]; then
        echo "安装 JimV-N 之前，你需要先初始化 JimV-C。"
        exit 1
    fi

    REDIS_RESPONSE='x_'`redis-cli -h ${REDIS_HOST} -a ${REDIS_PSWD} -p ${REDIS_PORT} --raw HEXISTS ${GLOBAL_CONFIG_KEY} ${VM_NETWORK_KEY}`
    if [ ${REDIS_RESPONSE} = 'x_0' ]; then
        echo "未在 JimV-C 的配置中发现 key ${VM_NETWORK_KEY}，请重新配置 JimV-C。"
        exit 1
    else
        export VM_NETWORK=`redis-cli -h ${REDIS_HOST} -a ${REDIS_PSWD} -p ${REDIS_PORT} --raw HGET ${GLOBAL_CONFIG_KEY} ${VM_NETWORK_KEY}`
    fi

    REDIS_RESPONSE='x_'`redis-cli -h ${REDIS_HOST} -a ${REDIS_PSWD} -p ${REDIS_PORT} --raw HEXISTS ${GLOBAL_CONFIG_KEY} ${VM_NETWORK_MANAGE_KEY}`
    if [ ${REDIS_RESPONSE} = 'x_0' ]; then
        echo "未在 JimV-C 的配置中发现 key ${VM_NETWORK_MANAGE_KEY}，请重新配置 JimV-C。"
        exit 1
    else
        export VM_NETWORK_MANAGE=`redis-cli -h ${REDIS_HOST} -a ${REDIS_PSWD} -p ${REDIS_PORT} --raw HGET ${GLOBAL_CONFIG_KEY} ${VM_NETWORK_MANAGE_KEY}`
    fi

    REDIS_RESPONSE='x_'`redis-cli -h ${REDIS_HOST} -a ${REDIS_PSWD} -p ${REDIS_PORT} --raw SISMEMBER ${COMPUTE_NODES_HOSTNAME_KEY} ${HOST_NAME}`
    if [ ${REDIS_RESPONSE} != 'x_0' ]; then
        echo "计算节点 ${HOST_NAME} 已存在，请重新指定 --hostname 的值，或清除冲突的计算节点。"
        exit 1
    else
        hostname ${HOST_NAME}
        echo ${HOST_NAME} > /etc/hostname
    fi
}

function set_ntp() {
    timedatectl set-timezone Asia/Shanghai
    timedatectl set-ntp true
    timedatectl status
}

function custom_repository_origin() {
    mv /etc/yum.repos.d/CentOS-Base.repo /etc/yum.repos.d/CentOS-Base.repo.backup
    mv /etc/yum.repos.d/epel.repo /etc/yum.repos.d/epel.repo.backup
    mv /etc/yum.repos.d/epel-testing.repo /etc/yum.repos.d/epel-testing.repo.backup
    curl -o /etc/yum.repos.d/CentOS-Base.repo http://mirrors.aliyun.com/repo/Centos-7.repo
    curl -o /etc/yum.repos.d/epel.repo http://mirrors.aliyun.com/repo/epel-7.repo
    yum clean all
    rm -rf /var/cache/yum
    yum makecache
}

function clear_up_environment() {
    systemctl stop firewalld
    systemctl disable firewalld
    systemctl stop NetworkManager
    systemctl disable NetworkManager

    sed -i 's@SELINUX=enforcing@SELINUX=disabled@g' /etc/sysconfig/selinux
    sed -i 's@SELINUX=enforcing@SELINUX=disabled@g' /etc/selinux/config
    setenforce 0
}

function install_libvirt() {
    # 安装 libvirt
    yum install libvirt libvirt-devel python-devel libguestfs -y
    yum install libguestfs libguestfs-{devel,tools,xfs,winsupport,rescue} python-libguestfs -y
}

function handle_ssh_client_config() {
    # 关闭 SSH 服务器端 Key 校验
    sed -i 's@.*StrictHostKeyChecking.*@StrictHostKeyChecking no@' /etc/ssh/ssh_config
}

function handle_net_bonding_bridge() {
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

cat > /etc/sysconfig/network-scripts/ifcfg-${NIC} << EOF
DEVICE=${NIC}
NAME=${NIC}
TYPE=Ethernet
BOOTPROTO=none
ONBOOT=yes
MASTER=bond0
SLAVE=yes
EOF

    /etc/init.d/network restart
}

function create_network_bridge_in_libvirt() {

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
}

function start_libvirtd() {
    systemctl stop dnsmasq
    systemctl disable dnsmasq
    systemctl enable libvirtd
    systemctl start libvirtd
    virsh net-destroy default; virsh net-undefine default
}

function clone_and_checkout_JimVN() {
    git clone https://github.com/jamesiter/JimV-N.git /opt/JimV-N
    if [ ! $? -eq 0 ]; then
        echo '克隆 JimV-N 失败，请检查网络可用性。'
        exit 1
    fi
}

function install_dependencies_library() {
    # 安装 JimV-N 所需扩展库
    pip install -r /opt/JimV-N/requirements.txt -i ${PYPI}
}

function generate_config_file() {
    cp -v /opt/JimV-N/jimvn.conf /etc/jimvn.conf
    sed -i "s/\"redis_host\".*$/\"redis_host\": \"${REDIS_HOST}\",/" /etc/jimvn.conf
    sed -i "s/\"redis_password\".*$/\"redis_password\": \"${REDIS_PSWD}\",/" /etc/jimvn.conf
    sed -i "s/\"redis_port\".*$/\"redis_port\": \"${REDIS_PORT}\",/" /etc/jimvn.conf
}

function display_summary_information() {
    echo
    echo "=== 信息汇总"
    echo "==========="
    echo
    echo "现在可以通过命令 'cd /opt/JimV-N && ./startup.sh' 启动运行 JimV-N。"
}

function deploy() {
    check_precondition
    set_ntp
    custom_repository_origin
    clear_up_environment
    install_libvirt
    handle_ssh_client_config
    handle_net_bonding_bridge
    create_network_bridge_in_libvirt
    start_libvirtd
    clone_and_checkout_JimVN
    install_dependencies_library
    generate_config_file
    display_summary_information
}

deploy

