"""День человека с Apple Watch без кольца Oura остаётся днём «Здоровья» (09.11.2026).

Живой случай: утренний конвейер зовёт migrate_all_json, и тот записывал любой дневной JSON как Oura.
Файл Apple Watch становился «днём Oura»: сон и ВСР часов ложились в raw на место кольца, а следующие
приходы «Здоровья» того же дня переставали обновлять шаги и биометрию. Значения вымышленные."""
from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.unit

_APPLE_DAY = {"steps": 1200, "active_kcal": 90.0, "hrv": {"avg": 30},
              "sleep": {"totalSleep": 3.1, "deep": 0.4, "source": "Example Watch"},
              "resting_heart_rate": {"value": 60}, "spo2": {"avg": 96.0}}


def test_shared_key_names_do_not_make_a_day_ouras():
    from metrics_db import has_oura_data
    assert not has_oura_data(_APPLE_DAY) and not has_oura_data({}) and not has_oura_data(None)
    assert has_oura_data({"readiness_score": 80})
    assert has_oura_data({"activity_score": 75, "steps": 5000})
    assert has_oura_data({"sleep": {"totalSleep": 7.0, "source": "Oura"}})


def test_migration_of_an_apple_day_file_keeps_the_day_apples(db, tmp_path, monkeypatch):
    import health_db
    day = "2030-03-06"
    (tmp_path / f"{day}.json").write_text(json.dumps(_APPLE_DAY))
    monkeypatch.setattr(health_db, "METRICS_DIR", tmp_path)
    health_db.migrate_all_json()
    row = db.fetchone("SELECT * FROM daily_metrics WHERE date=?", (day,))
    raw = json.loads(row["raw"])
    assert "sleep" not in raw and "hrv" not in raw             # место кольца в raw не занято часами
    assert raw["apple_health"]["hrv"] == 30 and row["hrv"] == 30 and row["steps"] == 1200
    health_db.upsert_metrics_from_json(day, {"steps": 9000, "hrv": {"avg": 41}}, source="AppleHealth")
    row = db.fetchone("SELECT * FROM daily_metrics WHERE date=?", (day,))
    assert (row["steps"], row["hrv"]) == (9000, 41)            # вечерний приход не молчит


def test_migration_of_an_oura_day_file_is_still_ouras(db, tmp_path, monkeypatch):
    import health_db
    day = "2030-03-07"
    (tmp_path / f"{day}.json").write_text(json.dumps(
        {"sleep": {"totalSleep": 7.0, "deep": 1.1, "source": "Oura"}, "readiness_score": 82, "steps": 5000}))
    monkeypatch.setattr(health_db, "METRICS_DIR", tmp_path)
    health_db.migrate_all_json()
    row = db.fetchone("SELECT * FROM daily_metrics WHERE date=?", (day,))
    assert (row["sleep_total"], row["readiness"], row["steps"]) == (7.0, 82, 5000)
    health_db.upsert_metrics_from_json(day, {"steps": 300, "hrv": {"avg": 50}}, source="AppleHealth")
    assert db.fetchone("SELECT steps FROM daily_metrics WHERE date=?", (day,))["steps"] == 5000


def test_day_file_follows_the_latest_apple_arrival_unless_the_ring_wrote_it(db, tmp_path, monkeypatch):
    import import_apple_health as ia
    monkeypatch.setattr(ia, "HEALTH_DATA", tmp_path)
    ia.save_daily_summaries({"2030-03-08": dict(_APPLE_DAY)}, mode="merge")
    ia.save_daily_summaries({"2030-03-08": {"hrv": {"avg": 41}, "sleep": {"totalSleep": 7.2}}}, mode="merge")
    doc = json.loads((tmp_path / "2030-03-08.json").read_text())
    assert doc["hrv"] == {"avg": 41} and doc["sleep"]["totalSleep"] == 7.2      # ночной приход не застыл
    (tmp_path / "2030-03-09.json").write_text(json.dumps({"hrv": {"avg": 22}, "readiness_score": 80}))
    ia.save_daily_summaries({"2030-03-09": {"hrv": {"avg": 50}, "steps": 300}}, mode="merge")
    doc = json.loads((tmp_path / "2030-03-09.json").read_text())
    assert doc["hrv"] == {"avg": 22} and doc["steps"] == 300                    # кольцо — хозяин своих ключей
    (tmp_path / "2030-03-10.json").write_text(json.dumps({"hrv": {"avg": 22, "source": "Oura"}}))
    ia.save_daily_summaries({"2030-03-10": {"hrv": {"avg": 50}}}, mode="merge")
    assert json.loads((tmp_path / "2030-03-10.json").read_text())["hrv"]["avg"] == 22   # блок с подписью кольца
