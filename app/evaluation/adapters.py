"""
FactoryIQ Milestone 5 — Agent Adapter Interface.

Three adapter types:
  ScriptedAdapter        — deterministic rule-based runner, no AI API calls
  RecordedTraceAdapter   — stub for pre-recorded traces (not yet implemented)
  LiveAdapter            — permanently disabled; would call real Claude API

Security: LiveAdapter raises ValueError unless ALLOW_LIVE_EVAL=true.
No paid API calls are made in ScriptedAdapter under any circumstances.
"""

from __future__ import annotations

import abc
import asyncio
import os


class BaseAdapter(abc.ABC):
    """Abstract base for all agent adapters used by the evaluation harness."""

    @abc.abstractmethod
    async def run(
        self,
        investigation_id: str,
        asset_id: str,
        event_queue: asyncio.Queue | None,
    ) -> None:
        """Execute the investigation. Must leave the DB row in a terminal state."""
        ...

    @property
    @abc.abstractmethod
    def adapter_type(self) -> str:
        """Canonical string identifier stored in eval_runs.adapter_type."""
        ...


class ScriptedAdapter(BaseAdapter):
    """
    Wraps run_scripted_investigation — fully deterministic, no paid API calls.
    Safe for unlimited automated evaluation runs.
    """

    @property
    def adapter_type(self) -> str:
        return "scripted"

    async def run(
        self,
        investigation_id: str,
        asset_id: str,
        event_queue: asyncio.Queue | None,
    ) -> None:
        from agent.runner import run_scripted_investigation
        await run_scripted_investigation(
            investigation_id=investigation_id,
            asset_id=asset_id,
            trigger_alarm_id=None,
            event_queue=event_queue,
        )


class RecordedTraceAdapter(BaseAdapter):
    """
    Replays a pre-recorded sequence of tool call + result pairs.
    Not yet implemented — stub reserves the interface for future work.
    """

    def __init__(self, trace_id: str) -> None:
        self._trace_id = trace_id

    @property
    def adapter_type(self) -> str:
        return "recorded"

    async def run(
        self,
        investigation_id: str,
        asset_id: str,
        event_queue: asyncio.Queue | None,
    ) -> None:
        raise NotImplementedError(
            "RecordedTraceAdapter is not yet implemented. "
            "Use ScriptedAdapter for automated evaluation."
        )


class LiveAdapter(BaseAdapter):
    """
    Would invoke the real Claude API. Disabled unless ALLOW_LIVE_EVAL=true.
    Exists only to reserve the interface; raises ValueError on run().
    """

    @property
    def adapter_type(self) -> str:
        return "live"

    async def run(
        self,
        investigation_id: str,
        asset_id: str,
        event_queue: asyncio.Queue | None,
    ) -> None:
        raise ValueError(
            "LiveAdapter is disabled. Set ALLOW_LIVE_EVAL=true to enable. "
            "This will make paid Anthropic API calls."
        )


def get_adapter(adapter_type: str) -> BaseAdapter:
    """Return the named adapter or raise ValueError."""
    if adapter_type == "scripted":
        return ScriptedAdapter()
    if adapter_type == "recorded":
        raise ValueError("RecordedTraceAdapter is not yet implemented.")
    if adapter_type == "live":
        if os.environ.get("ALLOW_LIVE_EVAL", "false").lower() != "true":
            raise ValueError(
                "LiveAdapter is disabled. Set ALLOW_LIVE_EVAL=true to enable. "
                "This will make paid Anthropic API calls."
            )
        return LiveAdapter()
    raise ValueError(f"Unknown adapter_type: {adapter_type!r}. Must be 'scripted'.")
