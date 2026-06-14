import json
from pathlib import Path

from glm_grabber.logger import JsonlLogger, redact_sensitive


def test_redact_sensitive_removes_nested_secret_values():
    data = {
        "phone": "18821363158",
        "headers": {"Authorization": "Bearer secret", "Cookie": "sid=secret"},
        "body": {"password": "plain", "safe": "ok"},
    }

    redacted = redact_sensitive(data)

    assert redacted["phone"] == "<redacted>"
    assert redacted["headers"]["Authorization"] == "<redacted>"
    assert redacted["headers"]["Cookie"] == "<redacted>"
    assert redacted["body"]["password"] == "<redacted>"
    assert redacted["body"]["safe"] == "ok"


def test_jsonl_logger_writes_redacted_event(tmp_path: Path):
    logger = JsonlLogger(tmp_path / "events.jsonl")

    logger.write("login_required", {"password": "secret", "status": "paused"})

    lines = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    event = json.loads(lines[0])
    assert event["event"] == "login_required"
    assert event["data"]["password"] == "<redacted>"
    assert event["data"]["status"] == "paused"
    assert "ts" in event
