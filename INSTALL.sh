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
export GLOBAL_CONFIG_KEY='global_config'
export VM_NETWORK_KEY='vm_network'
export VM_NETWORK_MANAGE_KEY='vm_manage_network'

ARGS=`getopt -o h --long redis_host:,redis_password:,help -n 'INSTALL.sh' -- "$@"`

eval set -- "${ARGS}"

while true
do
    case "$1" in
        --redis_host)
            export REDIS_HOST=$2
            shift 2
            ;;
        --redis_password)
            export REDIS_PSWD=$2
            shift 2
            ;;
        -h|--help)
            echo 'INSTALL.sh [-h|--help] {--redis_host,--redis_password}'
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
            echo "System version must greater than or equal to 7, We found ${VERSION_ID}."
	        exit 1
        fi
        ;;
    *)
        echo "${ID} is unknown, Please to be installed manually."
	    exit 1
        ;;
    esac

    if [ `egrep -c '(vmx|svm)' /proc/cpuinfo` -eq 0 ]; then
        echo "We need CPU support the feature vmx or svm, this haven't."
        exit 1
    fi

    if [ ! ${REDIS_HOST} ] || [ ${REDIS_HOST} -eq 0 ]; then
        echo "You be need to specified argument '--redis_host'"
        exit 1
    fi

    if [ ! ${REDIS_PSWD} ]; then
        export REDIS_PSWD=''
    fi

    if [ `redis-cli -h ${REDIS_HOST} -a ${REDIS_PSWD} --raw EXISTS ${GLOBAL_CONFIG_KEY}` -eq 0 ]; then
        echo "You need to initialize JimV-C before."
        exit 1
    fi

    if [ `redis-cli -h ${REDIS_HOST} -a ${REDIS_PSWD} --raw HEXISTS ${GLOBAL_CONFIG_KEY} ${VM_NETWORK_KEY}` -eq 0 ]; then
        echo "You need to initialize JimV-C before, we not found key ${VM_NETWORK_KEY}."
        exit 1
    else
        export VM_NETWORK=`redis-cli -h ${REDIS_HOST} -a ${REDIS_PSWD} --raw HGET ${GLOBAL_CONFIG_KEY} ${VM_NETWORK_KEY}`
    fi

    if [ `redis-cli -h ${REDIS_HOST} -a ${REDIS_PSWD} --raw HEXISTS ${GLOBAL_CONFIG_KEY} ${VM_NETWORK_MANAGE_KEY}` -eq 0 ]; then
        echo "You need to initialize JimV-C before, we not found key ${VM_NETWORK_MANAGE_KEY}."
        exit 1
    else
        export VM_NETWORK_MANAGE=`redis-cli -h ${REDIS_HOST} -a ${REDIS_PSWD} --raw HGET ${GLOBAL_CONFIG_KEY} ${VM_NETWORK_MANAGE_KEY}`
    fi
}

function prepare() {
    yum install epel-release python2-pip git redis net-tools -y
    pip install --upgrade pip -i ${PYPI}

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
    # 代替语句 ifconfig | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1'
    export SERVER_IP=`hostname -I`
    export SERVER_NETMASK=`ifconfig | grep ${SERVER_IP} | grep -Eo 'netmask ?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*'`
    export GATEWAY=`route -n | grep '^0.0.0.0' | awk '{ print $2; }'`
    export DNS1=`nslookup 127.0.0.1 | grep Server | grep -Eo '([0-9]*\.){3}[0-9]*'`
    export NIC=`ifconfig | grep ${SERVER_IP} -B 1 | head -1 | cut -d ':' -f 1`

    # 参考地址: https://access.redhat.com/documentation/zh-cn/red_hat_enterprise_linux/7/html/networking_guide/
cat > /etc/sysconfig/network-scripts/ifcfg-${VM_NETWORK} << "EOF"
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

cat > /etc/sysconfig/network-scripts/ifcfg-bond0 << "EOF"
DEVICE=bond0
NAME=bond0
TYPE=Bond
BRIDGE=${VM_NETWORK}
BONDING_MASTER=yes
ONBOOT=yes
BOOTPROTO=none
BONDING_OPTS="mode=balance-alb xmit_hash_policy=layer3+4"
EOF

cat > /etc/sysconfig/network-scripts/ifcfg-${NIC} << "EOF"
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

cat > /etc/libvirt/qemu/networks/${VM_NETWORK}.xml << "EOF"
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

function clone_and_checkout_JimV-N() {
    git clone https://github.com/jamesiter/JimV-N.git /opt/JimV-C
}

function install_dependencies_library() {
    # 安装 JimV-N 所需扩展库
    pip install -r /opt/JimV-N/requirements.txt -i ${PYPI}
}

function generate_config_file() {
    cp -v /opt/JimV-N/jimvn.conf /etc/jimvn.conf
    sed -i "s/\"redis_host\".*$/\"redis_host\": \"${REDIS_HOST}\",/" /etc/jimvn.conf
    sed -i "s/\"redis_password\".*$/\"redis_password\": \"${REDIS_PSWD}\",/" /etc/jimvn.conf
}

function display_summary_information() {
    echo
    echo "=== Summary information"
    echo "======================="
    echo
    echo "Now, you can run JimV-N use command '/opt/JimV-N/startup.sh'."
}

function deploy() {
    check_precondition
    prepare
    install_libvirt
    handle_ssh_client_config
    handle_net_bonding_bridge
    create_network_bridge_in_libvirt
    start_libvirtd
    clone_and_checkout_JimV-N
    install_dependencies_library
    generate_config_file
    display_summary_information
}

deploy

