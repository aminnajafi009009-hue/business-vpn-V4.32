"""موتور واحد آمار (منبع تنها برای ربات و مینی‌اپ).

قواعد ثابت (همه‌ی اعداد از همین‌جا می‌آیند تا ربات و مینی‌اپ هیچ‌وقت با هم اختلاف نداشته باشند):
• زمان‌ها در دیتابیس به‌وقت UTC سرور ذخیره می‌شوند؛ «روز» و «ماه» همیشه بر تقویم تهران محاسبه می‌شود
  (روزبندی در SQL با date(ts, '+N minutes') انجام می‌شود، نه substr خام).
• فروش = سفارش‌هایی با وضعیت paid / processing / fulfilled (pending/rejected/dismissed/failed حساب نمی‌شوند).
• انواع: new (سرویس آماده)، custom (بساز سرویس خودت)، renew (تمدید؛ هم از orders هم custom_orders)،
  test (تست رایگان؛ مبلغ صفر، جدا از درآمد).
• درآمد کل = new + custom + renew. تمدید همیشه یک جریان جدا هم دارد (تعداد/مبلغ/سهم/نمودار).
• سفارش در انتظار = همان صفی که ادمین واقعاً در ربات می‌بیند (orders با وضعیت pending + custom_orders پرداخت‌شده‌ی تحویل‌نشده).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import database as db

SOLD = "('paid','processing','fulfilled','completed','active')"
_FMT = "%Y-%m-%d %H:%M:%S"

_METHOD_LABELS = {
    "card": "💳 کارت به کارت", "wallet": "👛 کیف پول", "crypto": "🪙 رمزارز",
    "gateway": "🏦 درگاه", "zarinpal": "🏦 درگاه", "uniquepay": "🏦 درگاه", "tonpays": "🏦 درگاه",
}


def method_label(raw) -> str:
    r = str(raw or "").strip()
    return _METHOD_LABELS.get(r.lower(), r or "نامشخص")


# ------------------------------------------------------------------ زمان
def _tehran_now() -> datetime:
    from utils import now_tehran
    return now_tehran()


def tz_modifier() -> str:
    """آفست تهران نسبت به UTC برای date(ts, ?) در SQLite (مثلاً '+210 minutes')."""
    off = _tehran_now().utcoffset() or timedelta(hours=3, minutes=30)
    return f"{int(off.total_seconds() // 60):+d} minutes"


def tehran_today():
    return _tehran_now().date()


def tehran_day_start_utc(day) -> str:
    """شروع روز تهرانی (date) بر حسب رشته‌ی UTC دیتابیس."""
    from utils import TEHRAN_TZ
    aware = datetime(day.year, day.month, day.day, tzinfo=TEHRAN_TZ)
    return aware.astimezone(timezone.utc).replace(tzinfo=None).strftime(_FMT)


# ------------------------------------------------------------------ دفتر فروش
_LEDGER = f"""
SELECT o.created_at AS ts, o.user_id AS user_id, o.price AS amt,
       CASE WHEN o.order_type IN ('test','free_test') THEN 'test'
            WHEN o.order_type = 'renew' OR o.target_config_id IS NOT NULL THEN 'renew'
            ELSE 'new' END AS kind,
       COALESCE(NULLIF(o.payment_method, ''), 'نامشخص') AS method,
       o.plan_name AS plan
  FROM orders o
 WHERE o.status IN {SOLD} AND o.order_type != 'wallet_charge'
UNION ALL
SELECT c.created_at, c.user_id, c.price,
       CASE WHEN c.order_type = 'renew' THEN 'renew_custom' ELSE 'custom' END,
       COALESCE(NULLIF(c.payment_method, ''), 'نامشخص'),
       COALESCE(NULLIF(c.custom_name, ''), 'سرویس سفارشی')
  FROM custom_orders c
 WHERE c.status IN {SOLD}
