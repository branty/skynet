#    Copyright  2017 EasyStack, Inc
#    Authors: Branty <jun.wang@easystack.cn>

import logging
import json
import time

from oslo_config import cfg
from oslo_log import log
from oslo_service import service as os_service

from skynet import common
from skynet.common import CONF as skynet_CONF
from skynet.mongodb import Connection as MONGO_CONN
from skynet import pipline
from skynet import zabbix
from skynet.zabbix import ZabbixController


LOG = logging.getLogger(__name__)
CONF = None
conf = skynet_CONF()


class AgentManager(os_service.Service):
    def __init__(self, conf, zabbix_hdl, pollers_mg):
        super(AgentManager, self).__init__()
        self.conf = conf
        self.zabbix_hdl = zabbix_hdl
        self.pollers_mg = pollers_mg

    def interval_task(self, pollers, meter_source):
        """
        @param poller: class PollerSource instance
        """
        fake_openstack_hostname = self.conf.get_option(
            "skynet",
            "fake_openstack_hostname")
        zabbix_data = list()
        LOG.info("Staring to poll metrics: %s", [i.name for i in pollers])
        start = time.time()
        try:
            for poller in pollers:
                method = poller.method
                LOG.info("Polling pollster %s in the context of %s"
                         % (poller.name, meter_source))
                payload = getattr(self.zabbix_hdl, method)()
                data = {
                    "host": fake_openstack_hostname,
                    "key": poller.name,
                    "value": json.dumps(payload)
                }
                zabbix_data.append(data)
            zabbix.clear()
            self.zabbix_hdl.socket_to_zabbix(zabbix_data)
        except AttributeError as e:
            LOG.error(e.message)
        except Exception as e:
            LOG.error(e.message)
        end = time.time()
        LOG.info("Total seconds spends: %s", (end - start))

    def start(self):
        # Set shuffle time before polling task if necessary
        # default: 0.5
        # Should better make it configurable
        delay_polling_time = 0.5
        # Add timer tasks into this list, return all timer tasks if necessary
        poller_timers = list()
        for source in self.pollers_mg.sources:
            poller_timers.append(self.tg.add_timer(
                source.interval,
                self.interval_task,
                initial_delay=delay_polling_time,
                pollers=source.pollers,
                meter_source=source.name))
        LOG.info("********* Success to start Skynet Polling Task **********")

    def test_run_once(self):
        for source in self.pollers_mg.sources:
            self.interval_task(source.pollers)


def prepare_service():
    global CONF
    CONF = cfg.ConfigOpts()
    log.register_options(CONF)
    log.set_defaults(default_log_levels=CONF.default_log_levels)
    skynet_conf = common.get_skynet_conf()
    CONF(project='skynet', validate_default_values=True,
         default_config_files=[skynet_conf])
    log.setup(CONF, 'skynet')
    mongo_conn = MONGO_CONN(conf)
    zabbix_hdl = ZabbixController(conf, mongo_conn)
    pollers_manager = pipline.setup_polling()
    return (zabbix_hdl, pollers_manager)


def main():
    # Before starting service,prepare to check something ready.
    zabbix_handler, pollers_manager = prepare_service()
    LOG.info("********** Starting Skynet Polling Task **********")
    os_service.launch(CONF, AgentManager(conf, zabbix_handler,
                                         pollers_manager)).wait()
