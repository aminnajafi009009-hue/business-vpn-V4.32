"""
handlers/ticket.py
سیستم تیکت پشتیبانی با تاریخچه‌ی کامل و پنل مدیریت برای ادمین.

🎫 قبلاً این بخش کاملاً بی‌حافظه بود: فقط یک پیام فوروارد‌شده به ادمین با یک
دکمه‌ی «پاسخ»، بدون هیچ رکورد پایدار در دیتابیس. یعنی نه کاربر می‌توانست
تاریخچه‌ی تیکت‌های قبلی‌اش را ببیند، نه ادمین می‌توانست لیست تیکت‌های باز را
مرور کند یا وضعیت (باز/پاسخ‌داده‌شده/بسته) را دنبال کند. الان با جدول‌های
tickets/ticket_messages، هر دو طرف تاریخچه‌ی کامل مکالمه را دارند.
"""

import logging
import ui_editor

from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext

import database as db
from utils import show_menu_with_sticker
from states import UserStates, AdminStates
from config import ADMIN_ID
from keyboards import (
    back_button, ticket_reply_keyboard, support_menu,
    my_tickets_list_keyboard, ticket_thread_user_keyboard,
    admin_tickets_menu, admin_tickets_list_keyboard, admin_ticket_detail_keyboard,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from handlers.admin import _is_admin, AdminPermissionMiddleware

logger = logging.getLogger(__name__)
router = Router(name="ticket")
router.message.middleware(AdminPermissionMiddleware())
router.callback_query.middleware(AdminPermissionMiddleware())

_SENDER_LABEL = {"user": "👤 شما", "admin": "👨‍💻 پشتیبانی"}

# 📎 پیوست در تیکت: عکس/ویدیو/فایل/ویس/گیف/… (متن تیکت با برچسب نوع پیوست ذخیره می‌شود؛ خود فایل با copy_message به طرف مقابل می‌رسد)
_MEDIA_LABELS = (("photo", "📷 عکس"), ("video", "🎞 ویدیو"), ("animation", "🎞 گیف"), ("document", "📎 فایل"),
                 ("voice", "🎤 پیام صوتی"), ("audio", "🎵 آهنگ"), ("video_note", "⭕ ویدیو پیام"), ("sticker", "🖼 استیکر"))
_GROUP_WINDOW = 20  # ثانیه: آیتم‌های بعدی آلبوم (media_group) در همین بازه به همان تیکت اضافه می‌شوند


def _media_label(m) -> str | None:
    for attr, label in _MEDIA_LABELS:
        if getattr(m, attr, None):
            return label
    return None


def _ticket_body(m) -> str:
    """متن/کپشن پیام؛ برای پیام بدون متن (فقط پیوست) خالی برمی‌گرداند."""
    return (getattr(m, "text", None) or getattr(m, "caption", None) or "").strip()


def _ticket_text(m) -> str:
    label = _media_label(m)
    body = _ticket_body(m)
    if label:
        return f"{label} — {body}" if body else label
    return body or "(پیام غیرمتنی)"


def _format_thread(ticket: dict, messages: list[dict]) -> str:
    lines = [f"🎫 تیکت #{ticket['id']}\n"]
    for m in messages:
        lines.append(f"{_SENDER_LABEL.get(m['sender'], m['sender'])}:\n{m['text']}\n")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# سمت کاربر
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "support")
async def support_start(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await show_menu_with_sticker(callback.bot, callback.message.chat.id, "support",
        "👨‍💻 پشتیبانی\n\nمی‌تونی مستقیم تیکت بزنی یا از کانال اصلی و پشتیبان استفاده کنی 👇",
        reply_markup=support_menu(),
    )
    await callback.answer()


@router.callback_query(F.data == "ticket")
async def ticket_start(callback: types.CallbackQuery, state: FSMContext):
    await show_menu_with_sticker(callback.bot, callback.message.chat.id, "ticket_write",
        "👨‍💻 پیام خود را برای پشتیبانی بنویسید:",
        reply_markup=back_button("support", "🔙 انصراف", screen="ticket_write"),
    )
    await state.set_state(UserStates.waiting_ticket_message)
    await callback.answer()


@router.callback_query(F.data == "my_tickets")
async def my_tickets(callback: types.CallbackQuery, state: FSMContext | None = None):
    if state is not None:
        await state.clear()
    user = db.get_user(callback.from_user.id)
    if user is None:
        await callback.answer(ui_editor.get_alert_text("msg_18ae2939df", "ابتدا دستور /start را بزنید."), show_alert=True)
        return
    tickets = db.list_user_tickets(user["id"])
    text = "📋 هنوز هیچ تیکتی ثبت نکرده‌اید." if not tickets else "📋 تیکت‌های شما:\n\nبرای دیدن مکالمه‌ی هرکدام روی آن بزنید 👇"
    await callback.message.answer(text, reply_markup=my_tickets_list_keyboard(tickets))
    await callback.answer()


@router.callback_query(F.data.startswith("myticketview_"))
async def my_ticket_view(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    ticket_id = int(callback.data.replace("myticketview_", ""))
    ticket = db.get_ticket(ticket_id)
    if not ticket or not user or ticket["user_id"] != user["id"]:
        await callback.answer("❌ این تیکت پیدا نشد.", show_alert=True)
        return
    messages = db.get_ticket_messages(ticket_id)
    await callback.message.answer(_format_thread(ticket, messages), reply_markup=ticket_thread_user_keyboard(ticket_id, ticket["status"]))
    await callback.answer()


@router.callback_query(F.data.startswith("ticketreply_"))
async def ticket_reply_start(callback: types.CallbackQuery, state: FSMContext):
    ticket_id = int(callback.data.replace("ticketreply_", ""))
    ticket = db.get_ticket(ticket_id)
    user = db.get_user(callback.from_user.id)
    if not ticket or not user or ticket["user_id"] != user["id"] or ticket["status"] == "closed":
        await callback.answer("❌ این تیکت دیگر برای پاسخ در دسترس نیست.", show_alert=True)
        return
    await state.update_data(user_ticket_id=ticket_id)
    await state.set_state(UserStates.waiting_ticket_message)
    await callback.message.answer("✍️ پیام خودتون رو بفرستید (به همین تیکت اضافه می‌شه):")
    await callback.answer()


@router.message(UserStates.waiting_ticket_message)
async def ticket_message(message: types.Message, state: FSMContext):
    user = db.get_user(message.from_user.id)
    if user is None:
        await state.clear()
        return
    import time as _t
    data = await state.get_data()
    _gid = getattr(message, "media_group_id", None)
    _done = data.get("tk_done_ts")
    if _done is not None:
        # آیتم بعدی آلبومِ همین تیکت (ظرف چند ثانیه) هم اضافه می‌شود؛ غیر از آن جلسه بسته است
        if not (_gid and _gid == data.get("tk_group") and _t.time() - float(_done) <= _GROUP_WINDOW):
            await state.clear()
            return
    ticket_id = data.get("user_ticket_id")
    ticket = db.get_ticket(ticket_id) if ticket_id else None
    if not ticket or ticket["status"] == "closed":
        # تیکت مشخصی نبود یا بسته شده بود → آخرین تیکت باز کاربر پیدا یا یکی جدید ساخته می‌شود
        ticket = db.get_or_create_open_ticket(user["id"])

    _label = _media_label(message)
    _body = _ticket_body(message)
    db.add_ticket_message(ticket["id"], "user", _ticket_text(message))
    _head = f"🎫 تیکت #{ticket['id']}\n👤 {message.from_user.full_name}\n🆔 {message.from_user.id}\n\n💬 {_body or message.text}"
    if _label:
        _head = f"🎫 تیکت #{ticket['id']}\n👤 {message.from_user.full_name}\n🆔 {message.from_user.id}\n\n📎 {_label}" + (f"\n💬 {_body}" if _body else "")
    await message.bot.send_message(ADMIN_ID, _head, reply_markup=ticket_reply_keyboard(str(ticket["id"])))
    if _label:
        try:
            await message.bot.copy_message(ADMIN_ID, message.chat.id, message.message_id)
        except Exception:
            logger.warning("ticket: ارسال پیوست به ادمین ناموفق بود", exc_info=True)
    if _gid:
        # آلبوم: فقط برای اولین آیتم تأیید می‌دهیم و جلسه را برای بقیه‌ی آیتم‌ها کوتاه باز نگه می‌داریم
        if _done is None:
            await message.answer(ui_editor.get_text("msg_c439b5e6b7", "✅ پیام شما برای پشتیبانی ارسال شد. به‌زودی پاسخ داده می‌شود."))
        await state.update_data(tk_done_ts=_t.time(), tk_group=_gid)
        return
    await message.answer(ui_editor.get_text("msg_c439b5e6b7", "✅ پیام شما برای پشتیبانی ارسال شد. به‌زودی پاسخ داده می‌شود."))
    await state.clear()


# ---------------------------------------------------------------------------
# سمت ادمین — پاسخ سریع از روی نوتیفیکیشن (دکمه‌ی زیر پیام تیکت جدید)
# ---------------------------------------------------------------------------
@router.callback_query(F.data.startswith("replyticket_"))
async def admin_reply_start(callback: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer(ui_editor.get_alert_text("msg_16370070c5", "⛔ دسترسی ندارید."), show_alert=True)
        return
    ticket_id = int(callback.data.replace("replyticket_", ""))
    await state.update_data(reply_ticket_id=ticket_id)
    await state.set_state(AdminStates.waiting_ticket_reply)
    await callback.message.answer(f"✏️ پاسخ خود را برای تیکت #{ticket_id} بنویسید:")
    await callback.answer()


@router.message(AdminStates.waiting_ticket_reply)
async def admin_reply_send(message: types.Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    data = await state.get_data()
    ticket_id = data.get("reply_ticket_id")
    ticket = db.get_ticket(ticket_id) if ticket_id else None
    if not ticket:
        await state.clear()
        return
    import time as _t
    _gid = getattr(message, "media_group_id", None)
    _done = data.get("tk_done_ts")
    if _done is not None and not (_gid and _gid == data.get("tk_group") and _t.time() - float(_done) <= _GROUP_WINDOW):
        await state.clear()
        return
    user = db.get_user_by_id(ticket["user_id"])
    _label = _media_label(message)
    db.add_ticket_message(ticket["id"], "admin", _ticket_text(message) if _label else (message.text or ""))
    if user:
        try:
            # 🆕 بند ۲۰: دکمه‌ی سبز «پاسخ» مستقیماً زیر جواب پشتیبانی، تا کاربر
            # بدون رفتن به منو بتواند روی همین تیکت جواب بدهد.
            from utils import send_notification_sticker as _sns
            await _sns(message.bot, int(user["telegram_id"]), "notif_ticket_reply")
            _kb = InlineKeyboardMarkup(ui_screen="ticket_thread", inline_keyboard=[[
                InlineKeyboardButton(text="✍️ پاسخ", callback_data=f"ticketreply_{ticket['id']}", style="success", ui_screen="ticket_thread", ui_button_key="tkt_reply")
            ]])
            if _label:
                # پیوست (عکس/ویدیو/…): اول عنوان پاسخ، بعد خودِ پیوست (با کپشن اصلی) و دکمه‌ی «پاسخ» زیر آن
                if _done is None:
                    await message.bot.send_message(int(user["telegram_id"]), f"💬 پاسخ پشتیبانی (تیکت #{ticket['id']}):")
                await message.bot.copy_message(int(user["telegram_id"]), message.chat.id, message.message_id, reply_markup=_kb)
            else:
                await message.bot.send_message(
                    int(user["telegram_id"]),
                    f"💬 پاسخ پشتیبانی (تیکت #{ticket['id']}):\n\n{message.text}",
                    reply_markup=_kb,
                )
            if _gid:
                if _done is None:
                    await message.answer(ui_editor.get_text("msg_16729d90d5", "✅ پاسخ ارسال شد."))
                await state.update_data(tk_done_ts=_t.time(), tk_group=_gid)
                return
            await message.answer(ui_editor.get_text("msg_16729d90d5", "✅ پاسخ ارسال شد."))
        except Exception:
            await message.answer(ui_editor.get_text("msg_ddb9c5d6d5", "❌ ارسال پاسخ ناموفق بود (شاید کاربر ربات را بلاک کرده)."))
    await state.clear()


# ---------------------------------------------------------------------------
# 🎫 پنل مدیریت تیکت‌ها (سمت ادمین) — لیست/فیلتر/جزئیات/پاسخ/بستن/بازگشایی
# ---------------------------------------------------------------------------


@router.message(F.text == "🎫 مدیریت تیکت‌ها")
async def admin_tickets_open_reply(message: types.Message, state: FSMContext):
    """ورودی Reply Keyboard برای مدیریت تیکت‌ها."""
    if not _is_admin(message.from_user.id):
        return
    await state.clear()
    counts = {
        "open": db.count_tickets("open"),
        "answered": db.count_tickets("answered"),
        "closed": db.count_tickets("closed"),
    }
    await message.answer(
        "🎫 مدیریت تیکت‌ها\n\nیک دسته را برای مشاهده انتخاب کن 👇",
        reply_markup=admin_tickets_menu(counts),
    )

@router.callback_query(F.data == "admin_tickets")
async def admin_tickets_open(callback: types.CallbackQuery, state: FSMContext | None = None):
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
        return
    if state is not None:
        await state.clear()
    counts = {
        "open": db.count_tickets("open"),
        "answered": db.count_tickets("answered"),
        "closed": db.count_tickets("closed"),
    }
    await callback.message.edit_text("🎫 مدیریت تیکت‌ها\n\nیک دسته را برای مشاهده انتخاب کن 👇", reply_markup=admin_tickets_menu(counts))
    await callback.answer()


@router.callback_query(F.data.startswith("admtickets_"))
async def admin_tickets_list(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
        return
    parts = callback.data.split("_")
    status = parts[1]
    offset = int(parts[2]) if len(parts) > 2 else 0
    page_size = 10
    tickets = db.list_tickets(None if status == "all" else status, limit=page_size, offset=offset)
    total = db.count_tickets(None if status == "all" else status)
    label = {"open": "🟢 باز", "answered": "🟡 پاسخ‌داده‌شده", "closed": "🔴 بسته‌شده", "all": "📋 همه"}.get(status, status)
    text = f"{label}\n\nهیچ تیکتی در این دسته نیست." if not tickets else f"{label} ({total} مورد)\n\nروی هرکدام بزن تا مکالمه‌ی کامل رو ببینی 👇"
    await callback.message.edit_text(text, reply_markup=admin_tickets_list_keyboard(tickets, status, offset, offset + page_size < total))
    await callback.answer()


@router.callback_query(F.data.startswith("admticketview_"))
async def admin_ticket_view(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
        return
    ticket_id = int(callback.data.replace("admticketview_", ""))
    ticket = db.get_ticket(ticket_id)
    if not ticket:
        await callback.answer("❌ این تیکت پیدا نشد.", show_alert=True)
        return
    user = db.get_user_by_id(ticket["user_id"])
    messages = db.get_ticket_messages(ticket_id)
    header = f"👤 کاربر: {user.get('name', '-') if user else '-'} — 🆔 {user.get('telegram_id', '-') if user else '-'}\n\n"
    await callback.message.answer(header + _format_thread(ticket, messages), reply_markup=admin_ticket_detail_keyboard(ticket))
    await callback.answer()


@router.callback_query(F.data.startswith("admticketreply_"))
async def admin_ticket_reply_start(callback: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
        return
    ticket_id = int(callback.data.replace("admticketreply_", ""))
    await state.update_data(reply_ticket_id=ticket_id)
    await state.set_state(AdminStates.waiting_ticket_reply)
    await callback.message.answer(f"✏️ پاسخ خود را برای تیکت #{ticket_id} بنویسید:")
    await callback.answer()


@router.callback_query(F.data.startswith("admticketclose_"))
async def admin_ticket_close(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
        return
    ticket_id = int(callback.data.replace("admticketclose_", ""))
    db.set_ticket_status(ticket_id, "closed")
    ticket = db.get_ticket(ticket_id)
    user = db.get_user_by_id(ticket["user_id"]) if ticket else None
    if user:
        try:
            from utils import send_notification_sticker as _sns
            await _sns(callback.bot, int(user["telegram_id"]), "notif_ticket_reply")
            await callback.bot.send_message(int(user["telegram_id"]), f"✅ تیکت #{ticket_id} شما بسته شد. اگر مشکل حل نشده، می‌تونید تیکت جدید بزنید.")
        except Exception:
            pass
    await callback.answer("✅ تیکت بسته شد.")
    await callback.message.edit_reply_markup(reply_markup=admin_ticket_detail_keyboard(ticket))


@router.callback_query(F.data.startswith("admticketreopen_"))
async def admin_ticket_reopen(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
        return
    ticket_id = int(callback.data.replace("admticketreopen_", ""))
    db.set_ticket_status(ticket_id, "open")
    ticket = db.get_ticket(ticket_id)
    await callback.answer("🔓 تیکت دوباره باز شد.")
    await callback.message.edit_reply_markup(reply_markup=admin_ticket_detail_keyboard(ticket))
