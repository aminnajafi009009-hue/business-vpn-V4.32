"""
handlers/referral.py
نمایش لینک دعوت اختصاصی، کد اختصاصی، و آمار دعوت دوستان
(تعداد دعوت، دعوت‌های موفق، مبلغ آزاد شده، مبلغ در انتظار).
"""

import ui_editor


from aiogram import Router, F, types

import database as db
import bot_info
from utils import show_menu_with_sticker

from keyboards import referral_menu

router = Router(name="referral")


async def send_referral(bot, chat_id: int, tg_id: int) -> bool:
    user = db.get_user(tg_id)
    if user is None:
        return False
    if not db.referral_enabled():
        await bot.send_message(chat_id, "این بخش در حال حاضر غیرفعال است.")
        return True

    stats = db.get_referral_stats(user["id"])
    invite_link = f"https://t.me/{bot_info.get('bot_username')}?start={stats['invite_code']}"

    rs = db.get_referral_settings()
    # 🆕 این سه متن پیش‌فرض هستند و از پنل ادمین (ویرایش متن ← 👥 دعوت دوستان)
    # کاملاً قابل‌تغییرند؛ چون کل صفحه حالا از یک قالب با placeholder رندر
    # می‌شود (نگاه کن به SCREENS["referral"] در ui_editor.py)، ادمین می‌تواند
    # کل جمله‌ی شرط رفرال از جمله «مقدار خرید کاربر دعوت‌شده» را عیناً حذف کند
    # یا هر جور دلش خواست بازنویسی کند — چیزی هاردکد در پایتون قفل نشده.
    import referral_texts as rt
    condition_text = rt.condition_text(rs)

    template_values = {
        "reward_amount": f"{rs['reward_amount']:,}",
        "invite_link": invite_link,
        "invite_code": stats["invite_code"],
        "invited_count": stats["invited_count"],
        "successful_invites": stats["successful_invites"],
        "released_amount": f"{stats['released_amount']:,}",
        "locked_wallet": f"{user['locked_wallet']:,}",
        "wallet_balance": f"{int(user['wallet'] or 0):,}",
        "condition_text": condition_text,
        # نام‌های کاتالوگ «ویرایش متن ← 👥 دعوت دوستان» (referral_overview) — عددی تا قالب‌هایی مثل {reward:,} کار کنند
        "reward": int(rs["reward_amount"] or 0),
        "released": int(stats["released_amount"] or 0),
        "locked": int(user["locked_wallet"] or 0),
        "wallet": int(user["wallet"] or 0),
        "min_gb": rs["min_volume_gb"],
        "percent": f"{float(rs.get('percent_rate') or 0):g}",
        "commission_total": f"{int(stats.get('commission_total') or 0):,}",
        "commission_count": int(stats.get("commission_count") or 0),
    }
    await show_menu_with_sticker(
        bot, chat_id, rt.screen_key(rs), None,
        reply_markup=referral_menu(), template_values=template_values,
    )
    return True


@router.callback_query(F.data == "referral")
async def referral(callback: types.CallbackQuery):
    if not await send_referral(callback.bot, callback.message.chat.id, callback.from_user.id):
        await callback.answer(ui_editor.get_alert_text("msg_18ae2939df", "ابتدا دستور /start را بزنید."), show_alert=True)
        return
    await callback.answer()
