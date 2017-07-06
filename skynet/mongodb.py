#    Copyright  2017 EasyStack, Inc
#    Authors: Branty <jun.wang@easystack.cn>

import datetime
import time

import pymongo
import six

import common
from common import CONF

conf = CONF()

MAX_RETRIES = conf.get_option('mongodb', 'max_retries', 3)
RETRY_INTERVAL = conf.get_option('mongodb', 'retry_interval', 2)
MONGO_URL = conf.get_option('mongodb', 'connection')
MAPPING_FILE = conf.get_option('mongodb', 'mapping_file',
                               'mapping.json')


def get_metric_BASE_T(map_dict, metric=None):
    """
    :param map_dict: Parsed mapping.json as a dict

    """
    if not isinstance(map_dict, dict):
        raise
    if metric is None:
        return
    for period in map_dict['period_colls']:
        metrics = map_dict.get(str(period))
        if not metrics:
            continue
        if metric in metrics['meter_type']:
            return int(period)


def make_timestamp_range(start, end,
                         start_timestamp_op=None, end_timestamp_op=None):

    """Create the query document to find timestamps within that range.

    This is done by given two possible datetimes and their operations.
    By default, using $gte for the lower bound and $lt for the upper bound.
    """
    ts_range = {}

    if start:
        if start_timestamp_op == 'gt':
            start_timestamp_op = '$gt'
        else:
            start_timestamp_op = '$gte'
        ts_range[start_timestamp_op] = start

    if end:
        if end_timestamp_op == 'le':
            end_timestamp_op = '$lte'
        else:
            end_timestamp_op = '$lt'
        ts_range[end_timestamp_op] = end
    return ts_range


def make_query_from_filter(sample_filter, require_meter=True):
    """Return a query dictionary based on the settings in the filter.

    :param sample_filter: SampleFilter instance
    :param require_meter: If true and the filter does not have a meter,
                          raise an error.
    """
    q = {}

    """If the length of query counter is more than 1
    then return like '$in': ['counter1', 'counter1']
    """
    if sample_filter.get('meter'):
        if isinstance(sample_filter.get('meter'), list):
            q['counter_name'] = {
                "$in": sample_filter.get('meter')
            }
        else:
            q['counter_name'] = sample_filter.get('meter')
    elif require_meter:
        raise RuntimeError('Missing required meter specifier')

    ts_range = make_timestamp_range(sample_filter.get('start_timestamp'),
                                    sample_filter.get('end_timestamp'),
                                    sample_filter.get('start_timestamp_op'),
                                    sample_filter.get('end_timestamp_op'))

    if ts_range:
        q['timestamp'] = ts_range

    if sample_filter.get('resource'):
        if isinstance(sample_filter.get('resource'), list):
            q['resource_id'] = {
                "$in": sample_filter.get("resource"),
            }
        else:
            q['resource_id'] = sample_filter.get('resource')
    return q


class Model(object):
    """Base class for storage API models."""

    def __init__(self, **kwds):
        self.fields = list(kwds)
        for k, v in six.iteritems(kwds):
            setattr(self, k, v)

    def as_dict(self):
        d = {}
        for f in self.fields:
            v = getattr(self, f)
            if isinstance(v, Model):
                v = v.as_dict()
            elif isinstance(v, list) and v and isinstance(v[0], Model):
                v = [sub.as_dict() for sub in v]
            d[f] = v
        return d


class Statistics(Model):
    """Computed statistics based on a set of sample data."""
    def __init__(self, unit,
                 period, period_start, period_end,
                 duration, duration_start, duration_end,
                 groupby, **data):
        """Create a new statistics object.

        :param unit: The unit type of the data set
        :param period: The length of the time range covered by these stats
        :param period_start: The timestamp for the start of the period
        :param period_end: The timestamp for the end of the period
        :param duration: The total time for the matching samples
        :param duration_start: The earliest time for the matching samples
        :param duration_end: The latest time for the matching samples
        :param groupby: The fields used to group the samples.
        :param data: some or all of the following aggregates
           min: The smallest volume found
           max: The largest volume found
           avg: The average of all volumes found
           sum: The total of all volumes found
           count: The number of samples found
           aggregate: name-value pairs for selectable aggregates
        """
        super(Statistics, self).__init__(
            unit=unit,
            period=period,
            period_start=period_start,
            period_end=period_end,
            duration=duration,
            duration_start=duration_start,
            duration_end=duration_end,
            groupby=groupby,
            **data)


