#    Copyright  2017 EasyStack, Inc
#    Authors: Branty <jun.wang@easystack.cn>


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
