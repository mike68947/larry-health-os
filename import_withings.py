"""Давление Withings: зеркало замеров в bp_readings и дневное давление из них (нити withings-bp 04.10, bp-withings-owner 06.10).

Запуск по расписанию (шаблон launchd/cron withings-import) и руками: python3.11 import_withings.py
Withings не подключён (нет выдачи токена) — тихий выход 0: прибора нет, это не сбой.
Отказ Withings или токена — выход 1 с причиной: тихо проглоченный отказ и есть класс,
из-за которого давление молчало с июля.

Решение владельца 06.10: у кого Withings подключён, главный в давлении — Withings. Поэтому:
- bp_readings — ЗЕРКАЛО облака Withings: замер, удалённый в приложении Withings,
  удаляется и здесь. Живой случай 05.10: замер удалён в Withings, а «Здоровье» его хранило и
  подмешивало в среднее дня.
- дневные bp_systolic/bp_diastolic (среднее всех замеров дня — так требует домашний протокол 7-2-2)
  и пик дня raw bp_*_max (его читает потолок тревоги, решение 26.09) пишет отсюда Withings.
  Путь «Здоровья» эти ключи при непустом bp_readings не пишет (metrics_db.upsert_metrics_from_json).

Весы Withings (2026-11-07): тем же токеном — вес и состав тела в daily_metrics по утреннему (самому
раннему) взвешиванию местного дня, как у import_fitdays. Хозяин колонок дня — кто первым записал вес
(решение владельца 26.09: два пути не спорят за одно значение): свой день (raw.body_source=withings)
— зеркало облака, переписывается и чистится; чужой день («Здоровье», Fitdays) только доливается там,
где пусто. Пустой ответ при непустых своих днях — отказ, не чистка.
"""
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from statistics import fmean
from zoneinfo import ZoneInfo

import health_db as db
import region_pack
from withings_api import WithingsError, fetch_body, fetch_bp, withings_access_token

log = logging.getLogger("import_withings")
BP_SOURCE = "withings"      # метка в raw дня: день написан отсюда (по ней чистится день без замеров)
_RAW_BP_KEYS = ("bp_systolic", "bp_diastolic", "bp_systolic_max", "bp_diastolic_max")
BODY_SOURCE = "withings"    # метка в raw дня: вес и состав тела написаны отсюда
_BODY_COLS = ("weight", "body_fat_pct", "muscle_mass_kg", "bone_mass_kg", "body_water_pct",
              "visceral_fat", "bmr_kcal")


def _raw(conn, date: str) -> dict:
    row = conn.execute("SELECT raw FROM daily_metrics WHERE date=?", (date,)).fetchone()
    try:
        raw = json.loads(row[0]) if row and row[0] else {}
    except json.JSONDecodeError:
        raw = {}
    return raw if isinstance(raw, dict) else {}


def _mirror(conn, rows: list[dict]) -> int:
    """bp_readings := нынешний набор Withings; возвращает число удалённых. Пустой ответ при
    непустой истории — отказ, а не стирание: пустой ответ инструмента ≠ отсутствие данных."""
    have = {r[0] for r in conn.execute("SELECT measured_at FROM bp_readings")}
    if not rows and have:
        raise WithingsError(f"Withings вернул ноль замеров при {len(have)} в истории — "
                            "зеркалить не стану; проверьте, тот ли аккаунт подключён")
    conn.executemany(
        "INSERT INTO bp_readings (measured_at, systolic, diastolic, pulse, grpid) "
        "VALUES (:ts, :systolic, :diastolic, :pulse, :grpid) "
        "ON CONFLICT(measured_at) DO UPDATE SET systolic=excluded.systolic, "
        "diastolic=excluded.diastolic, pulse=excluded.pulse, grpid=excluded.grpid, "
        "imported_at=datetime('now')", rows)
    gone = have - {r["ts"] for r in rows}
    conn.executemany("DELETE FROM bp_readings WHERE measured_at=?", [(t,) for t in gone])
    return len(gone)


def _days(conn, tz) -> dict:
    """Дата (местная) → (среднее сист., среднее диаст., пик сист., пик диаст.) по всем замерам дня."""
    by_day: dict = {}
    for ts, s, d in conn.execute("SELECT measured_at, systolic, diastolic FROM bp_readings"):
        by_day.setdefault(datetime.fromtimestamp(ts, tz).date().isoformat(), []).append((s, d))
    return {day: (round(fmean(s for s, _ in v), 1), round(fmean(d for _, d in v), 1),
                  max(s for s, _ in v), max(d for _, d in v)) for day, v in by_day.items()}


