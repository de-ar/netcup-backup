from datetime import UTC, datetime

from netcup_backup.netcup.snapshots import Snapshot, _extract_task_id, now_snapshot_name


def test_snapshot_parses_iso_timestamp():
    raw = {"name": "s1", "creationTime": "2026-05-12T10:00:00Z"}
    s = Snapshot.from_api(raw)
    assert s.name == "s1"
    assert s.creation_time == datetime(2026, 5, 12, 10, 0, tzinfo=UTC)


def test_snapshot_falls_back_to_now():
    s = Snapshot.from_api({"name": "s2"})
    assert s.name == "s2"
    assert s.creation_time.tzinfo is not None


def test_extract_task_id_variants():
    assert _extract_task_id({"taskId": "abc"}) == "abc"
    assert _extract_task_id({"task_id": "def"}) == "def"
    assert _extract_task_id({"id": "ghi"}) == "ghi"
    assert _extract_task_id({"x": 1}) is None
    assert _extract_task_id("not a dict") is None


def test_now_snapshot_name_format():
    name = now_snapshot_name(prefix="auto")
    assert name.startswith("auto-")
    assert len(name) == len("auto-") + 15  # YYYYMMDD-HHMMSS
