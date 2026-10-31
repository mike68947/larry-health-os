"""Markdown (.md) во входящих: анализы, заключения врачей, список лекарств — текстом, без PDF.

Один формат, два маршрута: текст уходит разбору документов как есть, распознавателю анализов —
страницей, отрендеренной MuPDF (как PDF). Квитанция бота обещает оба разбора.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

MD = (
    "# Lab results 12.03.2026\n\n| Test | Value | Unit | Ref |\n|---|---|---|---|\n"
    "| Ferritin | 15.2 | ng/mL | 30-400 |\n\nФерритин 15.2 нг/мл — кириллица\n"
    "## Meds\n- Metformin 500 mg 2x/day\n"
)


def test_md_is_taken_by_both_readers():
    import import_medical_events as ime
    from lab_intake_watcher import DOC_EXTS
    assert ".md" in DOC_EXTS and ".md" in ime.DOC_EXTS


def test_md_text_is_read_verbatim(tmp_path):
    import import_all
    import import_medical_events as ime
    f = tmp_path / "labs.md"
    f.write_text(MD, encoding="utf-8")
    assert import_all.extract_text(f) == MD
    assert ime.extract_text(f) == MD


def test_md_renders_as_one_page_for_the_recognizer(tmp_path):
    import lab_recognizer
    f = tmp_path / "labs.md"
    f.write_text(MD, encoding="utf-8")
    pages = lab_recognizer._render_pages(f)
    assert len(pages) == 1 and pages[0][:2] == b"\xff\xd8"   # JPEG


def test_receipt_promises_labs_and_conclusions_for_md():
    from handlers.messages import _receipt_text
    t = _receipt_text("meds.md")
    assert "Анализы распознаю" in t and "из заключения врача извлеку диагнозы" in t
