Skynet Polling Agent
========================

Support metrics
--------
* openstack.hosts.top5.memory;
* openstack.hosts.top5.cpu;
* openstack.hosts.total;
* openstack.hosts.memory.usage;
* openstack.hosts.cpu.util;
* openstack.vms.top5.memory;
* openstack.vms.top5.cpu;
* openstack.vms.total;
* openstack.vms.cpu.utils;
* openstack.vms.memory.usage;
* openstack.alarms.total

Requirements
------------
All requirement writted in requirement.txt

Usage
-----
Assuming that all the above requirements are met, the skynet can be run with several steps:

1. Create skynet user:

        $ adduser --shell /sbin/nologin --home /var/lib/skynet skynet

2. Create the related dirs, and modify the policy of those dirs:

        $ mkdir -p /var/log/skynet/
        $ mkdir -p /etc/skynet/
        $ chown -R skynet:skynet /etc/skynet /var/log/skynet/

3. Build skynet source code into python path:

        $ git clone ssh://branty@review.easystack.cn:29418/easystack/skynet;git checkout stable/4.0
        $ cd skynet;python setup.py install
        $ cp etc/* /etc/skynet/;chown -R skynet:skynet /etc/skynet

4. Create a file named "/usr/lib/systemd/system/skynet-polling.service"(use vi/vim as your preference),
   add the following content in this file:

    [Unit]
    Description=Time task for polling/create new metrics into zabbix
    After=syslog.target network.target

    [Service]
    Type=simple
    User=skynet
    ExecStart=/usr/bin/skynet_polling --logfile /var/log/skynet/skynet.log
    Restart=on-failure
    
    [Install]
    WantedBy=multi-user.target

5. Register skynet-polling as a startup service and then start it:

        $ systemctl enable skynet-polling
        $ systemctl start skynet-polling.service;systemctl status skynet-polling.service

HA Support
----------

1. Enter crm shell interface:
        $ crm config
        $ edit

2. Add the following contents to proper location:
        primitive p_skynet-polling ocf:es:skynet-polling \
            op monitor interval=20 timeout=30 \
            op start interval=0 timeout=360 \
            op stop interval=0 timeout=360 \
            meta resource-stickiness=1 target-role=Started
        ...
        location p_skynet-polling-on-node-1.domain.tld p_skynet-polling 100: node-1.domain.tld
        location p_skynet-polling-on-node-2.domain.tld p_skynet-polling 100: node-2.domain.tld
        location p_skynet-polling-on-node-3.domain.tld p_skynet-polling 100: node-3.domain.tld

Source
------


Copyright
---------

Copyright (c) 2017 EasyStack Inc.

This project has been developed for the demand of EasyStack Inc., Ltd by Branty<jun.wang@easystack.cn>.

