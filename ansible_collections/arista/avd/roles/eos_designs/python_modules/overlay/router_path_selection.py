# Copyright (c) 2023-2024 Arista Networks, Inc.
# Use of this source code is governed by the Apache License 2.0
# that can be found in the LICENSE file.
from __future__ import annotations

from functools import cached_property

from ansible_collections.arista.avd.plugins.plugin_utils.strip_empties import strip_empties_from_dict
from ansible_collections.arista.avd.plugins.plugin_utils.utils import get, get_item

from .utils import UtilsMixin


class RouterPathSelectionMixin(UtilsMixin):
    """
    Mixin Class used to generate structured config for one key.
    Class should only be used as Mixin to a AvdStructuredConfig class
    """

    @cached_property
    def router_path_selection(self) -> dict | None:
        """
        Return structured config for router path-selection (DPS)
        """

        if not self.shared_utils.is_wan_router:
            return None

        router_path_selection = {
            "tcp_mss_ceiling": {"ipv4_segment_size": get(self.shared_utils.switch_data_combined, "dps_mss_ipv4", default="auto")},
            "path_groups": self._get_path_groups(),
        }

        if self.shared_utils.is_wan_server:
            router_path_selection["peer_dynamic_source"] = "stun"

        return strip_empties_from_dict(router_path_selection)

    @cached_property
    def _cp_ipsec_profile_name(self) -> str:
        """
        Returns the IPsec profile name to use for Control-Plane
        """
        return get(self._hostvars, "wan_ipsec_profiles.control_plane.profile_name", default="CP-PROFILE")

    @cached_property
    def _dp_ipsec_profile_name(self) -> str:
        """
        Returns the IPsec profile name to use for Data-Plane
        """
        # TODO need to use CP one if 'wan_ipsec_profiles.data_plane' not present
        return get(self._hostvars, "wan_ipsec_profiles.data_plane.profile_name", default="DP-PROFILE")

    def _get_path_groups(self) -> list:
        """
        Generate the required path-groups locally
        """
        path_groups = []

        if self.shared_utils.is_wan_server:
            # Configure all path-groups on Pathfinders and AutoVPN RRs
            path_groups_to_configure = self.shared_utils.wan_path_groups
        else:
            path_groups_to_configure = self.shared_utils.wan_local_path_groups

        local_path_groups_names = [path_group["name"] for path_group in self.shared_utils.wan_local_path_groups]

        for path_group in path_groups_to_configure:
            pg_name = path_group.get("name")

            path_group_data = {
                "name": pg_name,
                "id": self._get_path_group_id(pg_name, path_group.get("id")),
                "local_interfaces": self._get_local_interfaces_for_path_group(pg_name),
                "dynamic_peers": self._get_dynamic_peers(),
                "static_peers": self._get_static_peers_for_path_group(pg_name),
            }

            # On pathfinder IPsec profile is not required for non local path_groups
            if pg_name in local_path_groups_names and path_group.get("ipsec", True):
                path_group_data["ipsec_profile"] = self._cp_ipsec_profile_name

            path_groups.append(path_group_data)

        if self.shared_utils.wan_ha or self.shared_utils.is_cv_pathfinder_server:
            path_groups.append(self._generate_ha_path_group())

        return path_groups

    def _generate_ha_path_group(self) -> dict:
        """
        Called only when self.shared_utils.wan_ha is True or on Pathfinders
        """
        ha_path_group = {
            "name": self.shared_utils.wan_ha_path_group_name,
            "id": self._get_path_group_id(self.shared_utils.wan_ha_path_group_name),
            "flow_assignment": "lan",
        }
        if self.shared_utils.is_cv_pathfinder_server:
            return ha_path_group

        # not a pathfinder device
        ha_path_group.update(
            {
                # This should be the LAN interface over which a DPS tunnel is built
                "local_interfaces": [{"name": interface["interface"]} for interface in self._wan_ha_interfaces()],
                "static_peers": [
                    {
                        "router_ip": self._wan_ha_peer_vtep_ip(),
                        "name": self.shared_utils.wan_ha_peer,
                        "ipv4_addresses": [ip_address.split("/")[0] for ip_address in self.shared_utils.wan_ha_peer_ip_addresses],
                    }
                ],
            }
        )
        if get(self.shared_utils.switch_data_combined, "wan_ha.ipsec", default=True):
            ha_path_group["ipsec_profile"] = self._dp_ipsec_profile_name

        return ha_path_group

    def _wan_ha_interfaces(self) -> list:
        """
        Return list of interfaces for HA
        """
        return [uplink for uplink in self.shared_utils.get_switch_fact("uplinks") if get(uplink, "vrf") is None]

    def _wan_ha_peer_vtep_ip(self) -> str:
        """ """
        peer_facts = self.shared_utils.get_peer_facts(self.shared_utils.wan_ha_peer, required=True)
        return get(peer_facts, "vtep_ip", required=True)

    def _get_path_group_id(self, path_group_name: str, config_id: int | None = None) -> int:
        """
        TODO - implement algorithm to auto assign IDs - cf internal documenation
        TODO - also implement algorithm for cross connects on public path_groups
        """
        if path_group_name == self.shared_utils.wan_ha_path_group_name:
            return 65535
        if config_id is not None:
            return config_id
        return 500

    def _get_local_interfaces_for_path_group(self, path_group_name: str) -> list | None:
        """
        Generate the router_path_selection.local_interfaces list

        For AUTOVPN clients, configure the stun server profiles as appropriate
        """
        local_interfaces = []
        path_group = get_item(self.shared_utils.wan_local_path_groups, "name", path_group_name, default={})
        for interface in path_group.get("interfaces", []):
            local_interface = {"name": get(interface, "name", required=True)}

            if self.shared_utils.is_wan_client and self.shared_utils.should_connect_to_wan_rs([path_group_name]):
                stun_server_profiles = self._stun_server_profiles.get(path_group_name, [])
                if stun_server_profiles:
                    local_interface["stun"] = {"server_profiles": [profile["name"] for profile in stun_server_profiles]}

            local_interfaces.append(local_interface)

        return local_interfaces

    def _get_dynamic_peers(self) -> dict | None:
        """
        TODO support ip_local and ipsec ?
        """
        if not self.shared_utils.is_wan_client:
            return None
        return {"enabled": True}

    def _get_static_peers_for_path_group(self, path_group_name: str) -> list | None:
        """
        Retrieves the static peers to configure for a given path-group based on the connected nodes.
        """
        if not self.shared_utils.is_wan_router:
            return None

        static_peers = []
        for wan_route_server_name, wan_route_server in self.shared_utils.filtered_wan_route_servers.items():
            if (path_group := get_item(get(wan_route_server, "wan_path_groups", default=[]), "name", path_group_name)) is not None:
                ipv4_addresses = []

                for interface_dict in get(path_group, "interfaces", required=True):
                    if (ip_address := interface_dict.get("ip_address")) is not None:
                        # TODO - removing mask using split but maybe a helper is clearer
                        ipv4_addresses.append(ip_address.split("/")[0])
                static_peers.append(
                    {
                        "router_ip": get(wan_route_server, "vtep_ip", required=True),
                        "name": wan_route_server_name,
                        "ipv4_addresses": ipv4_addresses,
                    }
                )

        return static_peers
