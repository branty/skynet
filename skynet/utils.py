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