def safe_mongo_call(call):
    def closure(*args, **kwargs):
        max_retries = MAX_RETRIES
        retry_interval = RETRY_INTERVAL
        attempts = 0
        while True:
            try:
                return call(*args, **kwargs)
            except pymongo.errors.AutoReconnect as err:
                if 0 <= max_retries <= attempts:
                    print('Unable to reconnect to the primary mongodb '
                          'after %(retries)d retries. Giving up.' %
                          {'retries': max_retries})
                    raise
                print('Unable to reconnect to the primary mongodb: '
                      '%(errmsg)s. Trying again in %(retry_interval)d '
                      'seconds.' %
                      {'errmsg': err, 'retry_interval': retry_interval})
                attempts += 1
                time.sleep(retry_interval)
    return closure


class Connection(object):
    """MongoDB connection.
    """
    SORT_OPERATION_MAPPING = {'desc': pymongo.DESCENDING,
                              'asc': pymongo.ASCENDING}
    _GENESIS = datetime.datetime(year=datetime.MINYEAR, month=1, day=1)
    _APOCALYPSE = datetime.datetime(year=datetime.MAXYEAR, month=12, day=31,
                                    hour=23, minute=59, second=59)
    SAMPLE_T = 60

    def __init__(self, conf):
        self.conf = conf
        url = MONGO_URL
        max_retries = MAX_RETRIES
        retry_interval = RETRY_INTERVAL
        attempts = 0
        while True:
            try:
                self.client = pymongo.MongoClient(url)
                print('mongo client: %s' % self.client)
                self.CACHE_MAPPING_FILE = common.parse_metric_json(conf)
            except pymongo.errors.ConnectionFailure as e:
                if max_retries >= 0 and attempts >= max_retries:
                    print('Unable to connect to the database after '
                          '%(retries)d retries. Giving up.' %
                          {'retries': max_retries})
                    raise
                print('Unable to connect to the database server: '
                      '%(errmsg)s. Trying again in %(retry_interval)d '
                      'seconds.' %
                      {'errmsg': e, 'retry_interval': retry_interval})
                attempts += 1
                time.sleep(retry_interval)
            except Exception as e:
                print ('Unable to connect to the database server: '
                       '%(errmsg)s.' % {'errmsg': e})
                raise
            else:
                connection_options = pymongo.uri_parser.parse_uri(url)
                self.db = getattr(self.client, connection_options['database'])
                self.db.authenticate(connection_options['username'],
                                     connection_options['password'])
                break

    def get_meter_statistics(self, sample_filter, period=None, groupby=None,
                             aggregate=None, limit=None):
        """Return an iterable of models.Statistics instance containing meter
        statistics described by the query parameters.

        The filter must have a meter value set.

        """
        if groupby or aggregate:
            # TO DO
            # ceilometet.storage.impl_mongo.Connection.get_meter_statistics
            return []
        aggregate = []
        if (groupby and
                set(groupby) - set(['user_id', 'project_id',
                                    'resource_id', 'source'])):
            raise NotImplementedError("Unable to group by these fields")
        q = make_query_from_filter(sample_filter)
        if period:
            T = period
        else:
            # Set the smallest base_period as default sample period
            # T = self.SAMPLE_T
            T = get_metric_BASE_T(self.CACHE_MAPPING_FILE,
                                  sample_filter.get('meter')) \
                                  or self.SAMPLE_T
        coll = 'statistics%s' % T
        # print ("get_statistics2 q = %s" % q)
        if limit:
            results = self.db[coll].find(q,
                                         sort=[('timestamp', -1)],
                                         limit=limit)
        else:
            results = self.db[coll].find(q, sort=[('timestamp', -1)])

        stats = [self._stats_result_to_model(r, groupby, aggregate)
                 for r in results]
        return stats

    def _stats_result_aggregates(self, result, aggregate):
        stats_args = {}
        for attr in ['count', 'min', 'max', 'sum', 'avg']:
            if attr in result:
                stats_args[attr] = result[attr]

        if aggregate:
            stats_args['aggregate'] = {}
            for a in aggregate:
                ak = '%s%s' % (a.func, '/%s' % a.param if a.param else '')
                if ak in result:
                    stats_args['aggregate'][ak] = result[ak]
                elif 'aggregate' in result:
                    stats_args['aggregate'][ak] = result['aggregate'].get(ak)
        return stats_args

    def _stats_result_to_model(self, result, groupby, aggregate,
                               period=None, first_timestamp=None):

        stats_args = self._stats_result_aggregates(result, aggregate)
        stats_args['resource_id'] = result['resource_id']
        stats_args['unit'] = result['unit']
        stats_args['duration'] = result['T'] if 'T' in result \
            else result['duration']
        stats_args['duration_start'] = result['period_start']
        stats_args['duration_end'] = result['period_end']
        stats_args['period'] = result['T'] if 'T' in result \
            else result['period']
        stats_args['period_start'] = result['period_start']
        stats_args['period_end'] = result['period_end']
        stats_args['groupby'] = (dict(
            (g, result['groupby'][g]) for g in groupby) if groupby else None)
        return Statistics(**stats_args)
