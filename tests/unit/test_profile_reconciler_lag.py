"""Датчик профиля краснеет на ОТСТАВШЕМ ремонтнике, а не на замере, пришедшем после его прогона.

Синтетика (значения выдуманы): ремонтник ходит раз в сутки утром, ночная проверка — позже.
Сегодняшнее взвешивание сводит завтрашний прогон — расхождение по нему штатное (карточка
2026-11-01 «проверь джобу» была ложной). Вчерашний замер прогон уже видел — расхождение по нему
значит, что прогон не состоялся. Судится датой живого значения, не штампом прогона: ревью
ночного ремонта показало, что окно «пульс свежее 26 ч» скрывает пропущенный прогон, общий штамп
не доказывает сверку ключа, а будущий штамп выключал датчик.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date
from pathlib import Path

import pytest

import profile_reconciler as pr

pytestmark = pytest.mark.unit

TODAY = date(2021, 3, 9)


def _db(stored: str, weights, stamp="2021-03-09T06:00:01"):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE daily_metrics (date TEXT PRIMARY KEY, weight REAL)")
    conn.executemany("INSERT INTO daily_metrics VALUES (?,?)", weights)
    conn.execute("CREATE TABLE events (event_type TEXT, effective_date TEXT, "
                 "location TEXT, notes TEXT)")
    conn.execute("CREATE TABLE patient_profile (key TEXT PRIMARY KEY, value_text TEXT, "
                 "value_json TEXT, category TEXT, updated_at TEXT, updated_by TEXT)")
    conn.execute("INSERT INTO patient_profile (key, value_text, updated_at, updated_by) "
                 "VALUES ('identity.weight_kg', ?, ?, 'profile_reconciler')", (stored, stamp))
    return conn


def test_todays_measurement_waits_for_tomorrows_run():
    """Профиль сведён на вчерашнем замере, сегодня пришёл новый — расхождение есть, долга нет."""
    conn = _db("70.1 (замер 2021-03-08)", [("2021-03-08", 70.1), ("2021-03-09", 69.7)])
    assert pr.drift(conn) == ["identity.weight_kg"]
    assert pr.lagging(conn, TODAY) == []


def test_missed_run_is_caught_even_with_a_fresh_looking_stamp():
    """Ревью п. 1 и 3: сегодняшний прогон пропущен, штамп вчерашний (или из будущего) —
    вчерашний замер не сведён, ключ назван. Штамп в суждении не участвует."""
    weights = [("2021-03-07", 70.4), ("2021-03-08", 70.1)]
    for stamp in ("2021-03-08T06:00:01", "2031-01-01T00:00:00", None):
        conn = _db("70.4 (замер 2021-03-07)", weights, stamp)
        assert pr.lagging(conn, TODAY) == ["identity.weight_kg"], stamp


def test_in_sync_is_silent():
    conn = _db("69.7 (замер 2021-03-09)", [("2021-03-09", 69.7)])
    assert pr.lagging(conn, TODAY) == []


def test_negative_control_today_is_load_bearing():
    """ИСПОЛНЕННЫЙ негативный контроль: тот же сегодняшний замер, но «сегодня» — завтра:
    обязан покраснеть; иначе зелёный первого теста неотличим от датчика, молчащего всегда."""
    conn = _db("70.1 (замер 2021-03-08)", [("2021-03-08", 70.1), ("2021-03-09", 69.7)])
    assert pr.lagging(conn, date(2021, 3, 10)) == ["identity.weight_kg"]


def test_the_sensor_asks_lagging_not_drift():
    """Ревью п. 5: тесты выше зовут lagging() напрямую — откат датчика на drift() их не
    краснит. import integrity_tests исполняет весь ночной монитор, поэтому сторож — по
    источнику: тело check_profile_reconciler_fresh судит через lagging(…, сегодня)."""
    src = (Path(__file__).resolve().parents[2] / "integrity_tests.py").read_text(encoding="utf-8")
    body = src[src.index("def check_profile_reconciler_fresh"):]
    body = body[:re.search(r"\n(def |check\()", body).start()]
    assert "_pr.lagging(conn, _today())" in body and "_pr.drift(" not in body
