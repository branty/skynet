#  Copyright  2017 EasyStack, Inc
#  Author: Branty<jun.wang@easystack.cn>

import logging
from logging.config import fileConfig
import os

from skynet.exceptions import LogConfigurationNotFound
from skynet.common import CONF

cfg_file = CONF()
log_dir = cfg_file.get_option('log', 'config_dir', "/etc/skynet/")
log_file = cfg_file.get_option('log', 'config_file', "logging_config.conf")


def init_log():
    log_config_path = os.path.join(log_dir, log_file)
    try:
        fileConfig(log_config_path)
    except Exception:
        msg = "Please configure correctly and be sure file log path exists!"
        raise LogConfigurationNotFound(msg)
    else:
        logger = logging.getLogger()
        logger.debug('Start initializing SKYNET log...')
