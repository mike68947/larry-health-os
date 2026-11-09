"""Энергия из Health Auto Export: кДж переводятся в ккал (09.11.2026).

Живой случай: телефон отдавал active_energy в кДж, разборщик складывал числа в active_kcal как есть —
день с 1570 кДж читался как 1570 ккал. Значения ниже вымышленные."""
from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.unit


def _day(tmp_path, units):
    import import_apple_health as ia
    f = tmp_path / f"export_{units}.json"
    f.write_text(json.dumps({"data": {"metrics": [
        {"name": "active_energy", "units": units, "data": [
            {"date": "2030-03-01 10:00:00 +0100", "qty": 418.4},
            {"date": "2030-03-01 11:00:00 +0100", "qty": 418.4}]},
        {"name": "basal_energy_burned", "units": units, "data": [
            {"date": "2030-03-01 10:00:00 +0100", "qty": 4184}]}]}}))
    return ia.process_hae_json(f)["2030-03-01"]


def test_kilojoules_become_kilocalories(tmp_path):
    d = _day(tmp_path, "kJ")
    assert (d["active_kcal"], d["basal_kcal"]) == (200.0, 1000.0)      # 836.8 кДж и 4184 кДж


def test_kilocalories_pass_through_unchanged(tmp_path):
    d = _day(tmp_path, "kcal")
    assert (d["active_kcal"], d["basal_kcal"]) == (836.8, 4184.0)
