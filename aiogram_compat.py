"""
aiogram_compat.py
=================
تلگرام بلاک‌های جدیدی به Rich Message اضافه می‌کند (مثل بلاک «buttons» = دکمه‌های داخل پیام، که در پست‌های کانال می‌بینید)
که aiogram 3.30 نمی‌شناسد. وقتی ادمین چنین پیامی را به ربات می‌فرستاد (مثلاً برای «پیام همگانی»)، کل getUpdates با
ClientDecodeError خراب می‌شد و چون offset جلو نمی‌رفت، ربات برای همیشه روی همان آپدیت گیر می‌کرد.

اینجا پاسخ تلگرام قبل از اعتبارسنجی «پاک‌سازی» می‌شود:
  ۱) بلاک‌های ناشناخته‌ی rich_message از blocks جدا می‌شوند ولی کل بلاک‌ها (دقیقاً به همان شکل) در فیلد raw_blocks نگه داشته می‌شوند
     (در همه‌ی سطوح؛ یعنی reply_to_message و … هم). «پیام همگانی» با copy_message پیام را عیناً (با همه‌ی بلاک‌ها) می‌فرستد.
  ۲) اگر باز هم اعتبارسنجی خراب شد و پاسخ rich_message داشت، rich_message از آن آپدیت برداشته می‌شود (به‌جای گیرکردن ربات).
"""
from __future__ import annotations

import json
import logging

from aiogram.client.session.base import BaseSession
from aiogram.exceptions import ClientDecodeError

logger = logging.getLogger(__name__)

try:
    from aiogram.enums import RichBlockType
    _KNOWN = {e.value for e in RichBlockType}
except Exception:  # pragma: no cover
    _KNOWN = set()


def _sanitize(obj, mode: str) -> bool:
    """mode='blocks': فقط بلاک‌های ناشناخته؛ mode='drop': کل rich_message. True اگر چیزی عوض شد."""
    changed = False
    if isinstance(obj, dict):
        rm = obj.get("rich_message")
        if isinstance(rm, dict) and isinstance(rm.get("blocks"), list):
            blocks = rm["blocks"]
            if mode == "drop":
                obj["raw_rich_message"] = rm
                obj.pop("rich_message", None)
                changed = True
            elif _KNOWN and any(not isinstance(b, dict) or b.get("type") not in _KNOWN for b in blocks):
                rm["raw_blocks"] = list(blocks)
                rm["blocks"] = [b for b in blocks if isinstance(b, dict) and b.get("type") in _KNOWN]
                changed = True
        for v in list(obj.values()):
            if isinstance(v, (dict, list)) and _sanitize(v, mode):
                changed = True
    elif isinstance(obj, list):
        for v in obj:
            if isinstance(v, (dict, list)) and _sanitize(v, mode):
                changed = True
    return changed


_orig_check = BaseSession.check_response


def _patched_check(self, bot, method, status_code, content):
    if isinstance(content, str) and '"rich_message"' in content:
        try:
            data = json.loads(content)
            if _sanitize(data, "blocks"):
                content = json.dumps(data, ensure_ascii=False)
        except Exception:
            logger.debug("aiogram_compat: sanitize failed", exc_info=True)
    try:
        return _orig_check(self, bot, method, status_code, content)
    except ClientDecodeError:
        if isinstance(content, str) and '"rich_message"' in content:
            try:
                data = json.loads(content)
                if _sanitize(data, "drop"):
                    logger.warning("aiogram_compat: rich_message ناشناخته؛ از آپدیت حذف شد تا polling گیر نکند")
                    return _orig_check(self, bot, method, status_code, json.dumps(data, ensure_ascii=False))
            except ClientDecodeError:
                raise
            except Exception:
                logger.debug("aiogram_compat: drop retry failed", exc_info=True)
        raise


def install() -> None:
    if BaseSession.check_response is not _patched_check:
        BaseSession.check_response = _patched_check


install()
