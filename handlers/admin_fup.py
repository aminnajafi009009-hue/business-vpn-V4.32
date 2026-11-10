"""ادمین: «⚖️ مصرف منصفانه» (سرویس و پنل) — روشن/خاموش، حد مصرف آزاد، سهمیه‌ی روزانه و لیست سرویس‌های محدودشده.

callbackها با پیشوند fup_ (دسترسی vpn_panel). منطق در fair_usage.py."""
from __future__ import annotations

import logging

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton as B, InlineKeyboardMarkup as KB

import database as db
import fair_usage as fu
from config import ADMIN_ID

router = Router()
logger = logging.getLogger(__name__)


class FupStates(StatesGroup):
    waiting_free = State()
    waiting_daily = State()
    waiting_period = State()


def _allowed(uid: int) -> bool:
    return uid == ADMIN_ID or (db.is_sub_admin(str(uid)) and db.sub_admin_has_permission(str(uid), "vpn_panel"))


def _scope_options() -> list[tuple[int, str]]:
    """(شناسه، نام) دسته‌بندی‌هایی که می‌توان مصرف منصفانه را روی آن‌ها اعمال کرد (هم‌شناسه با تنظیمات تمدید)."""
    out: list[tuple[int, str]] = []
    for cat in (db.get_vip_categories() or []):
        out.append((int(cat["id"]), str(cat.get("name") or cat["id"])))
    out.append((-1, "🛠 سرویس‌های سفارشی (همه‌ی گزینه‌ها)"))
    try:
        for o in (db.get_map_options("custom_build") or []):
            out.append((-1000 - int(o["num"]), f"🛠 سفارشی: {o.get('name') or o['num']}"))
    except Exception:
        pass
    out.append((0, "🌐 بدون دسته/قدیمی"))
    return out


def _cats_summary(c: dict) -> str:
    cats = set(c.get("categories") or [])
    if not cats:
        return "همه‌ی دسته‌ها"
    names = {i: n for i, n in _scope_options()}
    return "، ".join(names.get(i, str(i)) for i in sorted(cats))


def page_text() -> str:
    c = fu.get_cfg()
    started = len(db.get_fup_started_configs())
    blocked = len(db.get_fup_blocked_configs())
    return (
        "⚖️ مصرف منصفانه\n\n"
        "برای سرویس‌های «نامحدود» متصل به پنل (به‌جز PAYG): کاربر تا حد مصرف آزاد بدون محدودیت مصرف می‌کند؛ "
        "بعد از آن هر روز فقط سهمیه‌ی روزانه مجاز است و با رسیدن به سقف، سرویس تا ساعت ۰۰:۰۰ متوقف می‌شود "
        "(کاربر نمی‌تواند با دکمه‌ی «فعال‌سازی» دورش بزند). سرویس‌های PAYG و حجم‌دار تحت‌تأثیر نیستند.\n\n"
        f"وضعیت: {'🟢 روشن' if c['enabled'] else '🔴 خاموش'}\n"
        f"🎯 حد مصرف آزاد: {fu.fmt_bytes(c['free_bytes'])}" + (f" در هر {c['period_days']} روز" if c['period_days'] else " (کل مدت سرویس)") + "\n"
        f"⏱ بازه‌ی زمانی: {(str(c['period_days']) + ' روز (بعد از پایان هر بازه، سرویس از مصرف منصفانه خارج و حد آزاد دوباره از صفر شروع می‌شود)') if c['period_days'] else 'بدون محدودیت زمانی (فقط حجم)'}\n"
        f"🗂 دسته‌بندی‌های مشمول: {_cats_summary(c)}\n"
        f"📅 سهمیه‌ی روزانه بعد از آن: {fu.fmt_bytes(c['daily_bytes'])}\n\n"
        f"👥 سرویس‌های واردشده به مصرف منصفانه: {started}\n"
        f"⛔ هم‌اکنون متوقف: {blocked}\n\n"
        "ℹ️ بررسی هر ۵ دقیقه انجام می‌شود. متن اعلان‌ها از «ویرایش متن» و روشن/خاموش آن‌ها از «تنظیمات اعلان‌ها» قابل تغییر است."
    )


