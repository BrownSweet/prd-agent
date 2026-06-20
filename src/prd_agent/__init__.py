"""PRD Agent package."""

import os

# The CLI is designed to work offline except for the configured LLM provider.
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")

try:
    from crewai.events.listeners.tracing.utils import (
        set_suppress_tracing_messages,
    )
except Exception:
    pass
else:
    set_suppress_tracing_messages(True)

__version__ = "0.1.0"