def _write_days(conn, days: dict) -> int:
    """Дневное давление из замеров. Начиная с первого дня Withings у дня один хозяин: день без
    замеров (все удалены) чистится, чужое значение такого дня переписывается."""
    first = min(days) if days else None
    targets = set(days)
    for date, raw, sys_ in conn.execute("SELECT date, raw, bp_systolic FROM daily_metrics"):
        mine = '"bp_source": "withings"' in (raw or "")
        if mine or (first and date >= first and sys_ is not None):
            targets.add(date)
    for date in sorted(targets):
        conn.execute("INSERT OR IGNORE INTO daily_metrics(date) VALUES (?)", (date,))
        raw = _raw(conn, date)
        for k in _RAW_BP_KEYS:
            raw.pop(k, None)
        raw.pop("bp_source", None)
        mean_s, mean_d = None, None
        if date in days:
            mean_s, mean_d, max_s, max_d = days[date]
            raw.update({"bp_systolic_max": max_s, "bp_diastolic_max": max_d, "bp_source": BP_SOURCE})
        conn.execute("UPDATE daily_metrics SET bp_systolic=?, bp_diastolic=?, raw=? WHERE date=?",
                     (mean_s, mean_d, json.dumps(raw, ensure_ascii=False), date))
    return len(targets)


def _body_days(rows: list[dict], tz) -> dict:
    """Дата (местная) → утреннее (самое раннее) взвешивание дня: один замер биоимпеданса на день,
    вес и состав тела из одной строки — как у import_fitdays.aggregate_morning."""
    days: dict = {}
    for r in sorted(rows, key=lambda r: r["ts"]):
        days.setdefault(datetime.fromtimestamp(r["ts"], tz).date().isoformat(), r)
    return days


def _write_body_days(conn, days: dict) -> int:
    """Вес и состав тела из взвешиваний. Свой день (raw.body_source=withings или вес пуст) — зеркало
    облака: переписывается, без взвешивания чистится. Чужой день — только доливка пустых колонок."""
    mine = {d for d, raw in conn.execute("SELECT date, raw FROM daily_metrics")
            if f'"body_source": "{BODY_SOURCE}"' in (raw or "")}
    if not days and mine:
        raise WithingsError(f"Withings вернул ноль взвешиваний при {len(mine)} днях веса в базе — "
                            "чистить не стану; проверьте, тот ли аккаунт подключён")
    targets = mine | set(days)
    for date in sorted(targets):
        conn.execute("INSERT OR IGNORE INTO daily_metrics(date) VALUES (?)", (date,))
        raw = _raw(conn, date)
        raw.pop("body_source", None)
        rec = {c: v for c, v in (days.get(date) or {}).items() if c in _BODY_COLS}
        weight_before = conn.execute("SELECT weight FROM daily_metrics WHERE date=?", (date,)).fetchone()[0]
        if date in mine or weight_before is None:
            if rec:
                raw["body_source"] = BODY_SOURCE
            sets, params = [f"{c}=?" for c in _BODY_COLS], [rec.get(c) for c in _BODY_COLS]
        else:                                    # чужой день: доливаем только пустое
            sets, params = [f"{c}=COALESCE({c}, ?)" for c in rec], list(rec.values())
        conn.execute(f"UPDATE daily_metrics SET {', '.join(sets)}, raw=? WHERE date=?",
                     (*params, json.dumps(raw, ensure_ascii=False), date))
    return len(targets)


def run() -> int:
    db.init_db()
    data_dir = Path(db.DB_PATH).parent
    token = withings_access_token(data_dir)
    if token is None:
        print("Withings не подключён — пропуск")
        return 0
    rows = fetch_bp(token, 0)                 # вся история: только так видно удалённое в приложении
    weighings = fetch_body(token, 0)
    tz = ZoneInfo(region_pack.value("timezone", "UTC"))
    with db.get_conn() as conn:               # давление и вес — одной транзакцией
        gone = _mirror(conn, rows)
        touched = _write_days(conn, _days(conn, tz))
        body_days = _write_body_days(conn, _body_days(weighings, tz))
    print(f"Withings: замеров давления {len(rows)}, удалено как удалённых в Withings {gone}, "
          f"дней давления пересчитано {touched}; взвешиваний {len(weighings)}, дней веса пересчитано {body_days}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        sys.exit(run())
    except WithingsError as exc:
        print(f"Импорт Withings не выполнен: {exc}", file=sys.stderr)
        import notify
        notify.fault(f"import_withings: {exc}", person_key=None)   # журнал сбоев → ночной цикл
        sys.exit(1)
