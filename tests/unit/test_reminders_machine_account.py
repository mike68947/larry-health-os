"""Нативный путь Reminders пишет в iCloud-аккаунт МАШИНЫ — он чужой всем, кроме оператора.

Замер 31.10: у тенанта партнёра не было caldav.json, его задачи уходили AppleScript'ом в
Reminders.app на Studio, то есть в iCloud владельца, и всплывали у владельца на телефоне
(список «Health (partner)», задача 114). Имя списка разное, аккаунт один — изоляции нет.
"""
from __future__ import annotations

import subprocess
from unittest.mock import Mock

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def env(monkeypatch, tmp_path):
    import notify
    import reminders_backend
    monkeypatch.setattr(reminders_backend, "caldav_configured", lambda: False)
    run = Mock(return_value=subprocess.CompletedProcess([], 0, stdout="OK", stderr=""))
    monkeypatch.setattr(subprocess, "run", run)
    fault = Mock(return_value=None)
    monkeypatch.setattr(notify, "fault", fault)
    import shutil
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/osascript" if name == "osascript" else None)

    def as_dir(name):
        monkeypatch.setenv("HEALTH_DATA_DIR", str(tmp_path / name))
    return run, fault, as_dir


TASK = {"id": 7, "type": "action", "content": "Сдать анализ (значения выдуманы)", "deadline": "2026-11-02"}


@pytest.mark.parametrize("tenant", ["health_demo_alpha", "health_staging"])
def test_tenant_without_own_channel_never_writes_machine_account(env, tenant):
    run, fault, as_dir = env
    as_dir(tenant)
    import task_agent
    assert task_agent.create_macos_reminder(dict(TASK)) is False
    run.assert_not_called()
    fault.assert_called_once()


def test_tenant_without_own_channel_never_reads_machine_account(env):
    run, fault, as_dir = env
    as_dir("health_demo_alpha")
    import reminders_sync
    assert reminders_sync.get_completed_task_ids() == []
    run.assert_not_called()
    fault.assert_called_once()


def test_operator_on_linux_without_caldav_is_quiet(env, monkeypatch):
    """Отчёты /bug 20–30.10, отпечаток 986fbe: посторонняя Docker-установка без CalDAV каждые
    3 часа звала osascript в Linux и писала сбой — 56 за неделю. Не подключено ≠ сломано."""
    run, fault, as_dir = env
    import shutil
    monkeypatch.setattr(shutil, "which", lambda name: None)
    as_dir("health")
    import reminders_sync
    import task_agent
    assert reminders_sync.get_completed_task_ids() == []
    assert task_agent.create_macos_reminder(dict(TASK)) is False
    run.assert_not_called()
    fault.assert_not_called()


def test_operator_keeps_native_path(env):
    run, fault, as_dir = env
    as_dir("health")
    import task_agent
    assert task_agent.create_macos_reminder(dict(TASK)) is True
    assert run.call_args.args[0][0] == "osascript"
    fault.assert_not_called()


def test_native_reminder_rings_at_the_persons_hour_not_midnight(env, monkeypatch):
    """Нативный путь ставил `time of d to 0` — будильник в полночь; час живёт в данных."""
    run, fault, as_dir = env
    as_dir("health")
    import reminders_backend
    from datetime import time
    monkeypatch.setattr(reminders_backend, "alarm_at", lambda: time(9, 30))
    import task_agent
    assert task_agent.create_macos_reminder(dict(TASK)) is True
    script = run.call_args.args[0][2]
    assert "set time of d to 34200" in script
