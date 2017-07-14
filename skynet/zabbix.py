#  Copyright  2017 EasyStack, Inc
#  Author: Branty<jun.wang@easystack.cn>

import copy
import datetime
import json
import logging
import socket
import struct
import urllib2

from skynet.common import OpenStackClients


LOG = logging.getLogger(__name__)
HOST_CACHED = {}

VMS_CACHED = {}


def clear(is_all=False):
    if is_all:
        HOST_CACHED.clear()
    VMS_CACHED.clear()


class ZabbixBase(object):
    """Zabbix Base Class

    Mainly responsible for sending zabbix data by socket
    Zabbix also has a sender utility 'zabbix_sender'.
    zabbix_sender: a command line utility for sending monitoring data
    to Zabbix server or proxy. More details:
        https://www.zabbix.com/documentation/3.0/manpages/zabbix_sender
    """
    def __init__(self, conf):
        self.conf = conf

    def set_proxy_head(self, data):
        """simplify constructing the protocol to communicate with Zabbix"""
        # data_length = len(data)
        # data_header = struct.pack('i', data_length) + '\0\0\0\0'
        # HEADER = '''ZBXD\1%s%s'''
        # data_to_send = HEADER % (data_header, data)
        payload = json.dumps(data)
        return payload

    def connect_zabbix(self, payload):
        """Send zabbix histoty data
        """
        ss = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ss.connect((self.zabbix_host, int(self.zabbix_port)))
        # read socket response, the five bytes are the head msg
        ss.send(payload)
        response_head = ss.recv(5, socket.MSG_WAITALL)
        if response_head != "ZBXD\1":
            LOG.error("Faild to send zabbix socket date,got invalid response.")
            return

        # read the date head to get the length of response
        response_data_head = ss.recv(8, socket.MSG_WAITALL)
        response_data = response_data_head[:4]
        response_len = struct.unpack('i', response_data)[0]

        # read the whole rest of the response now that we know the length
        response_raw = ss.recv(response_len, socket.MSG_WAITALL)
        ss.close()
        response = json.loads(response_raw)
        LOG.info(response)
        return response

    def socket_to_zabbix(self, payload=None):
        data = {"request": "sender data"}
        if isinstance(payload, dict):
            data['data'] = [payload]
        elif isinstance(payload, list):
            data['data'] = payload
        payload = self.set_proxy_head(data)
        self.connect_zabbix(payload)


