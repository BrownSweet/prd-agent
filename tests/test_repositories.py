from __future__ import annotations

import json
from datetime import datetime, timezone

from prd_agent.models import JobStatus
from prd_agent.repositories import _json_ready


def test_json_ready_serializes_datetimes_for_mysql_json_columns() -> None:
    value = {
        "createdAt": datetime(2026, 6, 16, 8, 30, tzinfo=timezone.utc),
        "status": JobStatus.SUCCEEDED,
        "items": [datetime(2026, 6, 16, 8, 31)],
    }

    ready = _json_ready(value)

    assert ready == {
        "createdAt": "2026-06-16T08:30:00+00:00",
        "status": "succeeded",
        "items": ["2026-06-16T08:31:00+00:00"],
    }
    json.dumps(ready)
