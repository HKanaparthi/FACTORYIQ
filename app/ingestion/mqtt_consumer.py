"""
MQTT consumer — subscribes to Sparkplug B DDATA and ALARM topics and writes
to TimescaleDB.

Single ingestion source rule: this is the ONLY write path into the telemetry table.
OPC UA data is available for direct query but is not ingested here.

Deduplication: ON CONFLICT DO NOTHING on (asset_id, tag_name, timestamp).
If the same (asset, tag, timestamp) arrives twice (e.g. from a retained message),
the second insert is silently dropped.

Sparkplug B topic pattern:
  DDATA: spBv1.0/FactoryIQ/DDATA/SimNode/<device_id>
  ALARM: spBv1.0/FactoryIQ/ALARM/SimNode
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone

import aiomqtt

from db import get_pool

logger = logging.getLogger(__name__)

DDATA_TOPIC = "spBv1.0/FactoryIQ/DDATA/SimNode/#"
ALARM_TOPIC  = "spBv1.0/FactoryIQ/ALARM/SimNode"


async def _write_telemetry(pool, asset_id: str, metrics: list[dict], now_ms: int) -> None:
    rows = []
    for m in metrics:
        props = m.get("properties", {})
        ts = datetime.fromtimestamp(m.get("timestamp", now_ms) / 1000, tz=timezone.utc)
        rows.append((
            asset_id,
            m["name"],
            ts,
            float(m["value"]),
            int(props.get("quality_code", 0)),
            props.get("quality_label", "Good"),
            props.get("unit", ""),
        ))

    if not rows:
        return

    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO telemetry
              (asset_id, tag_name, timestamp, value, opc_quality_code, opc_quality_label, unit,
               source, is_simulated)
            VALUES ($1, $2, $3, $4, $5, $6, $7, 'MQTT_SPARKPLUG', TRUE)
            ON CONFLICT DO NOTHING
            """,
            rows,
        )
        # Update tag_health for each tag we just received
        for asset_id_r, tag_name_r, ts_r, *_ in rows:
            await conn.execute(
                """
                INSERT INTO tag_health
                  (asset_id, tag_name, last_update, freshness_status,
                   staleness_threshold_seconds, updated_at)
                VALUES ($1, $2, $3, 'FRESH', $4, NOW())
                ON CONFLICT (asset_id, tag_name) DO UPDATE
                  SET last_update = EXCLUDED.last_update,
                      freshness_status = 'FRESH',
                      updated_at = NOW()
                """,
                asset_id_r,
                tag_name_r,
                ts_r,
                int(os.environ.get("TAG_STALENESS_THRESHOLD_SECONDS", "10")),
            )


async def _write_alarm(pool, alarm: dict) -> None:
    asset_id = alarm.get("asset_id", "UNKNOWN")
    alarm_type = alarm.get("tag_name", "UNKNOWN")

    async with pool.acquire() as conn:
        # Dedup: suppress repeat alarms for the same sustained condition.
        # Allow a new alarm through only after a 5-minute cooldown window.
        existing = await conn.fetchval(
            """
            SELECT 1 FROM alarms
            WHERE asset_id = $1
              AND alarm_type = $2
              AND acknowledged_at IS NULL
              AND triggered_at >= NOW() - INTERVAL '5 minutes'
            LIMIT 1
            """,
            asset_id,
            alarm_type,
        )
        if existing:
            return

        await conn.execute(
            """
            INSERT INTO alarms
              (asset_id, alarm_type, severity, message, raw_value, threshold, is_simulated)
            VALUES ($1, $2, $3, $4, $5, $6, TRUE)
            """,
            asset_id,
            alarm_type,
            alarm.get("severity", "HIGH"),
            alarm.get("message", ""),
            alarm.get("value"),
            alarm.get("threshold"),
        )


async def run_consumer() -> None:
    mqtt_host = os.environ.get("MQTT_HOST", "mosquitto")
    mqtt_port = int(os.environ.get("MQTT_PORT", "1883"))

    while True:
        try:
            async with aiomqtt.Client(hostname=mqtt_host, port=mqtt_port) as client:
                logger.info("MQTT consumer connected to %s:%d", mqtt_host, mqtt_port)
                await client.subscribe(DDATA_TOPIC, qos=0)
                await client.subscribe(ALARM_TOPIC, qos=1)

                async for message in client.messages:
                    topic = str(message.topic)
                    try:
                        payload = json.loads(message.payload.decode())
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        logger.warning("Unparseable MQTT message on topic %s", topic)
                        continue

                    pool = get_pool()
                    if "/DDATA/" in topic:
                        # Device ID is the last segment of the topic
                        device_id = topic.split("/")[-1]
                        await _write_telemetry(
                            pool,
                            device_id,
                            payload.get("metrics", []),
                            payload.get("timestamp", 0),
                        )
                    elif "/ALARM/" in topic:
                        await _write_alarm(pool, payload)

        except aiomqtt.MqttError as e:
            logger.warning("MQTT consumer lost connection: %s — retrying in 3s", e)
            await asyncio.sleep(3)
        except Exception:
            logger.exception("Unexpected error in MQTT consumer — retrying in 5s")
            await asyncio.sleep(5)
