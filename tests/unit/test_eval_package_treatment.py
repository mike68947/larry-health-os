"""Пакет оценки гипотезы несёт лечение и добавки (2026-11-07).

Консилиум 01.11.2026 выдвинул гипотезу «непроговорённые добавки объясняют сдвиги анализов»,
потому что пакет оценки содержал только анализы и заметки из чата — medications в нём не было.
Значения ниже вымышленные."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

_HYP = {"observation": "o", "mechanism": "m", "prediction": "p", "test": "t", "created_date": "2026-01-01"}


def _package(monkeypatch):
    import hypothesis_consilium_eval as hce
    import patient_context
    monkeypatch.setattr(hce.db, "get_lab_history", lambda days: [])
    monkeypatch.setattr(hce.db, "build_codraw_context", lambda: "")
    monkeypatch.setattr(patient_context, "reasoning_block", lambda: "")
    return hce._build_eval_data_package(_HYP)


def test_confirmed_current_and_ended_items_reach_the_package_with_dose_and_dates(db, monkeypatch):
    import treatment_db
    treatment_db.upsert_medication("Example-B6 50 mg", modality="supplement", status="active",
                                   start_date="2030-01-20", dosage="50 mg × 1", frequency="morning",
                                   source="manual:test", confirmation="manual", notes="reason: test")
    treatment_db.upsert_medication("Example-TMG 1 g", modality="supplement", status="discontinued",
                                   start_date="2030-01-28", end_date="2030-06-26", dosage="1 g × 1",
                                   source="manual:test", confirmation="manual")
    pkg = _package(monkeypatch)
    assert "ЛЕЧЕНИЕ И ДОБАВКИ (подтверждённые записи: 1 текущих, 1 законченных)" in pkg
    assert "• Example-B6 50 mg — 50 mg × 1 — morning — с 2030-01-20 — (reason: test)" in pkg
    assert "• Example-TMG 1 g — 1 g × 1 — 2030-01-28 → 2030-06-26" in pkg
    assert pkg.index("ЛЕЧЕНИЕ И ДОБАВКИ") < pkg.index("ЗАДАЧА КОНСИЛИУМА")


def test_unconfirmed_proposal_stays_out_and_empty_table_is_named_not_silent(db, monkeypatch):
    import treatment_db
    pkg = _package(monkeypatch)
    assert "подтверждённых записей нет" in pkg          # пусто ≠ «ничего не принимает»
    treatment_db.upsert_medication("Example-guess", modality="supplement", status="active",
                                   source="extractor", confirmation="proposed")
    pkg = _package(monkeypatch)
    assert "Example-guess" not in pkg and "подтверждённых записей нет" in pkg