def page_kb() -> KB:
    c = fu.get_cfg()
    return KB(inline_keyboard=[
        [B(text=("🟢 مصرف منصفانه: روشن" if c["enabled"] else "🔴 مصرف منصفانه: خاموش"), callback_data="fup_toggle", style="success" if c["enabled"] else "danger")],
        [B(text="🎯 تنظیم حد مصرف آزاد", callback_data="fup_free", style="primary")],
        [B(text="📅 تنظیم سهمیه‌ی روزانه", callback_data="fup_daily", style="primary")],
        [B(text="⏱ تنظیم بازه‌ی زمانی (روز)", callback_data="fup_period", style="primary"),
         B(text="♾ حذف محدودیت زمانی", callback_data="fup_period_off", style="danger")],
        [B(text="🗂 دسته‌بندی‌های مشمول", callback_data="fup_cats", style="primary")],
        [B(text="📋 سرویس‌های محدودشده", callback_data="fup_list", style="primary")],
        [B(text="🔙 بازگشت", callback_data="admin_cat_service", style="danger")],
    ])


async def _show(target, edit=True):
    try:
        if edit:
            await target.edit_text(page_text(), reply_markup=page_kb())
            return
    except Exception:
        pass
    await target.answer(page_text(), reply_markup=page_kb())


