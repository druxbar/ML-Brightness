"""Guard hacs.json against keys HACS rejects (runtime check for CI + local)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

# https://hacs.xyz/docs/publish/start/#hacsjson
_ALLOWED_HACS_JSON_KEYS = frozenset(
    {
        "name",
        "content_in_root",
        "country",
        "filename",
        "hide_default_branch",
        "homeassistant",
        "hacs",
        "persistent_directory",
        "render_readme",
        "zip_release",
    }
)

_DEBUG_LOG = Path(__file__).resolve().parents[1] / ".cursor" / "debug-57f3c2.log"


def _agent_ndjson(hypothesis_id: str, message: str, data: dict) -> None:
    # #region agent log
    _DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "sessionId": "57f3c2",
        "hypothesisId": hypothesis_id,
        "location": "tests/test_hacs_json.py",
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    with _DEBUG_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, default=str) + "\n")

    # #endregion


@pytest.fixture
def hacs_data() -> dict:
    root = Path(__file__).resolve().parents[1]
    path = root / "hacs.json"
    raw = path.read_text(encoding="utf-8")
    return json.loads(raw)


def test_hacs_json_no_unknown_keys(hacs_data: dict) -> None:
    """H1: domains (or other extras) in local hacs.json → HACS hacsjson failure."""
    keys = set(hacs_data)
    extras = keys - _ALLOWED_HACS_JSON_KEYS
    _agent_ndjson(
        "H1",
        "local_hacs_json_keys",
        {"keys": sorted(keys), "extras": sorted(extras), "has_domains": "domains" in hacs_data},
    )
    assert not extras, f"hacs.json has keys HACS rejects: {sorted(extras)}"
    _agent_ndjson(
        "H2",
        "hacs_action_validates_remote",
        {
            "note": "If GitHub HACS Action still shows domains in hacs.json, origin/main is stale vs this checkout; push commits.",
        },
    )


def test_hacs_json_has_name(hacs_data: dict) -> None:
    """Sanity: required name present."""
    _agent_ndjson("H3", "hacs_json_name", {"name": hacs_data.get("name")})
    assert hacs_data.get("name"), "hacs.json must set name"
