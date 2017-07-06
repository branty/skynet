#    Copyright  2017 EasyStack, Inc
#    Authors: Branty <jun.wang@easystack.cn>

import ConfigParser
from ConfigParser import NoOptionError
from ConfigParser import NoSectionError
import json
import os
import sys

from ceilometerclient.v2 import client as clm_clientv20
from novaclient import client as nova_client

CONF_FILES = [
    os.path.abspath(os.path.join(os.path.dirname(__file__),
                                 ".",
                                 "skynet.conf")),
    os.path.abspath(os.path.join(os.path.dirname(__file__),
                                 "..",
                                 "etc/"
                                 "skynet.conf")),
    "/etc/skynet/skynet.conf"
]

MAPPING_DIRS = [
    ".",
    "/etc/skynet",
    "/etc/ceilometer"
]


def mapping_file_to_dict(mapping_file):
    """
    Parsing the JSON file according to configuration
    The configuration is supported as follows:
    {
     "period_colls":[60,300,3600]
     "60":{
           "meter_type":["cpu_util",
                         "disk.read.bytes.rate",
                         "..."]
            "mult_topology":[1,5,15,120,1440]
            "point_topology":[100,300,100,100,200]
          },
     "300":{
          },
     "3600":{
            "meter_type":["instance",
                          "volume",
                          "account"
                          ...
                        ]
            "mult_topology":[1,6,24]
            "point_topology":[100,200,200]
          }
    }
    """

    def _parse_json_file(j_file):
        with open(j_file) as f:
            return json.load(f)
    try:
        map_dict = _parse_json_file(mapping_file)
        if 'period_colls' in map_dict and \
                isinstance(map_dict['period_colls'], list):
            for i in map_dict['period_colls']:
                if str(i) not in map_dict.keys():
                    print ("Parsing mapping.json error, "
                           "because of not key %d in "
                           "the mapping file" % i)
                    raise
        else:
            print ("Parsing mapping.json error,"
                   "Maybe not key period_colls "
                   "in the mapping file or "
                   "the value of period_colls is not list")
            raise
        return map_dict
    except ValueError:
        raise
    except Exception:
        raise


def get_mapping_file(mp_file):
    found_file = None
    for d in MAPPING_DIRS:
        if os.path.exists(os.path.join(d, mp_file)):
            found_file = os.path.join(d, mp_file)
            break
    return found_file


def parse_metric_json(conf):
    global CACHE_MAPPING_FILE
    mapping_file = conf.get_option("mongodb", "mapping_file",
                                   default="mapping.json")
    if os.path.exists(mapping_file):
        CACHE_MAPPING_FILE = mapping_file_to_dict(mapping_file)
    else:
        CACHE_MAPPING_FILE = mapping_file_to_dict(
            get_mapping_file(mapping_file))
    if not CACHE_MAPPING_FILE:
        print("Can't find Metric mapping.json file, "
              "Make sure the mapping_file exist in those dirs:%s"
              % MAPPING_DIRS)
        raise
    return CACHE_MAPPING_FILE


"""
    A mapping.json example follows:
    {
     "period_colls":[60,300,3600]
     "60":{
           "meter_type":["cpu_util",
                         "disk.read.bytes.rate",
                         "..."]
            "mult_topology":[1,5,15,120,1440]
            "point_topology":[100,300,100,100,200]
          },
     "300":{
          },
     "3600":{
            "meter_type":["instance",
                          "volume",
                          "account"
                          ...
                        ]
            "mult_topology":[1,6,24]
            "point_topology":[100,200,200]
          }
    }
    30, 60, 3600 are sampling cycles of meters .
"""
CACHE_MAPPING_FILE = {}


def singleton(cls, *args, **kwags):
    """The basic singleton pattern

    Use __new__ when you need to control the creation of a new instance.

    Use __init__ when you need to control initialization of a new instance.

    How to use them,view  the following link:
        https://mail.python.org/pipermail/tutor/2008-April/061426.html

    When cls._instance is None, the class of Singleton is not  instantiated,
    instantiate this class and return.

    When cls._instance in not None, return the instance directly.

    Talk  is too cheap,show you the codes:

    class Singleton(object):
        def __new__(cls, *args,**kwargs):
            if not hasattr(cls,'_instance'):
               cls._instance = super(Singleton,cls).__new__(
                    cls,
                    *args,
                    **kwargs)
            return  cls._instance

    class Myclass(Singleton):
        a = 1
    one = Myclass()
    two = Myclass()
    # we can compare one with two, id(), == ,is
    two.a = 3
    print one.a  # output is : 3
    print id(one) == id(two) # outout is : True

    """
    instance = {}

    def _singleton():
        if cls not in instance:
            instance[cls] = cls(*args, **kwags)
        return instance[cls]
    return _singleton


@singleton
class CONF(object):
    def __init__(self, conf_file=None):
        """Method to parse skynet.conf
        """
        conf = None
        if conf_file and os.path.exists(conf_file):
            conf = conf_file
        if not conf:
            for f in CONF_FILES:
                if os.path.exists(f):
                    conf = f
                    break
        if not conf:
            print "Can'f find skynet script configuration file"
            sys.exit(1)
        self.conf = ConfigParser.SafeConfigParser()
        with open(f) as cnf:
            self.conf.readfp(cnf)

    def get_option(self, group, name, default=None, raw=False):
        value = None
        try:
            value = self.conf.get(group, name, raw=raw)
        except NoOptionError or NoSectionError:
            if default is not None:
                return default
            else:
                raise
        return value


class OpenStackClients(object):
    """Class for get some OpenStack clients
    """
    def __init__(self, conf):
        self.conf = conf
        self._nv_client = None
        self._clm_client = None

    @property
    def nv_client(self):
        if not self._nv_client:
            self._nv_client = self.get_novaclient()
        return self._nv_client

    @property
    def clm_client(self):
        if not self._clm_client:
            self._clm_client = self.get_ceilometerclient()
        return self._clm_client

    def get_novaclient(self):
        """Compute(nova) client
        """
        # Refactor(Branty)
        auth_url = self.conf.get_option(
            'keystone_authtoken',
            'auth_url')
        if auth_url.endswith('/v3'):
            auth_url = auth_url.replace('/v3', '/v2.0')
        return nova_client.Client(
            2,
            self.conf.get_option(
                'keystone_authtoken',
                'username'),
            self.conf.get_option(
                'keystone_authtoken',
                'password'),
            self.conf.get_option(
                'keystone_authtoken',
                'project_name'),
            auth_url,
            region_name=self.conf.get_option(
                'keystone_authtoken',
                'region_name')
            )

    def get_ceilometerclient(self):
        """Telemetry(ceilometer) client
        """
        v3_kwargs = {
                "username": self.conf.get_option(
                    'keystone_authtoken',
                    'username'),
                "password": self.conf.get_option(
                    'keystone_authtoken',
                    'password'),
                "project_name": self.conf.get_option(
                    'keystone_authtoken',
                    'project_name'),
                "user_domain_name": self.conf.get_option(
                    'keystone_authtoken',
                    'user_domain_name'),
                "project_domain_name": self.conf.get_option(
                    'keystone_authtoken',
                    'project_domain_name'),
                "auth_url": self.conf.get_option(
                    'keystone_authtoken',
                    'auth_url'),
                "region_name": self.conf.get_option(
                    'keystone_authtoken',
                    'region_name')
        }
        return clm_clientv20.Client('', **v3_kwargs)
if __name__ == "__main__":
    conf = CONF()
