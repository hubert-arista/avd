# Copyright (c) 2023-2024 Arista Networks, Inc.
# Use of this source code is governed by the Apache License 2.0
# that can be found in the LICENSE file.
from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

from ansible_collections.arista.avd.plugins.filter.range_expand import range_expand
from ansible_collections.arista.avd.plugins.plugin_utils.errors import AristaAvdError, AristaAvdMissingVariableError
from ansible_collections.arista.avd.plugins.plugin_utils.utils import get

if TYPE_CHECKING:
    from .avdipaddressing import AvdIpAddressing


class UtilsMixin:
    """
    Mixin Class with internal functions.
    Class should only be used as Mixin to an AvdIpAddressing class
    """

    @cached_property
    def _mlag_primary_id(self: "AvdIpAddressing") -> int:
        if self.shared_utils.mlag_switch_ids is None or self.shared_utils.mlag_switch_ids.get("primary") is None:
            raise AristaAvdMissingVariableError("'mlag_switch_ids' is required to calculate MLAG IP addresses")
        return self.shared_utils.mlag_switch_ids["primary"]

    @cached_property
    def _mlag_secondary_id(self: "AvdIpAddressing") -> int:
        if self.shared_utils.mlag_switch_ids is None or self.shared_utils.mlag_switch_ids.get("secondary") is None:
            raise AristaAvdMissingVariableError("'mlag_switch_ids' is required to calculate MLAG IP addresses")
        return self.shared_utils.mlag_switch_ids["secondary"]

    @cached_property
    def _fabric_ipaddress_mlag_algorithm(self: "AvdIpAddressing") -> str:
        return self.shared_utils.fabric_ip_addressing_mlag_algorithm

    @cached_property
    def _fabric_ip_addressing_mlag_ipv4_prefix_length(self: "AvdIpAddressing") -> int:
        return self.shared_utils.fabric_ip_addressing_mlag_ipv4_prefix_length

    @cached_property
    def _fabric_ip_addressing_p2p_uplinks_ipv4_prefix_length(self: "AvdIpAddressing") -> int:
        return self.shared_utils.fabric_ip_addressing_p2p_uplinks_ipv4_prefix_length

    @cached_property
    def _mlag_peer_ipv4_pool(self: "AvdIpAddressing") -> str:
        return self.shared_utils.mlag_peer_ipv4_pool

    @cached_property
    def _mlag_peer_l3_ipv4_pool(self: "AvdIpAddressing") -> str:
        return self.shared_utils.mlag_peer_l3_ipv4_pool

    @cached_property
    def _uplink_ipv4_pool(self: "AvdIpAddressing") -> str:
        if self.shared_utils.uplink_ipv4_pool is None:
            raise AristaAvdMissingVariableError("'uplink_ipv4_pool' is required to calculate uplink IP addresses")
        return self.shared_utils.uplink_ipv4_pool

    @cached_property
    def _id(self: "AvdIpAddressing") -> int:
        if self.shared_utils.id is None:
            raise AristaAvdMissingVariableError("'id' is required to calculate IP addresses")
        return self.shared_utils.id

    @cached_property
    def _max_uplink_switches(self: "AvdIpAddressing") -> int:
        return self.shared_utils.max_uplink_switches

    @cached_property
    def _max_parallel_uplinks(self: "AvdIpAddressing") -> int:
        return self.shared_utils.max_parallel_uplinks

    @cached_property
    def _loopback_ipv4_pool(self: "AvdIpAddressing") -> str:
        return self.shared_utils.loopback_ipv4_pool

    @cached_property
    def _loopback_ipv4_offset(self: "AvdIpAddressing") -> int:
        return self.shared_utils.loopback_ipv4_offset

    @cached_property
    def _loopback_ipv6_pool(self: "AvdIpAddressing") -> str:
        return self.shared_utils.loopback_ipv6_pool

    @cached_property
    def _loopback_ipv6_offset(self: "AvdIpAddressing") -> int:
        return self.shared_utils.loopback_ipv6_offset

    @cached_property
    def _vtep_loopback_ipv4_pool(self: "AvdIpAddressing") -> str:
        return self.shared_utils.vtep_loopback_ipv4_pool

    @cached_property
    def _mlag_odd_id_based_offset(self: "AvdIpAddressing") -> int:
        """
        Return the subnet offset for an MLAG pair based on odd id

        Requires a pair of odd and even IDs
        """

        # Verify a mix of odd and even IDs
        if (self._mlag_primary_id % 2) == (self._mlag_secondary_id % 2):
            raise AristaAvdError("MLAG compact addressing mode requires all MLAG pairs to have a single odd and even ID")

        odd_id = self._mlag_primary_id
        if odd_id % 2 == 0:
            odd_id = self._mlag_secondary_id

        return int((odd_id - 1) / 2)

    def _get_parallel_uplink_index(self: "AvdIpAddressing", uplink_switch_index: int) -> int:
        uplink_switch = self.shared_utils.uplink_switches[uplink_switch_index]
        uplink_switch_indexes = [index for index, value in enumerate(self.shared_utils.uplink_switches) if value == uplink_switch]
        # Find index of uplink_interface going to the same uplink_switch (in case of parallel uplinks)
        return uplink_switch_indexes.index(uplink_switch_index)

    def _get_downlink_ipv4_pool(self: "AvdIpAddressing", uplink_switch_index: int) -> str | None:
        uplink_switch_interface = self.shared_utils.uplink_switch_interfaces[uplink_switch_index]
        uplink_switch = self.shared_utils.uplink_switches[uplink_switch_index]
        peer_facts = self.shared_utils.get_peer_facts(uplink_switch, required=True)
        downlink_pools = get(peer_facts, "downlink_pools")

        if not downlink_pools:
            return None

        for downlink_pool_and_interfaces in downlink_pools:
            downlink_interfaces = range_expand(get(downlink_pool_and_interfaces, "downlink_interfaces"))

            if uplink_switch_interface in range_expand(downlink_interfaces):
                # Return IPv4 if uplink_switch_interface is present in downlink_interfaces
                return get(downlink_pool_and_interfaces, "downlink_ipv4_pool")

            # Do some checking if a defined pool was not matched, dangling interfaces, currently this does nothing

    def _get_p2p_ipv4_pool(self: "AvdIpAddressing", uplink_switch_index: int) -> str:
        uplink_pool = self.shared_utils.uplink_ipv4_pool
        downlink_pool = self._get_downlink_ipv4_pool(uplink_switch_index)
        if uplink_pool is not None and downlink_pool is not None:
            raise AristaAvdError("Either 'uplink_ipv4_pool' is set on this switch or 'downlink_pools' is set on all uplink switches, not both.")

        if uplink_pool is None and downlink_pool is None:
            raise AristaAvdMissingVariableError(
                "To calculate uplink IP addresses 'uplink_ipv4_pool' must be set on this switch or 'downlink_ipv4_pool' on all the uplink switches."
            )

        return uplink_pool or downlink_pool
