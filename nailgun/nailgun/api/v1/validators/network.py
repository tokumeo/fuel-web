# -*- coding: utf-8 -*-
#    Copyright 2013 Mirantis, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from nailgun.api.v1.validators.base import BasicValidator
from nailgun import consts

from nailgun import objects

from nailgun.db import db
from nailgun.db.sqlalchemy.models import Cluster
from nailgun.db.sqlalchemy.models import Node
from nailgun.errors import errors
import six


class NetworkConfigurationValidator(BasicValidator):

    @classmethod
    def validate_networks_update(cls, data):
        d = cls.validate_json(data)
        if not d:
            raise errors.InvalidData(
                "No valid data received",
                log_message=True
            )

        networks = d.get('networks')
        if not isinstance(networks, list):
            raise errors.InvalidData(
                "'networks' is expected to be an array",
                log_message=True
            )
        for i in networks:
            if 'id' not in i:
                raise errors.InvalidData(
                    "No 'id' param presents for '{0}' network".format(i),
                    log_message=True
                )
        return d


class NovaNetworkConfigurationValidator(NetworkConfigurationValidator):

    @classmethod
    def validate_dns_servers_update(cls, data):
        d = cls.validate_json(data)

        dns_servers = d['dns_nameservers'].get("nameservers", [])

        if not isinstance(dns_servers, list):
            raise errors.InvalidData(
                "It's expected to receive array of DNS servers, "
                "not a single object",
                log_message=True
            )
        if len(dns_servers) < 2:
            raise errors.InvalidData(
                "There should be at least two DNS servers",
                log_message=True
            )

        return d


class NeutronNetworkConfigurationValidator(NetworkConfigurationValidator):

    @classmethod
    def validate_neutron_params(cls, data, **kwargs):
        d = cls.validate_json(data)
        np = d.get('networking_parameters')
        cluster_id = kwargs.get("cluster_id")
        if cluster_id:
            cluster = db().query(Cluster).get(cluster_id)
            if cluster and cluster.network_config:
                cfg = cluster.network_config
                for k in ("segmentation_type", "net_l23_provider"):
                    if k in np and getattr(cfg, k) != np[k]:
                        raise errors.InvalidData(
                            "Change of '{0}' is prohibited".format(k),
                            log_message=True
                        )
        return d


