"""Таймаут индикатора «печатает» не отменяет утренний бриф (карточка 2026-10-29-6f54c656).

28.10 08:30 send_chat_action(typing) упал «Telegram error: Timed out», и send_morning_report
вышел, не собрав отчёт: дня нет ни в reports/, ни в context_cards. Здесь индикатор падает тем
же TimedOut, а генерация отчёта обязана всё равно быть вызвана и человек — получить сообщение."""
from __future__ import annotations

import asyncio
import types

import pytest
from telegram.error import TimedOut

import jobs.scheduled as sched
import notify
import triage_agent as _tri

pytestmark = pytest.mark.unit


def test_typing_timeout_does_not_cancel_the_brief(monkeypatch, tg, fault_journal):
    monkeypatch.setattr(_tri, "latest_verdict", lambda require_today=False: ({}, ""))
    monkeypatch.setattr(notify, "notify_operator", lambda msg: "telegram")

    async def typing_times_out(*a, **k):
        raise TimedOut()

    monkeypatch.setattr(tg, "send_chat_action", typing_times_out)
    calls = []

    def gen(*a, **k):
        calls.append(a)
        raise RuntimeError("выдуманный сбой генерации — дальше индикатора дошли")

    monkeypatch.setattr(sched.gp, "generate_daily_report", gen)
    monkeypatch.setattr(sched, "refresh_data", lambda *a, **k: None)
    monkeypatch.setattr(sched, "get_chat_id", lambda: 111222333)
    sent = []

    async def fake_send_long(bot, chat_id, text, **kw):
        sent.append(text)

    monkeypatch.setattr(sched, "send_long", fake_send_long)
    asyncio.run(sched.send_morning_report(types.SimpleNamespace(bot=tg)))
    assert len(calls) == 1, "бриф оборван таймаутом индикатора"
    assert len(sent) == 1
