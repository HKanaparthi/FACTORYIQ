"""
asyncua OPC UA server for FactoryIQ simulation.

Node hierarchy follows ISA-95:
  Objects/FactoryIQ/CharlotteSite/ProductionArea/Line1/<AssetID>/<TagName>

The server publishes all tag values at 1-second intervals.
Tags affected by stop_publishing faults retain their last value and quality.
Tags affected by force_quality faults publish with the specified OPC UA status code.
"""

import asyncio
import logging
import time
from typing import Optional

from asyncua import Server, ua
from asyncua.ua import DataValue, StatusCode, Variant, VariantType

from tag_model import TAGS, ASSET_PATH_PREFIX, OPC_QUALITY_GOOD, OPC_QUALITY_BAD
from fault_state import FaultState
from physics import compute_reading

logger = logging.getLogger(__name__)

PUBLISH_INTERVAL_S = 1.0


class OPCUAServer:
    def __init__(self, endpoint: str, fault_state: FaultState) -> None:
        self._endpoint = endpoint
        self._fault_state = fault_state
        self._server: Optional[Server] = None
        self._nodes: dict[tuple[str, str], object] = {}
        self._last_values: dict[tuple[str, str], float] = {}

    async def start(self) -> None:
        self._server = Server()
        await self._server.init()
        self._server.set_endpoint(self._endpoint)
        self._server.set_server_name("FactoryIQ Simulator")

        uri = "urn:factoryiq:simulator"
        idx = await self._server.register_namespace(uri)

        objects = self._server.nodes.objects
        # Build ISA-95 folder hierarchy
        parts = ASSET_PATH_PREFIX.split("/")
        parent = objects
        for part in parts:
            parent = await parent.add_folder(idx, part)

        # Create asset folders and tag variable nodes
        asset_folders: dict[str, object] = {}
        for tag in TAGS:
            if tag.asset_id not in asset_folders:
                asset_folders[tag.asset_id] = await parent.add_folder(idx, tag.asset_id)
            folder = asset_folders[tag.asset_id]
            node = await folder.add_variable(
                idx,
                tag.tag_name,
                ua.Variant(tag.nominal, ua.VariantType.Double),
            )
            await node.set_writable(False)
            self._nodes[(tag.asset_id, tag.tag_name)] = node
            self._last_values[(tag.asset_id, tag.tag_name)] = tag.nominal

        logger.info("OPC UA server started at %s with %d nodes", self._endpoint, len(self._nodes))
        async with self._server:
            await self._publish_loop()

    async def _publish_loop(self) -> None:
        rng_per_tag = {(t.asset_id, t.tag_name): __import__("random").Random() for t in TAGS}
        while True:
            start = time.monotonic()
            active_faults = await self._fault_state.get_active()

            for tag in TAGS:
                key = (tag.asset_id, tag.tag_name)
                node = self._nodes[key]
                value, quality_code = compute_reading(tag, active_faults, rng_per_tag[key])

                if value is None:
                    # stop_publishing fault: do not update the node, retain last value
                    continue

                self._last_values[key] = value
                dv = DataValue(
                    Value=Variant(value, VariantType.Double),
                    StatusCode_=StatusCode(quality_code),
                )
                await node.set_value(dv)

            elapsed = time.monotonic() - start
            await asyncio.sleep(max(0.0, PUBLISH_INTERVAL_S - elapsed))
