"""Дерево кода не читает стенные часы в обход _time_inject (карточка report:87fc15, 26.10).

До этого теста контракт единого времени стерёг ТОЛЬКО ночной integrity
(`check_time_contract` → time_contract_sensor). Нить bug-report (19–20.10) принесла восемь
прямых `datetime.now(timezone.utc)` в bug_inbox/bug_outbox/bug_report/screen_trace/night_cycle;
baseline пуст (worklist закрыт), поэтому каждый сайт — FAIL, и integrity стал красным на
КАЖДОЙ установке, включая чужие (v0.2.4): `run_checks.sh` пишет «integrity findings» в журнал
сбоев, и он уезжает разработчику в /bug как «none в run_checks.integrity». Pre-commit сенсор
не зовёт — дефект доезжал до выпуска. Здесь он краснеет в прогоне тестов, до коммита.
"""
import time_contract_sensor


def test_no_new_direct_clock_calls():
    fails, _warns = time_contract_sensor.check()
    assert not fails, "прямой вызов часов в обход _time_inject (get_now/get_today):\n" + "\n".join(
        f"  {f['file']}:{f['line']}  {f['text']}" for f in fails)
