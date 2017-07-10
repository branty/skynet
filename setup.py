#!/usr/bin/env python
from setuptools import find_packages
from setuptools import setup

setup(
    name="skynet",
    version="1.0.0",
    author="Branty",
    author_email="jun.wang@easystack.cn",
    packages=find_packages(),
    scripts=['bin/skynet_polling'],
    url="www.easystack.cn",
    description="A Timer task for polling/creating new"
                "zabbix/openstack metrics into zabbix"
)