class ZabbixController(ZabbixBase):
    """Zabbix controller send agent history data by socket
    """
    def __init__(self, conf, mongo_conn):
        super(ZabbixController, self).__init__(conf)
        self.zabbix_host = conf.get_option("zabbix", "zabbix_host")
        self.zabbix_port = conf.get_option("zabbix", "zabbix_port",
                                           default=10051)
        self.zabbix_user = conf.get_option("zabbix", "zabbix_user")
        self.zabbix_user_pwd = conf.get_option("zabbix", "zabbix_user_pwd")
        self.auth = self.get_zabbix_auth()
        self.osk_clients = OpenStackClients(conf)
        self.mongo_handler = mongo_conn

    def get_zabbix_auth(self):
        """ Get admin credentials (user, password) from Zabbix API
        """
        payload = {"jsonrpc": "2.0",
                   "method": "user.login",
                   "params": {"user": self.zabbix_user,
                              "password": self.zabbix_user_pwd},
                   "id": 2}
        response = self.call_zabbix_api(payload)
        if "error" in response:
            LOG.error("Incorrect user or password, please check it again")
        return response['result']

    def call_zabbix_api(self, payload):
        url = "http://%s/zabbix/api_jsonrpc.php" % self.zabbix_host
        data = json.dumps(payload)
        req = urllib2.Request(url, data, {'Content-Type': 'application/json'})
        f = urllib2.urlopen(req)
        response = json.loads(f.read())
        f.close()
        return response

    def get_openstack_hostgroups(self):
        """Get all hosts filtered by hostgroups

        Default filter groups is : ['Controller','Computer']
        """
        # default is ['']
        hostgroups = self.conf.get_option("skynet", "hostgroups")
        hostgroups = [i.strip() for i in hostgroups.split(',')]
        payload = {
            "jsonrpc": "2.0",
            "method": "hostgroup.get",
            "params": {
                "output": "extend",
                "filter": {
                    "name": hostgroups}
            },
            "auth": self.auth,
            "id": 1
        }
        response = self.call_zabbix_api(payload)
        if "error" in response:
            LOG.error("Bad Request:%s" % response['error'])
        return [hg['groupid'] for hg in response['result']]

    def get_all_hosts(self, filters=None):
        payload = {
                "jsonrpc": "2.0",
                "method": "host.get",
                "params": {
                    "output": "extend"
                    },
                "auth": self.auth,
                "id": 1
            }
        payload['params'].update(filters)
        response = self.call_zabbix_api(payload)
        return response

    def get_item_by_filters(self, filters, search_key=None):
        """Get all itemids by hostgroups and search_key

        :param filter:dict: refers to the zabbix hostgroup
        :param search_key:dict: refers to the item_key,also a filter msg
        :rtype: list
        """
        payload = {
                "jsonrpc": "2.0",
                "method": "item.get",
                "params": {
                    "output": "extend"
                    },
                "auth": self.auth,
                "id": 1
        }
        payload['params'].update(filters)
        if search_key:
            payload['params']['search'] = search_key
        response = self.call_zabbix_api(payload)
        return response

    def get_history(self, histoty, itemids,
                    sortfield="clock", sortorder="DESC"):
        payload = {
                "jsonrpc": "2.0",
                "method": "history.get",
                "params": {
                    "output": "extend",
                    "history": histoty,
                    "sortfield": sortfield,
                    "sortorder": sortorder,
                    "limit": len(itemids) if isinstance(itemids,
                                                        list) else 1
                    },
                "auth": self.auth,
                "id": 1
        }
        payload['params']['itemids'] = itemids
        response = self.call_zabbix_api(payload)
        return response

    def create_host_total(self):
        groupids = self.get_openstack_hostgroups()
        try:
            response = self.get_all_hosts({"groupids": groupids})
        except Exception:
            LOG.error("Failed to get all hosts in hostgroups %s" % groupids)
            # Failed to get host, default return None
            return {
                "total": 0,
                "active": 0,
                "off": 0
            }
        if "error" in response:
            LOG.error("Bad Request:%s" % response['error'])
            return {"total": 0,
                    "active": 0,
                    "off": 0}
        total = len(response['result'])
        active = 0
        for host in response['result']:
            if host['status'] == "0" and not host['error']:
                active += 1
        return {
            "total": total,
            "active": active,
            "off": (total - active)}

    def create_memory_usage(self):
        def _get(total_items):
            itemids = list()
            for item in total_items['result']:
                if int(item['lastvalue']) > 0 and int(item['prevvalue']) > 0:
                    itemids.append(item['itemid'])
            total_mems = 0
            for item in itemids:
                ava_mems = self.get_history("3", item)
                total_mems += int(ava_mems['result'][0].get("value", 0))
            return total_mems
        try:
            groupids = self.get_openstack_hostgroups()
            # get total memory
            filters = {"groupids": groupids}
            search_key = {"key_": "vm.memory.size[available]"}
            total_items = self.get_item_by_filters(filters, search_key)
            sum_ava_mems = _get(total_items)

            # get avaliable memory
            search_key['key_'] = "vm.memory.size[total]"
            total_items = self.get_item_by_filters(filters, search_key)
            sum_total_mems = _get(total_items)
            return {
                "available_mems": sum_ava_mems,
                "total_mems": sum_total_mems,
                "mem_used_radio":
                    round(1.0 * (sum_total_mems -
                          sum_ava_mems) / sum_total_mems, 4)
            }
        except:
            LOG.error("Failed to get metric openstack.hosts.memory.usage")
            return {
                "available_mems": 0,
                "total_mems": 0,
                "mem_used_radio": 0.0
            }

    def create_cpu_util(self):
        def _get(total_items):
            itemids = list()
            for item in total_items['result']:
                if float(item['lastvalue']) > 0 and\
                   float(item['prevvalue']) > 0:
                    itemids.append(item['itemid'])
            total_cpu_util = list()
            for item in itemids:
                cpu_util = self.get_history("7", item)
                total_cpu_util.append(float(cpu_util['result'][0].get(
                                        "value",
                                        0)))
            return total_cpu_util
        try:
            groupids = self.get_openstack_hostgroups()
            # get total cpu_util
            filters = {"groupids": groupids}
            search_key = {"key_": "system.cpu.util[,idle]"}
            total_items = self.get_item_by_filters(filters, search_key)
            ideal_utils = _get(total_items)
            cpu_utils = sum([(100 - i) for i in ideal_utils])
            used_radio = round(1.0 * cpu_utils / len(ideal_utils) / 100, 4)
            return {
                "total_cpu_util": 1.0,
                "used_cpu_util": used_radio,
                "used_radio": used_radio
            }
        except:
            LOG.error("Failed to get metric openstack.hosts.cpu.util")
            return {
                "total_cpu_util": 0.0,
                "used_cpu_util": 0.0,
                "used_ratio": 0.0
            }

    def _get_item_values(self, total_items):
        items_map = {}
        for item in total_items['result']:
            if float(item['lastvalue']) > 0 \
               and float(item['prevvalue']) > 0:
                items_map[item['itemid']] = item['hostid']
        pavais_his = list()
        for itemid in items_map.keys():
            response = self.get_history("7", itemid)
            pavais_his.append(
                (items_map[itemid],
                 float(response['result'][0].get("value", 0.0))))
        return pavais_his

    def create_hosts_top_memory_usage(self):
        try:
            top = int(self.conf.get_option("skynet", "top", 5))
            groupids = self.get_openstack_hostgroups()
            filters = {"groupids": groupids}
            search_key = {"key_": "vm.memory.size[pavailable]"}
            total_items = self.get_item_by_filters(filters, search_key)
            total_pavais = self._get_item_values(total_items)
            if len(total_pavais) > top:
                sorted_memory_usage = sorted(total_pavais,
                                             key=lambda i: i[1])[:top]
            else:
                LOG.warn("Total num of openstack physical host %d is less then"
                         "top(%d)" % (len(total_pavais), top))
                sorted_memory_usage = sorted(total_pavais,
                                             key=lambda i: i[1])
            hostid_value_map = {}
            top_result = []
            for i in sorted_memory_usage:
                hostid_value_map[i[0]] = round((100 - i[1]), 2)
            hosts = self.get_all_hosts({"hostids":
                                        hostid_value_map.keys()})['result']
            top_result = [{host['host']:
                          hostid_value_map[host['hostid']]} for host in hosts]
            top_result.sort(cmp=lambda x, y: cmp(x, y),
                            key=lambda x: x.values()[0])
            return top_result
        except:
            LOG.error("Failed to get openstack cluster top%s memory usage"
                      % top)
            return []

    def create_hosts_top_cpu_util(self):
        """The processor load is calculated as system CPU
           load divided by number of CPU cores.
        """
        try:
            top = int(self.conf.get_option("skynet", "top", 5))
            groupids = self.get_openstack_hostgroups()
            filters = {"groupids": groupids}
            search_key = {"key_": "system.cpu.util[,idle]"}
            total_items = self.get_item_by_filters(filters, search_key)
            total_cpus = self._get_item_values(total_items)
            if len(total_cpus) > top:
                sorted_memory_usage = sorted(total_cpus,
                                             key=lambda i: i[1])[:top]
            else:
                LOG.warn("Total num of openstack physical host %d is less then"
                         "top(%d)" % (len(total_cpus), top))
                sorted_memory_usage = sorted(total_cpus,
                                             key=lambda i: i[1])
            hostid_value_map = {}
            top_result = []
            for i in sorted_memory_usage:
                hostid_value_map[i[0]] = i[1]
            hosts = self.get_all_hosts({
                        "hostids":
                        hostid_value_map.keys()})['result']
            top_result = [{
                host['host']:
                round((100 - hostid_value_map[host['hostid']]),
                      4)} for host in hosts]
            top_result.sort(cmp=lambda x, y: cmp(x, y),
                            key=lambda x: x.values()[0])
            return top_result
        except:
            LOG.error("Failed to get openstack cluster top%s memory usage"
                      % top)
            return []

    def _get_all_instances(self, nv_client):
        global VMS_CACHED
        search_opts = {'all_tenants': True}
        vms = nv_client.servers.list(search_opts=search_opts)
        return vms

    def create_vms_total(self):
        global VMS_CACHED
        nv_client = self.osk_clients.nv_client
        try:
            instances = self._get_all_instances(nv_client)
        except:
            LOG.error("Failed to get openstack all vms")
            return {
                "total_count": 0,
                "active_count": 0,
                "error_count": 0,
                "off_count": 0,
                "paused_count": 0
            }
        total_count = len(instances)
        error_count = 0
        off_count = 0
        paused_count = 0
        active_vms = list()
        for i in instances:
            if i.status == "ACTIVE":
                active_vms.append(i.id)
            elif i.status == "ERROR":
                error_count += 1
            elif i.status == "SHUTOFF":
                off_count += 1
            elif i.status == "SUSPENDED":
                paused_count += 1
        if not VMS_CACHED.get("ACTIVE_VMS"):
            VMS_CACHED['ACTIVE_VMS'] = active_vms
        return {
            "total_count": total_count,
            "active_count": len(active_vms),
            "error_count": error_count,
            "off_count": off_count,
            "paused_count": paused_count
            }

    def create_vms_memory_usage(self):
        try:
            hyp_stats_stics = self.osk_clients.nv_client.\
                hypervisor_stats.statistics()
        except:
            LOG.error("Failed to get openstack vms memory usage")
            return {
                "used_memory_mb": 0,
                "total_memory_mb": 0,
                "used_memory_ratio": 0.0
            }
        return {
            "used_memory_mb": hyp_stats_stics.memory_mb_used,
            "total_memory_mb": hyp_stats_stics.memory_mb,
            "used_memory_ratio":
                round(1.0 * hyp_stats_stics.memory_mb_used /
                      hyp_stats_stics.memory_mb, 4)
            }

    def create_vms_vcpu_usage(self):
        try:
            hyp_stats_stics = self.osk_clients.nv_client.\
                hypervisor_stats.statistics()
        except:
            LOG.error("Failed to get openstack vpus kernel usage")
            return {
                "used_vcpus_used": 0,
                "total_vcpus_total": 0,
                "used_vcpus_ratio": 0.0
            }
        return {
            "used_vcpus_used": hyp_stats_stics.vcpus_used,
            "total_vcpus_total": hyp_stats_stics.vcpus,
            "used_vcpus_ratio":
                round(1.0 * hyp_stats_stics.vcpus_used /
                      hyp_stats_stics.vcpus, 4)
            }

    def get_vms_top_metric(self, metric, top=5, windows=3):
        global VMS_CACHED
        if not VMS_CACHED:
            try:
                nv_client = self.osk_clients.nv_client
                instances = self._get_all_instances(nv_client)
            except:
                LOG.error("Failed to get openstack all vms")
                return []
            active_vms = list()
            for vm in instances:
                if vm.status == "ACTIVE":
                    active_vms.append(vm.id)
                VMS_CACHED[vm.id] = vm.name
            VMS_CACHED['ACTIVE_VMS'] = active_vms
        resources = VMS_CACHED['ACTIVE_VMS']
        sample_filter = {
            "resource": resources,
            "meter": metric,
            "start_timestamp":
                # TO DO(Branty)
                datetime.datetime.utcnow() -
                datetime.timedelta(seconds=60 * windows),
            "end_timestamp": datetime.datetime.utcnow(),
            "start_timestamp_op": "gt",
            "end_timestamp_op": "lt"
        }
        try:
            top = int(self.conf.get_option("skynet", "top", 5))
            response = self.mongo_handler.get_meter_statistics(
                sample_filter)
            cache_result = {}
            for stas in response:
                if stas.resource_id not in cache_result:
                    cache_result[stas.resource_id] = stas.avg
            # DESC order
            top_vms = copy.copy(cache_result.items())
            top_vms.sort(
                key=lambda x: x[1],
                cmp=lambda x, y: cmp(float(y), float(x)))
            result = list()
            if len(top_vms) > top:
                for rsc in top_vms:
                    try:
                        if len(result) >= top:
                            break
                        rs = {VMS_CACHED[rsc[0]]: rsc[1]}
                        result.append(rs)
                    except Exception:
                        # TO DO(Branty)
                        # Maybe this intance is deleted
                        LOG.warn("Intance with id %s may be deleted" % rsc[0])
            else:
                LOG.warn("Total num of openstack nova vms %d is less then"
                         "top(%d)" % (len(top_vms), top))
                result.extned(
                    [{VMS_CACHED[rsc[0]]:rsc[1]} for rsc in top_vms]
                )
            cache_result.clear()
            return result
        except:
            LOG.error("Failed to get openstack vm top%d %s metric"
                      % (top, metric))
            return []

    def create_vms_top_memory_usage(self):
        return self.get_vms_top_metric("memory.usage", 5, 3)

    def create_vms_top_vcpu_usage(self, top=5, windows=3):
        return self.get_vms_top_metric("cpu_util", 5, 3)

    def create_alarms_total(self):
        def _get_all_alarms(clm_client):
            return clm_client.alarms.list()
        clm_client = self.osk_clients.clm_client
        try:
            alarms = _get_all_alarms(clm_client)
        except:
            LOG.error("Failed to get all ceilometer alarms")
            return {
                "total_count": 0,
                "no_data_count": 0,
                "alarm_count": 0,
                "ok_count": 0
            }
        ok_count = 0
        alarm_count = 0
        no_data_count = 0
        for alarm in alarms:
            if alarm.state == "insufficient data":
                no_data_count += 1
            elif alarm.state == "alarm":
                alarm_count += 1
            elif alarm.state == "ok":
                ok_count += 1
        return {
            "total_count": len(alarms),
            "no_data_count": no_data_count,
            "alarm_count": alarm_count,
            "ok_count": ok_count
        }
