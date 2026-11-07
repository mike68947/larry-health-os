"""Канал /bug читает время через шов _time_inject — и это ПОВЕДЕНИЕ, а не только текст
(карточки report:87fc15 и integrity «контракт единого времени», 26–30.10).

Датчик time_contract_sensor судит текст: замена вызова часов на None для него тоже «чисто».
Здесь часы замораживаются set_test_clock, `now` в функции не передаётся, и проверяется граница
окна с обеих сторон: штамп очереди = замороженное время, застрявшее — строго после порога,
сбой журнала в окне 7 суток виден, за окном — нет. Значения выдуманы."""
import json
from datetime import datetime, timedelta, timezone

import pytest

import _time_inject

pytestmark = pytest.mark.unit

T0 = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def clock():
    _time_inject.set_test_clock(T0)
    yield
    _time_inject.clear_test_clock()


def test_outbox_stamp_and_stuck_follow_the_frozen_clock(clock, monkeypatch, tmp_path):
    import bug_outbox
    monkeypatch.setattr(bug_outbox, "_dir", lambda: tmp_path)
    bug_outbox._queue({"x": 1})
    item = json.loads((tmp_path / "bug_report_outbox.jsonl").read_text(encoding="utf-8"))
    assert datetime.fromisoformat(item["queued_at"]) == T0
    limit = bug_outbox.GIVE_UP + timedelta(hours=2)
    _time_inject.set_test_clock(T0 + limit)                   # ровно на пороге — ещё не застрял
    assert bug_outbox.stuck() == 0
    _time_inject.set_test_clock(T0 + limit + timedelta(minutes=1))
    assert bug_outbox.stuck() == 1


def test_fault_window_edges_follow_the_frozen_clock(clock, tmp_path):
    import bug_report
    win = timedelta(days=bug_report.FAULT_WINDOW_DAYS)
    rows = [{"ts": (T0 - win + timedelta(minutes=1)).isoformat(), "where": "inside"},
            {"ts": (T0 - win - timedelta(minutes=1)).isoformat(), "where": "outside"}]
    journal = tmp_path / "faults.jsonl"
    journal.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    assert [g["at"] for g in bug_report.faults_from_journal(journal)] == [["inside"]]