@router.callback_query(F.data == "fup_open")
async def fup_open(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    if not _allowed(cb.from_user.id):
        return
    await state.clear()
    await _show(cb.message)


@router.callback_query(F.data == "fup_toggle")
async def fup_toggle(cb: types.CallbackQuery):
    await cb.answer()
    if not _allowed(cb.from_user.id):
        return
    fu.set_enabled(not fu.get_cfg()["enabled"])
    await _show(cb.message)


@router.callback_query(F.data == "fup_free")
async def fup_free(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    if not _allowed(cb.from_user.id):
        return
    await state.set_state(FupStates.waiting_free)
    await cb.message.answer(
        f"🎯 حد مصرف آزاد فعلی: {fu.fmt_bytes(fu.get_cfg()['free_bytes'])}\n\n"
        "کاربر تا این مقدار بدون هیچ محدودیتی مصرف می‌کند (در هر بازه‌ی زمانی تنظیم‌شده؛ اگر بازه‌ای نباشد، کل مصرف سرویس).\n"
        "مقدار جدید را بفرستید؛ مثلاً 100 (گیگابایت) یا 500MB یا 2.5GB:")


@router.callback_query(F.data == "fup_daily")
async def fup_daily(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    if not _allowed(cb.from_user.id):
        return
    await state.set_state(FupStates.waiting_daily)
    await cb.message.answer(
        f"📅 سهمیه‌ی روزانه‌ی فعلی: {fu.fmt_bytes(fu.get_cfg()['daily_bytes'])}\n\n"
        "بعد از رسیدن به حد مصرف آزاد، کاربر هر روز تا این مقدار مجاز است و ساعت ۰۰:۰۰ صفر می‌شود.\n"
        "مقدار را بفرستید؛ مثلاً 5 (گیگابایت) یا 500MB:")


@router.callback_query(F.data == "fup_period")
async def fup_period(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    if not _allowed(cb.from_user.id):
        return
    await state.set_state(FupStates.waiting_period)
    d = fu.get_cfg()["period_days"]
    await cb.message.answer(
        f"⏱ بازه‌ی زمانی فعلی: {str(d) + ' روز' if d else 'بدون محدودیت زمانی'}\n\n"
        "مثلاً با حد آزاد 100 گیگ و بازه‌ی 30 روز: کاربر در هر ۳۰ روز ۱۰۰ گیگ مصرف آزاد دارد؛ با رسیدن به آن وارد مصرف منصفانه می‌شود و با پایان ۳۰ روز "
        "از آن خارج شده و حد آزاد دوباره از صفر شروع می‌شود (دوره‌ها از تاریخ ساخت سرویس حساب می‌شوند).\n"
        "تعداد روز را بفرستید (مثلاً 30):")


@router.callback_query(F.data == "fup_period_off")
async def fup_period_off(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer("♾ محدودیت زمانی برداشته شد؛ فقط حجم" if _allowed(cb.from_user.id) else None)
    if not _allowed(cb.from_user.id):
        return
    c = fu.get_cfg(); c["period_days"] = 0; fu.save_cfg(c)
    await state.clear()
    await _show(cb.message)


@router.message(FupStates.waiting_period)
async def fup_period_value(message: types.Message, state: FSMContext):
    if not _allowed(message.from_user.id):
        return
    t = (message.text or "").strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    if not t.isdigit() or not (1 <= int(t) <= 3650):
        await message.answer("❌ عدد روز نامعتبر است (۱ تا ۳۶۵۰). مثل 30 بفرستید:")
        return
    c = fu.get_cfg(); c["period_days"] = int(t); fu.save_cfg(c)
    await state.clear()
    await _show(message, edit=False)


def _cats_kb() -> KB:
    c = fu.get_cfg()
    sel = set(c.get("categories") or [])
    rows = [[B(text=("✅ " if not sel else "⬜ ") + "همه‌ی دسته‌ها", callback_data="fup_cat_all", style="success" if not sel else "primary")]]
    for i, n in _scope_options():
        on = i in sel
        rows.append([B(text=("✅ " if on else "⬜ ") + n[:50], callback_data=f"fup_cat_{i}", style="success" if on else "primary")])
    rows.append([B(text="🔙 بازگشت", callback_data="fup_open", style="danger")])
    return KB(inline_keyboard=rows)


_CATS_TEXT = ("🗂 دسته‌بندی‌های مشمول مصرف منصفانه\n\n"
              "فقط سرویس‌های دسته‌های علامت‌خورده مشمول می‌شوند؛ بقیه (مثلاً یک بسته‌ی واقعاً نامحدود) بدون محدودیت می‌مانند. "
              "اگر هیچ دسته‌ای انتخاب نشود (یا «همه‌ی دسته‌ها»)، روی همه اعمال می‌شود. سرویس‌های PAYG هرگز مشمول نیستند.\n"
              "با خارج‌کردن یک دسته، سرویس‌های محدودشده‌ی آن ظرف ۵ دقیقه آزاد می‌شوند.")


@router.callback_query(F.data == "fup_cats")
async def fup_cats(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    if not _allowed(cb.from_user.id):
        return
    await state.clear()
    try:
        await cb.message.edit_text(_CATS_TEXT, reply_markup=_cats_kb())
    except Exception:
        await cb.message.answer(_CATS_TEXT, reply_markup=_cats_kb())


@router.callback_query(F.data.startswith("fup_cat_"))
async def fup_cat_toggle(cb: types.CallbackQuery):
    await cb.answer()
    if not _allowed(cb.from_user.id):
        return
    key = cb.data[len("fup_cat_"):]
    c = fu.get_cfg()
    if key == "all":
        c["categories"] = []
    else:
        try:
            i = int(key)
        except Exception:
            return
        sel = set(c.get("categories") or [])
        sel.symmetric_difference_update({i})
        c["categories"] = sorted(sel)
    fu.save_cfg(c)
    try:
        await cb.message.edit_reply_markup(reply_markup=_cats_kb())
    except Exception:
        pass


async def _save(message: types.Message, state: FSMContext, field: str, default_unit: str):
    if not _allowed(message.from_user.id):
        return
    val = fu.parse_amount(message.text or "", default_unit)
    if val is None or val < 0 or (field == "free_bytes" and val == 0) or val > 10_000_000 * fu.GB:
        await message.answer("❌ مقدار نامعتبر است. مثل 5 یا 500MB یا 2.5GB بفرستید:")
        return
    c = fu.get_cfg(); c[field] = val; fu.save_cfg(c)
    await state.clear()
    await _show(message, edit=False)


@router.message(FupStates.waiting_free)
async def fup_free_value(message: types.Message, state: FSMContext):
    await _save(message, state, "free_bytes", "gb")


@router.message(FupStates.waiting_daily)
async def fup_daily_value(message: types.Message, state: FSMContext):
    await _save(message, state, "daily_bytes", "gb")


@router.callback_query(F.data == "fup_list")
async def fup_list(cb: types.CallbackQuery):
    await cb.answer()
    if not _allowed(cb.from_user.id):
        return
    blocked = db.get_fup_blocked_configs(limit=30)
    started = [x for x in db.get_fup_started_configs(limit=30) if not x.get("fup_blocked")][:15]
    rows = []
    for tag, items in (("⛔", blocked), ("⚖️", started)):
        for x in items:
            rows.append([B(text=f"{tag} {x.get('service_id') or x.get('plan')}"[:60], callback_data=f"svcdetail_{x['id']}", style="primary")])
    rows.append([B(text="🔙 بازگشت", callback_data="fup_open", style="danger")])
    text = "📋 سرویس‌های محدودشده\n\n⛔ = هم‌اکنون متوقف | ⚖️ = وارد مصرف منصفانه (فعال)\nبرای مدیریت روی سرویس بزنید 👇" if len(rows) > 1 else "📋 سرویسی در مصرف منصفانه نیست."
    try:
        await cb.message.edit_text(text, reply_markup=KB(inline_keyboard=rows))
    except Exception:
        await cb.message.answer(text, reply_markup=KB(inline_keyboard=rows))
