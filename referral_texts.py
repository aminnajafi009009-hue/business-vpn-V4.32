"""referral_texts.py — جمله‌های شرط/توضیح رفرال برای کاربر، بر اساس «حالت رفرال» (مبلغی / درصدی / هر دو).

جمله‌های درصدی از «ویرایش متن» قابل‌تغییرند (کلیدهای referral_cond_percent_* و referral_join_percent_*)."""
from __future__ import annotations

import ui_editor


def _pct(rs: dict) -> str:
    return f"{float(rs.get('percent_rate') or 0):g}"


def _tpl(key: str, rs: dict) -> str:
    text, _raw = ui_editor.render_template(key, {"percent": _pct(rs)}, fallback=ui_editor.SCREENS[key]["default"])
    return text


def screen_key(rs: dict) -> str:
    """کلید صفحه‌ی «دعوت دوستان» در ویرایش متن بر اساس حالت."""
    if rs.get("amount_active") and rs.get("percent_active"):
        return "referral_both"
    if rs.get("percent_active"):
        return "referral_percent"
    return "referral"


def _percent_on(rs: dict) -> bool:
    return bool(rs.get("percent_active")) and float(rs.get("percent_rate") or 0) > 0


def amount_condition_text(rs: dict) -> str:
    amt = int(rs["reward_amount"] or 0)
    min_gb = int(rs["min_volume_gb"] or 0)
    min_amt = int(rs.get("min_paid_amount") or 0)
    if not rs["paid_purchase_required"]:
        return f"ℹ️ به‌ازای هر دوستی که با لینک شما عضو شود، {amt:,} تومان بلافاصله و بدون نیاز به خرید به کیف پول شما آزاد می‌شود."
    conds = []
    if rs["min_volume_enabled"] and min_gb > 0:
        conds.append(f"حجم {min_gb} گیگ یا بیشتر")
    if min_amt > 0:
        conds.append(f"مبلغ {min_amt:,} تومان یا بیشتر")
    if conds:
        what = " و ".join(conds)
        return (f"ℹ️ به‌ازای هر دوستی که با لینک شما عضو شود و یک خرید با {what} انجام دهد، {amt:,} تومان به‌صورت خودکار به کیف پول شما آزاد می‌شود.\n"
                f"❌ تست رایگان و خریدهای کمتر از این حد پاداش را آزاد نمی‌کنند.")
    return f"ℹ️ به‌ازای هر دوستی که با لینک شما عضو شود و هر خرید پولی انجام دهد، {amt:,} تومان به‌صورت خودکار و بدون نیاز به هیچ اقدام دیگری به کیف پول شما آزاد می‌شود."


def percent_condition_text(rs: dict) -> str:
    if not _percent_on(rs):
        return ""
    return _tpl("referral_cond_percent_first" if rs.get("percent_first_only") else "referral_cond_percent_every", rs)


def condition_text(rs: dict) -> str:
    parts = []
    if rs.get("amount_active"):
        parts.append(amount_condition_text(rs))
    p = percent_condition_text(rs)
    if p:
        parts.append(p)
    return "\n".join(parts)


def join_amount_text(rs: dict) -> str:
    amt = int(rs["reward_amount"] or 0)
    min_gb = int(rs["min_volume_gb"] or 0)
    min_amt = int(rs.get("min_paid_amount") or 0)
    if not rs["paid_purchase_required"]:
        return f"{amt:,} تومان به‌صورت فوری و بدون نیاز به خرید به کیف پول شما آزاد می‌شود."
    conds = []
    if rs["min_volume_enabled"] and min_gb > 0:
        conds.append(f"حجم {min_gb} گیگ یا بیشتر")
    if min_amt > 0:
        conds.append(f"مبلغ {min_amt:,} تومان یا بیشتر")
    if conds:
        return f"پس از اینکه این کاربر یک خرید با {' و '.join(conds)} انجام دهد، {amt:,} تومان به‌صورت خودکار به کیف پول شما آزاد می‌شود."
    return f"پس از اینکه این کاربر هر خرید پولی انجام دهد، {amt:,} تومان به‌صورت خودکار به کیف پول شما آزاد می‌شود."


def join_text(rs: dict) -> str:
    parts = []
    if rs.get("amount_active"):
        parts.append(join_amount_text(rs))
    if _percent_on(rs):
        parts.append(_tpl("referral_join_percent_first" if rs.get("percent_first_only") else "referral_join_percent_every", rs))
    return "\n".join(parts)
