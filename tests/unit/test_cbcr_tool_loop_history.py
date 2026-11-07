"""Карточка 26.10 (survivorship_curator у партнёра, 400 дважды за ночь).

Полный текст ошибки из survivorship_partner.log: «messages.1.content.1.text.parsed_output:
Extra inputs are not permitted». Ход ассистента в tool-loop возвращался в историю как
`model_dump()` ответа SDK, а у ParsedTextBlock (anthropic 0.92) там есть `parsed_output: None`.
Здесь блоки — НАСТОЯЩИЕ классы SDK, и проверяются оба цикла (генерация и критика) и
сохранность смысловых полей целиком. Значения выдуманы."""
from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

anthropic_types = pytest.importorskip("anthropic.types")
import cbcr_hypothesis as ch

pytestmark = pytest.mark.unit

THINK = anthropic_types.ThinkingBlock(type="thinking", thinking="…", signature="sig-1")
TOOL = anthropic_types.ToolUseBlock(type="tool_use", id="toolu_1", name="read_cbcr_concept",
                                    input={"name": "Bias", "opt": None})


class _Stop(Exception):
    pass


class _FakeClient:
    """Первый ответ — шаг с инструментом; на втором запросе запоминаем историю и стоп."""
    def __init__(self, first):
        self.first, self.sent = first, []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        if self.first is not None:
            r, self.first = self.first, None
            return SimpleNamespace(content=r, stop_reason="tool_use", usage=None)
        self.sent.append(copy.deepcopy(kw["messages"]))
        raise _Stop


def _text(t):
    return anthropic_types.ParsedTextBlock(type="text", text=t)


def _run(loop, client, monkeypatch):
    monkeypatch.setattr(ch, "_get_client", lambda: client)
    monkeypatch.setattr(ch, "_execute_tool_call", lambda n, i: "result")
    if loop == "generate":
        monkeypatch.setattr(ch, "_load_manifest", lambda: "manifest")
        monkeypatch.setattr(ch, "_build_patient_context_block", lambda: "")
        call = lambda: ch.generate_hypothesis({"trigger": "survivorship", "summary": "s", "details": {}})
    else:
        call = lambda: ch.critique_hypothesis({"observation": "o"})
    with pytest.raises(_Stop):
        call()
    hist = client.sent[0]
    assert hist[-2]["role"] == "assistant" and hist[-1]["role"] == "user"
    return hist[-2]["content"], hist[-1]["content"]


@pytest.mark.parametrize("loop", ["generate", "critique"])
def test_history_carries_only_input_fields(loop, monkeypatch):
    assert "parsed_output" in _text("x").model_dump()          # предпосылка: SDK так отдаёт
    assistant, results = _run(loop, _FakeClient([THINK, _text("Смотрю понятие."), TOOL]), monkeypatch)
    assert assistant == [
        {"type": "thinking", "thinking": "…", "signature": "sig-1"},
        {"type": "text", "text": "Смотрю понятие."},
        {"type": "tool_use", "id": "toolu_1", "name": "read_cbcr_concept",
         "input": {"name": "Bias", "opt": None}},              # None внутри input не тронут
    ]
    assert [r["tool_use_id"] for r in results] == ["toolu_1"]


@pytest.mark.parametrize("loop", ["generate", "critique"])
@pytest.mark.parametrize("blank", ["", "  \n"])
def test_blank_text_block_is_dropped(loop, blank, monkeypatch):
    assistant, _ = _run(loop, _FakeClient([THINK, _text(blank), TOOL]), monkeypatch)
    assert [b["type"] for b in assistant] == ["thinking", "tool_use"]