class NetAssignmentValidator(BasicValidator):
    @classmethod
    def validate(cls, node):
        if not isinstance(node, dict):
            raise errors.InvalidData(
                "Each node should be dict",
                log_message=True
            )
        if 'id' not in node:
            raise errors.InvalidData(
                "Each node should have ID",
                log_message=True
            )
        if 'interfaces' not in node or \
                not isinstance(node['interfaces'], list):
            raise errors.InvalidData(
                "Node '{0}': there is no 'interfaces' list".format(
                    node['id']),
                log_message=True
            )

        net_ids = set()
        for iface in node['interfaces']:
            if not isinstance(iface, dict):
                raise errors.InvalidData(
                    "Node '{0}': each interface should be a dict "
                    "(got '{1}')".format(node['id'], iface),
                    log_message=True
                )
            if 'type' not in iface:
                raise errors.InvalidData(
                    "Node '{0}': each interface must have a type".format(
                        node['id']),
                    log_message=True
                )
            if iface['type'] not in consts.NETWORK_INTERFACE_TYPES:
                raise errors.InvalidData(
                    "Node '{0}': unknown interface type".format(node['id']),
                    log_message=True
                )
            if iface['type'] == consts.NETWORK_INTERFACE_TYPES.ether \
                    and 'id' not in iface:
                raise errors.InvalidData(
                    "Node '{0}': each HW interface must have ID".format(
                        node['id']),
                    log_message=True
                )
            if iface['type'] == consts.NETWORK_INTERFACE_TYPES.bond:
                if 'name' not in iface:
                    raise errors.InvalidData(
                        "Node '{0}': each bond interface must have "
                        "name".format(node['id']),
                        log_message=True
                    )
                if 'slaves' not in iface \
                        or not isinstance(iface['slaves'], list) \
                        or len(iface['slaves']) < 2:
                    raise errors.InvalidData(
                        "Node '{0}': each bond interface must have two or more"
                        " slaves".format(node['id']),
                        log_message=True
                    )
                for slave in iface['slaves']:
                    if 'name' not in slave:
                        raise errors.InvalidData(
                            "Node '{0}', interface '{1}': each bond slave "
                            "must have name".format(node['id'], iface['name']),
                            log_message=True
                        )
                if 'bond_properties' in iface:
                    for k in iface['bond_properties'].keys():
                        if k not in consts.BOND_PROPERTIES:
                            raise errors.InvalidData(
                                "Node '{0}', interface '{1}': unknown bond "
                                "property '{2}'".format(
                                    node['id'], iface['name'], k),
                                log_message=True
                            )
                bond_mode = cls.get_bond_mode(iface)
                if not bond_mode:
                    raise errors.InvalidData(
                        "Node '{0}': bond interface '{1}' doesn't have "
                        "mode".format(node['id'], iface['name']),
                        log_message=True
                    )
                if bond_mode not in consts.BOND_MODES:
                    raise errors.InvalidData(
                        "Node '{0}': bond interface '{1}' has unknown "
                        "mode '{2}'".format(
                            node['id'], iface['name'], bond_mode),
                        log_message=True
                    )
            if 'assigned_networks' not in iface or \
                    not isinstance(iface['assigned_networks'], list):
                raise errors.InvalidData(
                    "Node '{0}', interface '{1}':"
                    " there is no 'assigned_networks' list".format(
                        node['id'], iface.get('id') or iface.get('name')),
                    log_message=True
                )

            for net in iface['assigned_networks']:
                if not isinstance(net, dict):
                    raise errors.InvalidData(
                        "Node '{0}', interface '{1}':"
                        " each assigned network should be a dict".format(
                            node['id'], iface.get('id') or iface.get('name')),
                        log_message=True
                    )
                if 'id' not in net:
                    raise errors.InvalidData(
                        "Node '{0}', interface '{1}':"
                        " each assigned network should have ID".format(
                            node['id'], iface.get('id') or iface.get('name')),
                        log_message=True
                    )
                if net['id'] in net_ids:
                    raise errors.InvalidData(
                        "Node '{0}': there is a duplicated network '{1}' in"
                        " assigned networks (second occurrence is in "
                        "interface '{2}')".format(
                            node['id'], net['id'],
                            iface.get('id') or iface.get('name')),
                        log_message=True
                    )
                net_ids.add(net['id'])
        return node

    @classmethod
    def get_bond_mode(cls, iface):
        bond_mode = None
        if 'mode' in iface:
            bond_mode = iface['mode']
        if 'mode' in iface.get('bond_properties', {}):
            bond_mode = iface['bond_properties']['mode']
        return bond_mode

    @classmethod
    def validate_structure(cls, webdata):
        node_data = cls.validate_json(webdata)
        return cls.validate(node_data)

    @classmethod
    def validate_collection_structure_and_data(cls, webdata):
        data = cls.validate_json(webdata)
        if not isinstance(data, list):
            raise errors.InvalidData(
                "Data should be list of nodes",
                log_message=True
            )
        for node_data in data:
            cls.validate(node_data)
            cls.verify_data_correctness(node_data)
        return data

    @classmethod
    def validate_structure_and_data(cls, webdata, node_id):
        interfaces_data = cls.validate_json(webdata)
        node_data = {'id': node_id, 'interfaces': interfaces_data}
        cls.validate(node_data)
        cls.verify_data_correctness(node_data)
        return interfaces_data

    @classmethod
    def verify_data_correctness(cls, node):
        db_node = db().query(Node).filter_by(id=node['id']).first()
        if not db_node:
            raise errors.InvalidData(
                "There is no node with ID '{0}' in DB".format(node['id']),
                log_message=True
            )
        if objects.Node.hardware_info_locked(db_node):
            raise errors.InvalidData(
                "Node '{0}': Interfaces configuration can't be changed after "
                "or during deployment.".format(db_node.id))
        interfaces = node['interfaces']
        db_interfaces = db_node.nic_interfaces
        net_manager = objects.Cluster.get_network_manager(db_node.cluster)
        network_group_ids = net_manager.get_node_networkgroups_ids(db_node)

        bonded_eth_ids = set()
        pxe_iface_name = net_manager._get_pxe_iface_name(db_node)
        if not pxe_iface_name:
            raise errors.InvalidData(
                "Node '{0}': Interfaces configuration can't be changed if"
                "there is no pxe interface in DB".format(node['id']),
                log_message=True
            )

        for iface in interfaces:
            iface_nets = [n.get('name')
                          for n in iface.get('assigned_networks')]
            if iface['type'] == consts.NETWORK_INTERFACE_TYPES.ether:
                db_iface = next(six.moves.filter(
                    lambda i: i.id == iface['id'],
                    db_interfaces
                ), None)
                if not db_iface:
                    raise errors.InvalidData(
                        "Node '{0}': there is no interface with ID '{1}'"
                        " in DB".format(node['id'], iface['id']),
                        log_message=True
                    )
                if not db_iface.pxe:
                    if consts.NETWORKS.fuelweb_admin in iface_nets:
                        raise errors.InvalidData(
                            "Node '{0}': admin network can not be assigned to"
                            " non-pxe interface {1}".format(node['id'],
                                                            iface['name']),
                            log_message=True
                        )
            elif iface['type'] == consts.NETWORK_INTERFACE_TYPES.bond:
                pxe_iface_present = False
                for slave in iface['slaves']:
                    iface_id = [i.id for i in db_interfaces
                                if i.name == slave['name']]
                    if slave["name"] == pxe_iface_name:
                        pxe_iface_present = True
                    if iface_id:
                        if iface_id[0] in bonded_eth_ids:
                            raise errors.InvalidData(
                                "Node '{0}': interface '{1}' is used in bonds "
                                "more than once".format(
                                    node['id'], iface_id[0]),
                                log_message=True
                            )
                        bonded_eth_ids.add(iface_id[0])
                    else:
                        raise errors.InvalidData(
                            "Node '{0}': there is no interface '{1}' found "
                            "for bond '{2}' in DB".format(
                                node['id'], slave['name'], iface['name']),
                            log_message=True
                        )

                if consts.NETWORKS.fuelweb_admin in iface_nets:
                    prohibited_modes = net_manager.\
                        get_prohibited_admin_bond_modes()
                    bond_mode = cls.get_bond_mode(iface)
                    if bond_mode in prohibited_modes:
                        raise errors.InvalidData(
                            "Node '{0}': interface '{1}' belongs to "
                            "admin network and has lacp mode '{2}'".format(
                                node['id'], iface['name'], bond_mode),
                            log_message=True
                        )
                    if not pxe_iface_present:
                        raise errors.InvalidData(
                            "Node '{0}': interface '{1}' belongs to "
                            "admin network and doesn't contain node's pxe "
                            "interface '{2}'".format(
                                node['id'], iface['name'], pxe_iface_name),
                            log_message=True
                        )

            for net in iface['assigned_networks']:
                if net['id'] not in network_group_ids:
                    raise errors.InvalidData(
                        "Network '{0}' doesn't exist for node {1}".format(
                            net['id'], node['id']),
                        log_message=True
                    )
                network_group_ids.remove(net['id'])

        if network_group_ids:
            str_ng_ids = ["'" + str(ng_id) + "'"
                          for ng_id in network_group_ids]
            raise errors.InvalidData(
                "Node '{0}': {1} network(s) are left unassigned".format(
                    node['id'], ",".join(str_ng_ids)),
                log_message=True
            )

        for iface in interfaces:
            if iface['type'] == consts.NETWORK_INTERFACE_TYPES.ether \
                    and iface['id'] in bonded_eth_ids \
                    and len(iface['assigned_networks']) > 0:
                raise errors.InvalidData(
                    "Node '{0}': interface '{1}' cannot have "
                    "assigned networks as it is used in "
                    "bond".format(node['id'], iface['id']),
                    log_message=True
                )
