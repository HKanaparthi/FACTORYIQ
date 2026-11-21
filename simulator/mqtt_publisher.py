"""
MQTT publisher for FactoryIQ simulation.

Publishes all tag values every second using Sparkplug B topic convention:
  spBv1.0/{group_id}/{message_type}/{edge_node_id}/{device_id}

Payload format: JSON (documented simplification — full Sparkplug B uses protobuf).
The JSON structure mirrors the Sparkplug B metric schema for compatibility.

DBIRTH (device birth) messages are sent on startup.
DDATA messages are sent every second thereafter.
Tags affected by stop_publishing faults are omitted from that cycle's DDATA message.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

import aiomqtt

from tag_model import TAGS, ASSET_PATH_PREFIX, ASSET_TAGS
from fault_state import FaultState
from physics import compute_reading, should_trigger_alarm

logger = logging.getLogger(__name__)

SPARKPLUG_GROUP = "FactoryIQ"
SPARKPLUG_EDGE_NODE = "SimNode"
PUBLISH_INTERVAL_S = 1.0


def _ddata_topic(device_id: str) -> str:
    return f"spBv1.0/{SPARKPLUG_GROUP}/DDATA/{SPARKPLUG_EDGE_NODE}/{device_id}"


def _dbirth_topic(device_id: str) -> str:
    return f"spBv1.0/{SPARKPLUG_GROUP}/DBIRTH/{SPARKPLUG_EDGE_NODE}/{device_id}"


def _alarm_topic() -> str:
    return f"spBv1.0/{SPARKPLUG_GROUP}/ALARM/{SPARKPLUG_EDGE_NODE}"


def _make_payload(
    device_id: str,
    metrics: list[dict],
    seq: int,
    message_type: str = "DDATA",
) -> bytes:
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    payload = {
        "seq": seq,
        "timestamp": now_ms,
        "message_type": message_type,
        "device_id": device_id,
        "is_simulated": True,
        "metrics": metrics,
    }
    return json.dumps(payload).encode()


class MQTTPublisher:
    def __init__(self, host: str, port: int, fault_state: FaultState) -> None:
        self._host = host
        self._port = port
        self._fault_state = fault_state
        self._seq = 0

    async def run(self) -> None:
        # Reconnect loop — retries on connection failure
        while True:
            try:
                await self._connect_and_publish()
            except aiomqtt.MqttError as e:
                logger.warning("MQTT connection lost: %s — retrying in 3s", e)
                await asyncio.sleep(3)

    async def _connect_and_publish(self) -> None:
        async with aiomqtt.Client(hostname=self._host, port=self._port) as client:
            logger.info("MQTT connected to %s:%d", self._host, self._port)
            await self._send_births(client)
            await self._publish_loop(client)

    async def _send_births(self, client: aiomqtt.Client) -> None:
        assets = set(t.asset_id for t in TAGS)
        for asset_id in sorted(assets):
            tags_for_asset = [t for t in TAGS if t.asset_id == asset_id]
            metrics = [
                {
                    "name": t.tag_name,
                    "value": t.nominal,
                    "datatype": "Double",
                    "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
                    "properties": {
                        "quality_code": 0x00000000,
                        "quality_label": "Good",
                        "unit": t.unit,
                        "opc_node_path": f"{ASSET_PATH_PREFIX}/{asset_id}/{t.tag_name}",
                        "alarm_high": t.alarm_high,
                        "alarm_critical": t.alarm_critical,
                    },
                }
                for t in tags_for_asset
            ]
            payload = _make_payload(asset_id, metrics, self._seq, "DBIRTH")
            self._seq += 1
            await client.publish(_dbirth_topic(asset_id), payload, qos=0, retain=False)

    async def _publish_loop(self, client: aiomqtt.Client) -> None:
        rng_per_tag = {(t.asset_id, t.tag_name): __import__("random").Random() for t in TAGS}

        while True:
            loop_start = time.monotonic()
            active_faults = await self._fault_state.get_active()

            # Group tags by asset_id for per-device DDATA messages
            asset_metrics: dict[str, list[dict]] = {t.asset_id: [] for t in TAGS}
            alarms: list[dict] = []

            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

            for tag in TAGS:
                key = (tag.asset_id, tag.tag_name)
                value, quality_code = compute_reading(tag, active_faults, rng_per_tag[key])

                if value is None:
                    # stop_publishing fault — omit this metric from the message
                    continue

                from tag_model import quality_label
                metric = {
                    "name": tag.tag_name,
                    "value": value,
                    "datatype": "Double",
                    "timestamp": now_ms,
                    "properties": {
                        "quality_code": quality_code,
                        "quality_label": quality_label(quality_code),
                        "unit": tag.unit,
                    },
                }
                asset_metrics[tag.asset_id].append(metric)

                # Check for alarm condition
                severity = should_trigger_alarm(tag, value, quality_code)
                if severity:
                    from tag_model import ALARM_MESSAGES
                    message = ALARM_MESSAGES.get(key, f"{tag.asset_id}/{tag.tag_name} threshold exceeded")
                    alarms.append({
                        "asset_id": tag.asset_id,
                        "tag_name": tag.tag_name,
                        "severity": severity,
                        "message": message,
                        "value": value,
                        "threshold": tag.alarm_high,
                        "timestamp": now_ms,
                        "is_simulated": True,
                    })

            # Publish per-device DDATA messages
            for asset_id, metrics in asset_metrics.items():
                if not metrics:
                    continue
                payload = _make_payload(asset_id, metrics, self._seq)
                self._seq += 1
                await client.publish(_ddata_topic(asset_id), payload, qos=0, retain=False)

            # Publish alarms (deduplicated — one alarm per asset per threshold crossing per second is acceptable)
            for alarm in alarms:
                payload = json.dumps(alarm).encode()
                await client.publish(_alarm_topic(), payload, qos=1, retain=False)

            elapsed = time.monotonic() - loop_start
            await asyncio.sleep(max(0.0, PUBLISH_INTERVAL_S - elapsed))
