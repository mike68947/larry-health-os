"""Установка без снимка CTCAE — штатное состояние, а не сбой (карточка report:5bf1da, 01.11).

Снимок CTCAE в публичную версию не входит (NOTICE.md), и _seed_safety_lab_thresholds без него
строк не сеет. До правки пустые лаб-строки safety_net у такой установки уходили в notify.fault
каждым процессом: у чужих установок (выпуск v0.2.5) — карточка /bug (ValueError в
safety_net.py:_load_lab_thresholds). Тот же класс, что EFLM (test_eflm_absent_not_fault).
Теперь: без снимка — ни одного fault, оператору одна строка недельной сводки ОДИН раз;
со снимком и пустой БД — громкий сбой, как был.

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
    monkeypatch.setattr(rules_db, "get_absolute_thresholds", lambda *a, **k: [])
    return got


def _weekly_lines():
    p = notify.weekly_path()
    return [json.loads(x)["text"] for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def test_no_snapshot_is_not_a_fault_and_operator_told_once(faults, monkeypatch, tmp_path):
    monkeypatch.setattr(norm_documents, "CTCAE_SNAPSHOT", tmp_path / "absent" / "ctcae.json")
    monkeypatch.setattr(sn, "_FALLBACK_LAB", sn._snapshot_lab_rows())   # как при импорте без снимка
    for _ in range(3):                       # три прогона = три «дня» одной установки
        sn._FALLBACK_ALERTED.clear()
        assert sn._load_lab_thresholds() == {}
    assert faults == [], f"нет снимка CTCAE — не сбой, а ушло в /bug: {faults}"
    lines = _weekly_lines()
    assert len(lines) == 1, f"оператору — ровно одна строка, а не каждый день: {lines}"
    assert "--fetch-ctcae" in lines[0], "строка не говорит, как включить"


def test_failed_journal_write_does_not_silence_the_note(faults, monkeypatch, tmp_path):
    """Ревью ночного ремонта 01.11 (P1): отметка ставилась и при отказе записи журнала —
    единственное сообщение пропадало навсегда. Теперь отметка — только по квитанции записи."""
    monkeypatch.setattr(norm_documents, "CTCAE_SNAPSHOT", tmp_path / "absent" / "ctcae.json")
    monkeypatch.setattr(sn, "_FALLBACK_LAB", sn._snapshot_lab_rows())
    tries = []
    monkeypatch.setattr(notify, "weekly", lambda line: tries.append(line) or False)
    sn._load_lab_thresholds()
    sn._load_lab_thresholds()
    assert len(tries) == 2, "после отказа записи отметка поставлена — повтора нет"
    assert not (notify.weekly_path().parent / sn._CTCAE_ABSENT_MARK).exists()


def test_snapshot_present_empty_db_still_faults(faults, monkeypatch, tmp_path):
    """Не ломать владельца: снимок есть, а порогов в БД нет — это настоящая поломка сида."""
    snap = tmp_path / "ctcae.json"
    snap.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(norm_documents, "CTCAE_SNAPSHOT", snap)
    sn._load_lab_thresholds()
    assert any("lab_abs" in t for t in faults), "пустая БД при снимке перестала быть сбоем"
    assert _weekly_lines() == []