"""


def _q(sql, params=()):
    cur = db.get_connection().cursor()
    cur.execute(sql, params)
    return db._fetchall(cur)


def _one(sql, params=()):
    rows = _q(sql, params)
    return rows[0] if rows else {}


def _i(v) -> int:
    try:
        return int(v or 0)
    except Exception:
        return 0


def _rng(col, start, end):
    """شرط بازه‌ی نیمه‌باز [start, end) روی ستون زمان UTC."""
    if not start:
        return "", ()
    return f" AND {col} >= ? AND {col} < ?", (start, end or "9999-12-31 00:00:00")


# ------------------------------------------------------------------ خلاصه‌ی دوره
def period_summary(start_utc: str | None, end_utc: str | None) -> dict:
    w, p = _rng("ts", start_utc, end_utc)
    rows = _q(f"SELECT kind, COUNT(*) n, COALESCE(SUM(amt),0) s FROM ({_LEDGER}) WHERE 1=1{w} GROUP BY kind", p)
    k = {r["kind"]: (_i(r["n"]), _i(r["s"])) for r in rows}
    z = (0, 0)
    plan_n, plan_s = k.get("new", z)
    cust_n, cust_s = k.get("custom", z)
    rplan_n, rplan_s = k.get("renew", z)
    rcust_n, rcust_s = k.get("renew_custom", z)
    test_n = k.get("test", z)[0]
    new_n, new_s = plan_n + cust_n, plan_s + cust_s
    ren_n, ren_s = rplan_n + rcust_n, rplan_s + rcust_s
    rev = new_s + ren_s

    buyers = _i(_one(f"SELECT COUNT(DISTINCT user_id) c FROM ({_LEDGER}) WHERE kind != 'test' AND amt > 0{w}", p).get("c"))
    renewers = _i(_one(f"SELECT COUNT(DISTINCT user_id) c FROM ({_LEDGER}) WHERE kind IN ('renew','renew_custom') AND amt > 0{w}", p).get("c"))
    testers = _i(_one(f"SELECT COUNT(DISTINCT user_id) c FROM ({_LEDGER}) WHERE kind = 'test'{w}", p).get("c"))

    by_method: dict = {}
    renew_by_method: dict = {}
    for r in _q(f"SELECT method m, kind, COUNT(*) n, COALESCE(SUM(amt),0) s FROM ({_LEDGER}) WHERE kind != 'test' AND amt > 0{w} GROUP BY method, kind", p):
        lbl = method_label(r["m"])
        slot = by_method.setdefault(lbl, {"count": 0, "amount": 0})
        slot["count"] += _i(r["n"]); slot["amount"] += _i(r["s"])
        if r["kind"] in ("renew", "renew_custom"):
            rs = renew_by_method.setdefault(lbl, {"count": 0, "amount": 0})
            rs["count"] += _i(r["n"]); rs["amount"] += _i(r["s"])

    wt, wp = _rng("created_at", start_utc, end_utc)
    ch = _one(f"SELECT COUNT(*) n, COALESCE(SUM(amount),0) s FROM transactions WHERE type='charge' AND status='completed'{wt}", wp)
    nu_w, nu_p = _rng("joined", start_utc, end_utc)
    new_users = _i(_one(f"SELECT COUNT(*) c FROM users WHERE 1=1{nu_w}", nu_p).get("c"))

    return {
        "plan_new_count": plan_n, "plan_new_amount": plan_s,
        "custom_new_count": cust_n, "custom_new_amount": cust_s,
        "sales_count": new_n, "sales_amount": new_s,
        "renew_plan_count": rplan_n, "renew_plan_amount": rplan_s,
        "renew_custom_count": rcust_n, "renew_custom_amount": rcust_s,
        "renew_count": ren_n, "renew_amount": ren_s,
        "renew_pct": round(ren_s / rev * 100, 1) if rev else 0.0,
        "test_count": test_n, "testers": testers,
        "total_revenue": rev, "orders_count": new_n + ren_n,
        "buyers": buyers, "renewers": renewers,
        "avg_per_order": round(rev / (new_n + ren_n)) if (new_n + ren_n) else 0,
        "avg_per_customer": round(rev / buyers) if buyers else 0,
        "by_method": by_method, "renew_by_method": renew_by_method,
        "wallet_charged": _i(ch.get("s")), "wallet_charge_count": _i(ch.get("n")),
        "new_users": new_users,
    }


# ------------------------------------------------------------------ لحظه‌ای
def pending_counts() -> dict:
    """همان تعریفی که صف واقعی ادمین دارد (نه شمارش وضعیت‌های دیگر)."""
    orders_pending = _i(_one("SELECT COUNT(*) c FROM orders WHERE status = 'pending'").get("c"))
    custom_paid = _i(_one("SELECT COUNT(*) c FROM custom_orders WHERE status = 'paid'").get("c"))
    receipts = _i(_one("SELECT COUNT(*) c FROM pending_receipts WHERE status = 'pending'").get("c"))
    tickets = _i(_one("SELECT COUNT(*) c FROM tickets WHERE status != 'closed'").get("c"))
    return {"pending_orders": orders_pending + custom_paid, "pending_receipts": receipts, "open_tickets": tickets}


# ------------------------------------------------------------------ سری روزانه
def daily_series(days: int) -> list[dict]:
    """روزهای تهرانی (قدیمی→جدید): درآمد/تعداد هر نوع، تست، شارژ کیف پول، کاربر جدید."""
    days = max(1, int(days))
    today = tehran_today()
    first = today - timedelta(days=days - 1)
    start_utc = tehran_day_start_utc(first)
    mod = tz_modifier()
    acc: dict[str, dict] = {}
    for i in range(days):
        d = (first + timedelta(days=i)).isoformat()
        acc[d] = {"d": d, "revenue": 0, "orders": 0, "new_amount": 0, "new_count": 0, "custom_amount": 0, "custom_count": 0,
                  "renew_amount": 0, "renew_count": 0, "tests": 0, "wallet_charged": 0, "users": 0}
    for r in _q(f"SELECT date(ts, ?) d, kind, COUNT(*) n, COALESCE(SUM(amt),0) s FROM ({_LEDGER}) WHERE ts >= ? GROUP BY d, kind", (mod, start_utc)):
        a = acc.get(r["d"])
        if not a:
            continue
        n, s, kd = _i(r["n"]), _i(r["s"]), r["kind"]
        if kd == "test":
            a["tests"] += n
            continue
        a["revenue"] += s; a["orders"] += n
        if kd == "new":
            a["new_amount"] += s; a["new_count"] += n
        elif kd == "custom":
            a["custom_amount"] += s; a["custom_count"] += n
        else:
            a["renew_amount"] += s; a["renew_count"] += n
    for r in _q("SELECT date(created_at, ?) d, COALESCE(SUM(amount),0) s FROM transactions WHERE type='charge' AND status='completed' AND created_at >= ? GROUP BY d", (mod, start_utc)):
        if r["d"] in acc:
            acc[r["d"]]["wallet_charged"] = _i(r["s"])
    for r in _q("SELECT date(joined, ?) d, COUNT(*) c FROM users WHERE joined >= ? GROUP BY d", (mod, start_utc)):
        if r["d"] in acc:
            acc[r["d"]]["users"] = _i(r["c"])
    return list(acc.values())


def top_plans(start_utc, end_utc, limit=8, kinds=None) -> list[dict]:
    w, p = _rng("ts", start_utc, end_utc)
    kw = ""
    if kinds:
        kw = " AND kind IN (" + ",".join("'%s'" % x for x in kinds) + ")"
    return _q(f"SELECT plan name, COUNT(*) c, COALESCE(SUM(amt),0) s FROM ({_LEDGER}) WHERE kind != 'test'{kw}{w} GROUP BY plan ORDER BY s DESC LIMIT ?", p + (int(limit),))


def top_buyers(start_utc, end_utc, limit=8) -> list[dict]:
    w, p = _rng("l.ts", start_utc, end_utc)
    return _q(f"SELECT u.name name, u.telegram_id telegram_id, COUNT(*) c, COALESCE(SUM(l.amt),0) s FROM ({_LEDGER}) l JOIN users u ON u.id=l.user_id WHERE l.kind != 'test' AND l.amt > 0{w} GROUP BY l.user_id ORDER BY s DESC LIMIT ?", p + (int(limit),))


def days_bounds(days: int) -> tuple[str, str]:
    """[شروع روز اول, شروع فردا) برای «N روز اخیر» به تقویم تهران."""
    today = tehran_today()
    return tehran_day_start_utc(today - timedelta(days=days - 1)), tehran_day_start_utc(today + timedelta(days=1))
