"""Установка без снимка EFLM — штатное состояние, а не сбой (нить eflm-install-fetch, 31.10).

Снимок EFLM в репозиторий не едет, а установка не качает его сама (условия EFLM — NOTICE.md).
До правки пустая lab_trend_thresholds у такой установки уходила в notify.fault каждым процессом:
у чужих установок (выпуск v0.2.5) — ежедневная карточка /bug, отпечаток 00c93e
(ValueError в safety_net.py:_load_lab_trend_thresholds). Теперь: без снимка — ни одного fault,
оператору одна строка недельной сводки ОДИН раз; со снимком и пустой БД — громкий сбой, как был.

Снимок подменяется путём (§20): зелёный не зависит от того, лежит ли у машины настоящий файл.
"""
from __future__ import annotations

import json

import pytest

import notify
import norm_documents
import rules_db
import safety_net as sn

pytestmark = pytest.mark.unit


@pytest.fixture
def faults(monkeypatch):
    got = []
    monkeypatch.setattr(notify, "fault", lambda tech, *a, **k: got.append(tech))
    sn._FALLBACK_ALERTED.clear()
    monkeypatch.setattr(rules_db, "get_lab_trend_thresholds", lambda *a, **k: [])
    return got


def _weekly_lines():
    p = notify.weekly_path()
    return [json.loads(x)["text"] for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def test_no_snapshot_is_not_a_fault_and_operator_told_once(faults, monkeypatch, tmp_path):
    monkeypatch.setattr(norm_documents, "EFLM_SNAPSHOT", tmp_path / "absent" / "eflm_bv.json")
    monkeypatch.setattr(sn, "_FALLBACK_LAB_TREND", sn._snapshot_trend_rows())   # как при импорте без снимка
    for _ in range(3):                       # три прогона = три «дня» одной установки
        sn._FALLBACK_ALERTED.clear()         # дедуп процесса не спасает: процесс каждый день новый
        assert sn._load_lab_trend_thresholds() == {}
    assert faults == [], f"нет снимка EFLM — не сбой, а ушло в /bug: {faults}"
    lines = _weekly_lines()
    assert len(lines) == 1, f"оператору — ровно одна строка, а не каждый день: {lines}"
    assert "--fetch-eflm" in lines[0], "строка не говорит, как включить"


def test_snapshot_present_empty_db_still_faults(faults, monkeypatch, tmp_path):
    """Не ломать владельца: снимок есть, а порогов в БД нет — это настоящая поломка сида."""
    snap = tmp_path / "eflm_bv.json"
    snap.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(norm_documents, "EFLM_SNAPSHOT", snap)
    sn._load_lab_trend_thresholds()
    assert any("lab_trend" in t for t in faults), "пустая БД при снимке перестала быть сбоем"
    assert _weekly_lines() == []
