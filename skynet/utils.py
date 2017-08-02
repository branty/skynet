#  Copyright  2017 EasyStack, Inc

import logging
import time

import six

from skynet import exceptions


LOG = logging.getLogger(__name__)


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


def calculate_items_usage(hypervisors, item):
    """Calculate openstack hypervisor item usage

    Due to allocation ratio of virtual CPU to physical CPU, OpenStack VMS can
    be allocated more resource(such as disk,cpu,memory) than physical.The
    calculation formula for different items:
        used_item / (total_item * item_allocation_ratio)

    Note: disabled hypervisors and "ironic" type hypervisors will be filtered
    @param hypervisors : openstack nova hypervisor instancs
    @param item: exptected to calculation item
    """
    def _sum_item(total, used, hp):
        if item == "vcpu":
            total += hp.vcpus * hp.cpu_allocation_ratio
            used += hp.vcpus_used
        elif item == "memory":
            total += hp.memory_mb * hp.ram_allocation_ratio
            used += hp.memory_mb_used
        else:
            # Additional items will be token into considerarion
            pass
        return (total, used)
    item_total = 0
    item_used = 0
    item_ratio = 0.0
    if not isinstance(hypervisors, list):
        return (item_total, item_used, item_ratio)
    else:
        for hp in hypervisors:
            if hp.hypervisor_type == "ironic":
                # Due to "ironic" type of hypervisor driver,
                # Skip to calculate those values
                continue
            elif hp.status == "disable":
                # When the hypervisor is disable,
                # The total items should be included
                hp.vcpu_used = 0
                hp.memory_mb_used = 0
                item_total, item_used = _sum_item(item_total,
                                                  item_used,
                                                  hp)
            elif hp.state in ["up", "down"]:
                item_total, item_used = _sum_item(item_total,
                                                  item_used,
                                                  hp)
            else:
                # Maybe more scenarios should be token into consideration.
                pass
    item_ratio = round(item_used / item_total, 4)
    return (item_total, item_used, item_ratio)


class Retry(object):

    def __init__(self,
                 stop_max_attemp_number=None,
                 stop_max_delay=None):
        self.stop_max_attemp_number = 3 if stop_max_attemp_number is\
            None else stop_max_attemp_number
        self.stop_max_delay = 5 if stop_max_delay is\
            None else stop_max_delay

    def call(self, func, *args, **kwargs):
        """when Failed, Retry the executed func as you need"""
        raise exceptions.NotImplementsError(
                "Retry function is not implemented")


class ZabbixRetry(Retry):

    def __init__(self,
                 stop_max_attemp_number=None,
                 stop_max_delay=None):
        super(ZabbixRetry, self).__init__(stop_max_attemp_number,
                                          stop_max_delay)

    def call(self, func, *args, **kwargs):
        attempt_times = 1
        conf = kwargs.get('conf')
        while True:
            try:
                zbx_handler = func(
                    conf,
                    kwargs.get('mongo_conn'))
            except Exception as err:
                if self.stop_max_attemp_number > 0 and attempt_times\
                  > self.stop_max_attemp_number:
                    LOG.error('Unable to connect to the zabbix server(host: '
                              '%(host)s, port: %(port)s) after %(retries)d '
                              'retries. Giving up.'
                              % {'retries': self.stop_max_attemp_number,
                                 'host': conf.get_option("zabbix",
                                                         "zabbix_host"),
                                 'port': conf.get_option('zabbix',
                                                         'zabbix_web_port')})
                    raise
                LOG.warn('Unable to connect to the zabbix server(%(host)s,'
                         'port: %(port)s): %(errmsg)s. Trying again in '
                         '%(retry_interval)d seconds.'
                         % {'host': conf.get_option('zabbix', 'zabbix_host'),
                            'port': conf.get_option('zabbix',
                                                    'zabbix_web_port'),
                            'errmsg': err,
                            'retry_interval': self.stop_max_delay})
                attempt_times += 1
                time.sleep(self.stop_max_delay)
            else:
                # Success and return connection
                return zbx_handler


def retry(*dargs, **dkw):
    """ Decorator function that instantiates the Retrying object

    @param *dargs: positional arguments passed to Retrying object
    @param **dkw: keyword arguments passed to the Retrying object

    """
    # support both @retry and @retry() as valid syntax
    if len(dargs) == 1 and callable(dargs[0]):
        def wrap_simple(f):

            @six.wraps(f)
            def wrapped_f(*args, **kw):
                return ZabbixRetry().call(f, *args, **kw)
            return wrapped_f
        return wrap_simple(dargs[0])
    else:
        def wrap(f):
            def wrapped_f(*args, **kw):
                return ZabbixRetry(*dargs, **dkw).call(f, *args, **kw)
            return wrapped_f
        return wrap
