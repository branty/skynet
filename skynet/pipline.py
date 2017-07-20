#  Copyright  2017 EasyStack, Inc
#  Author: Branty<jun.wang@easystack.cn>

import logging
import os

import yaml

from skynet.common import CONF
from skynet.exceptions import PipelineException, PipelineFileNotFound


LOG = logging.getLogger(__name__)
conf = CONF()

PIPLINE_DIRS = [
    ".",
    "../etc/",
    "/etc/skynet"
]


class Poller(object):
    """Represents a source of samples or events."""

    def __init__(self, cfg):
        try:
            self.name = cfg['name']
            self.method = cfg['method']
        except KeyError as err:
            msg = "Required field %s not specified, %s" % (err.args[0], cfg)
            LOG.error(msg)
            raise PipelineException(msg)

    def __str__(self):
        return "Poller name: %s, Poller method: %s" % (self.name, self.method)


class PollerSource(object):
    """Represents a source of samples.

    In effect it is a set of pollsters samples for a set of matching meters.
    Each source encapsulates meter name matching, polling interval
    determination, optional resource enumeration or discovery, and mapping
    to one or more sinks for publication.
    """

    def __init__(self, cfg):
        # Support 'counters' for backward compatibility
        self.cfg = cfg
        self.name = cfg['name']
        self.meters = cfg.get('meters', [])
        self.pollers = None
        try:
            self.interval = int(cfg.get('interval', 600))
        except ValueError:
            msg = "Interval value should > 0 cfg: %s" % cfg
            LOG.error(msg)
            raise PipelineException(msg)
        if self.interval <= 0:
            msg = "Interval value should > 0 cfg: %s" % cfg
            LOG.error(msg)
            raise PipelineException(msg)
        self.check_pollers(self.meters)

    def get_interval(self):
        return self.interval

    def check_pollers(self, meters):
        pollers = set()
        for meter in meters:
            if meter['name'] in pollers:
                msg = "Duplicated source names: %s, cfg: %s" % (meter,
                                                                self.cfg)
                LOG.error(msg)
                raise PipelineException(msg)
            else:
                pollers.add(meter['name'])
        pollers.clear()
        for meter in meters:
            pollers.add(Poller(meter))
        self.pollers = pollers


class PollersManager(object):
    """Polling Manager

    Polling manager sets up polling according to config file.
    """

    def __init__(self, cfg):
        """Setup the polling according to config.

        The configuration is the sources half of the Pipeline Config.
        """
        self.sources = []
        if not ('sources' in cfg):
            msg = "Sources are required in %s" % cfg
            LOG.error(msg)
            raise PipelineException(msg)
        unique_names = set()
        for s in cfg.get('sources', []):
            name = s.get('name')
            if name in unique_names:
                raise PipelineException("Duplicated source names: %s" %
                                        name, self)
            else:
                unique_names.add(name)
                self.sources.append(PollerSource(s))
        unique_names.clear()


def _setup_polling_manager(cfg_file):
    LOG.debug("Polling config file: %s" % cfg_file)

    with open(cfg_file) as fap:
        data = fap.read()

    pipeline_cfg = yaml.safe_load(data)
    return PollersManager(pipeline_cfg)
    LOG.info("Polling config file %s: %s" % (cfg_file, data))


def setup_polling():
    """Setup polling manager according to yaml config file."""
    pipline = conf.get_option("skynet", "pipline_file", "skynet_pipline.yaml")
    pipline_file = None
    for f in PIPLINE_DIRS:
        f = os.path.abspath(os.path.join(f, pipline))
        if os.path.exists(f):
            pipline_file = f
            break
    if not pipline_file:
        msg = "Skynet pipline file is not Found"
        LOG.error(msg)
        raise PipelineFileNotFound(msg)
    return _setup_polling_manager(pipline_file)
