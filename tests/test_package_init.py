from __future__ import annotations

import os

import prd_agent  # noqa: F401
from crewai.events.listeners.tracing.utils import should_suppress_tracing_messages


def test_crewai_tracing_is_silent_by_default() -> None:
    assert os.environ["CREWAI_DISABLE_TELEMETRY"] == "true"
    assert os.environ["CREWAI_TRACING_ENABLED"] == "false"
    assert should_suppress_tracing_messages() is True
