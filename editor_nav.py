"""ناوبری ویرایشگر متن و دکمه‌ها: ۸ دسته‌ی اصلی ← صفحه‌ها ← مدیریت دکمه‌ها/متن‌ها + جستجو.

این ماژول فقط «لایه‌ی ناوبری» است؛ ذخیره‌سازی (متن، ایموجی پریمیوم، رنگ، مخفی‌کردن، جابه‌جایی، بازگشت به پیش‌فرض)
همچنان در ui_editor.py انجام می‌شود و اینجا دست‌کاری نمی‌شود.

منابع متن (اجتماع):  SCREENS  +  text_catalog  +  پیام‌های کشف‌شده‌ی خودکار (ui_discovery).
هر مورد در «پوشه‌ی» درست خودش قرار می‌گیرد؛ هر چیزی که جا نشده باشد در «🧾 سایر» می‌ماند تا هیچ متنی گم نشود.
"""
from __future__ import annotations

import ast
import os
import re

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import ui_editor as ue

PAGE_SIZE = 8

# (id, label)
CATS: list[tuple[str, str]] = [
    ("home", "🏠 شروع و منوی اصلی"),
    ("shop", "🛒 خرید و پلن‌ها"),
    ("pay", "💳 پرداخت و فاکتور"),
    ("wallet", "💰 کیف پول"),
    ("services", "📱 سرویس‌های من"),
    ("renew", "🔁 تمدید"),
    ("profile", "👥 پروفایل و دعوت دوستان"),
    ("support", "📞 پشتیبانی، راهنما و اعلان‌ها"),
]
OTHER = ("other", "🧾 سایر")
_CAT_LABEL = dict(CATS + [OTHER])

# --- صفحه‌ها (SCREENS) → دسته -------------------------------------------------
SCREEN_CAT: dict[str, str] = {}


def _put(cat: str, *keys: str) -> None:
    for k in keys:
        SCREEN_CAT[k] = cat


_put("home", "main_reply", "start", "start_welcome", "start_join_required", "join_confirmed")
_put("shop", "config_name", "buy_plans", "plans", "free_test_intro", "free_test_list_intro", "free_test_multi", "free_test",
     "vip_category_list", "vip_plans", "plan_select", "payg_name", "custom_build", "custom_build_options",
     "payg_options", "discount_code_entry")
_put("pay", "cbuild_payment_method", "cbuild_pay_wallet", "cbuild_pay_online", "cbuild_pay_card",
     "plan_payment_method", "plan_pay_wallet", "plan_pay_online", "gateway_tonpays_card", "plan_pay_card",
     "receipt_submitted", "card_payment_actions", "crypto_payment_detail", "insufficient_balance")
_put("wallet", "wallet", "wallet_free", "wallet_locked", "wallet_transactions", "wallet_charge",
     "walletcharge_method", "walletcharge_pay_card", "walletcharge_pay_online")
_put("services", "service_search_results", "services", "my_configs_empty", "my_configs_has", "my_configs_list_empty", "my_configs_list_has",
     "config_detail", "config_delete_confirm", "config_delivery", "config_copy_all")
_put("renew", "renew_payment_method", "renew_done", "renew_menu")
_put("profile", "referral", "referral_percent", "referral_both", "referral_cond_percent_first",
     "referral_cond_percent_every", "referral_join_percent_first", "referral_join_percent_every",
     "profile", "purchase_history")
_put("support", "ticket_list", "ticket_thread", "support", "ticket_write", "guides_empty", "guides_has", "agency_request", "agent_manage",
     "ticket_reply", "order_log", "notif_service_ended", "notif_fup_start", "notif_fup_blocked",
     "notif_payg_empty_suspend", "notif_payg_empty_delete", "notif_payg_resumed", "notif_wallet_low",
     "notif_usage_alert")

# پیشوندها (اعلان‌های رفرال و …) برای کلیدهای جدیدی که بعداً اضافه شوند
_SCREEN_PREFIX_CAT = (("notif_referral", "support"), ("notif_", "support"), ("referral_", "profile"),
                      ("walletcharge_", "wallet"), ("wallet_", "wallet"), ("renew_", "renew"),
                      ("cbuild_pay", "pay"), ("plan_pay", "pay"), ("gateway_", "pay"), ("config_", "services"),
                      ("my_configs", "services"), ("free_test", "shop"), ("vip_", "shop"), ("ticket_", "support"),
                      ("guides_", "support"), ("agent", "support"))

_LEGACY_SCREEN_CATEGORY = {"start": "home", "shop": "shop", "finance": "pay", "services": "services"}

# --- بخش‌های کاتالوگ/کشف‌شده → دسته --------------------------------------------
_SECTION_CAT = (
    ("شروع", "home"),
    ("خرید اشتراک", "shop"), ("سرویس سفارشی", "shop"), ("PAYG", "shop"), ("تست رایگان", "shop"), ("تخفیف", "shop"),
    ("فاکتور", "pay"), ("پرداخت ارزی", "pay"), ("درگاه", "pay"),
    ("کیف پول", "wallet"),
    ("سرویس‌های من", "services"), ("تحویل", "services"),
    ("تمدید", "renew"),
    ("پروفایل", "profile"), ("دعوت", "profile"),
    ("پشتیبانی", "support"), ("راهنما", "support"), ("اعلان", "support"), ("لاگ", "support"),
)


def _norm(s: str) -> str:
    return str(s or "").replace("‌", "").replace("‍", "")


def cat_of_section(section: str) -> str:
    n = _norm(section)
    for needle, cat in _SECTION_CAT:
        if _norm(needle) in n:
            return cat
    return "other"


def cat_of_screen(key: str) -> str:
    if key in SCREEN_CAT:
        return SCREEN_CAT[key]
    for pre, cat in _SCREEN_PREFIX_CAT:
        if str(key).startswith(pre):
            return cat
    return _LEGACY_SCREEN_CATEGORY.get((ue.SCREENS.get(key) or {}).get("category"), "other")


# --- دسته‌بندی دقیق پیام‌های کشف‌شده (فایل + تابع) -----------------------------
_AUTO_FILE_DEFAULT = {
    "alerts.py": "support", "gateways.py": "pay", "ticket.py": "support", "start.py": "home",
    "wallet.py": "wallet", "bot.py": "support", "admin.py": "home", "menu.py": "support", "plans.py": "shop",
}
# (regex روی نام تابع، دسته) — اولین تطبیق برنده است
_AUTO_FN_RULES = [
    (r"^invoice_expiry|^approve_purchase|^_plan_payment|^pay_with_|^check_online_payment|^receive_purchase_receipt"
     r"|^cbuild_pay|^charge_pay_crypto|^charge_crypto|^_create_invoice|^_below_min|^tonpays_|^gw_|^check_for_user", "pay"),
    (r"^menu_renew|^renew_|^_renew", "renew"),
    (r"^menu_wallet|^wallet_|^transactions$|^charge|^_offer_charge|^use_discount|^_wd_|^wd_|^_start_wallet|^receive_receipt", "wallet"),
    (r"^menu_my_configs|^service_search|^view_config|^user_change_sublink|^user_disable_sublink|^_send_configs"
     r"|^copy_|^wireguard_files|^mirror_configs|^delete_config|^purchase_config_name_input", "services"),
    (r"^menu_referral", "profile"),
    (r"^menu_ticket|^menu_agent|^menu_agency|^new_agent|^my_ticket|^ticket_|^_send_ended_alert|^global_error|^__call__", "support"),
    (r"^menu_plans|^_free_test|^menu_custom_button|^check_discount|^discount_for|^_cbuild|^cbuild_|^custom_|^_show_custom"
     r"|^_start_payg|^_payg_|^purchase_config_name_auto", "shop"),
    (r"^_on_user_left|^start$|^check_join|^subadm_|^_finalize_send", "home"),
]

_FN_CACHE: dict[str, list] = {}


def _enclosing_fn(source: str, line: int) -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, source)
    spans = _FN_CACHE.get(path)
    if spans is None:
        spans = []
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
            for n in ast.walk(tree):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    spans.append((n.lineno, n.end_lineno or n.lineno, n.name))
        except Exception:
            spans = []
        _FN_CACHE[path] = spans
    best = None
    for a, b, name in spans:
        if a <= line <= b and (best is None or a > best[0]):
            best = (a, name)
    return best[1] if best else ""


def cat_of_auto(item: dict) -> str:
    src = str(item.get("source") or "")
    fn = _enclosing_fn(src, int(item.get("line") or 0)) if src and item.get("line") else ""
    for rx, cat in _AUTO_FN_RULES:
        if fn and re.search(rx, fn):
            return cat
    base = os.path.basename(src)
    if base in _AUTO_FILE_DEFAULT and base not in ("menu.py", "plans.py", "admin.py", "bot.py"):
        return _AUTO_FILE_DEFAULT[base]
    c = cat_of_section(item.get("category") or "")
    if c != "other":
        return c
    return _AUTO_FILE_DEFAULT.get(base, "other")


# --- اقلام متن ---------------------------------------------------------------
def _short(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s[:n] + ("…" if len(s) > n else "")


_ITEMS_CACHE: dict | None = None


def _build_items() -> dict[str, list[dict]]:
    """{cat: [item]} ؛ item = {key, kind('screen'|'catalog'|'auto'), label, template}"""
    out: dict[str, list[dict]] = {c: [] for c, _ in CATS}
    out["other"] = []
    seen: set[str] = set()

    def add(cat: str, it: dict) -> None:
        if it["key"] in seen:
            return
        seen.add(it["key"])
        out.setdefault(cat, []).append(it)

    for key, sc in ue.SCREENS.items():
        if not sc.get("default") and not sc.get("vars") and key not in ("start",):
            continue  # صفحه‌ی فقط‌دکمه (متنش جای دیگری ساخته می‌شود)
        add(cat_of_screen(key), {"key": key, "kind": "screen", "label": sc.get("label", key), "template": sc.get("default", "")})
    try:
        import text_catalog as tc
        ue._discover_auto_messages()
        dead = ue._dead_catalog_keys()
        for section, entries in tc.TEXT_CATEGORIES.items():
            if section in ue._TEXT_ONLY_EXCLUDED_CATEGORIES:
                continue
            cat = cat_of_section(section)
            for k, d in entries:
                if ue._is_text_catalog_content_key(k) and k not in dead:
                    add(cat, {"key": k, "kind": "catalog", "label": "", "template": d})
        for it in ue._AUTO_REGISTRY.values():
            add(cat_of_auto(it), {"key": it["key"], "kind": "auto", "label": "", "template": it["template"],
                                  "source": it.get("source", "")})
    except Exception:
        pass
    return out


def items_map(refresh: bool = False) -> dict[str, list[dict]]:
    global _ITEMS_CACHE
    if _ITEMS_CACHE is None or refresh:
        _ITEMS_CACHE = _build_items()
    return _ITEMS_CACHE


def all_text_items() -> list[tuple[str, dict]]:
    return [(c, it) for c, lst in items_map().items() for it in lst]


def cat_of_text_key(key: str) -> str:
    for c, it in all_text_items():
        if it["key"] == key:
            return c
    if key in ue.SCREENS:
        return cat_of_screen(key)
    return "other"


def find_item(key: str) -> dict | None:
    for _c, it in all_text_items():
        if it["key"] == key:
            return it
    return None


def item_title(it: dict) -> str:
    if it.get("label"):
        return it["label"]
    cur = ue.get_text(it["key"], it.get("template", ""))
    return _short(cur or it.get("template", ""), 34) or it["key"]


def active_cats(mode: str) -> list[tuple[str, str]]:
    cats = list(CATS)
    if mode == "text":
        if items_map().get("other"):
            cats.append(OTHER)
    else:
        if _screens_in("other"):
            cats.append(OTHER)
    return cats


def cat_label(cat: str) -> str:
    return _CAT_LABEL.get(cat, cat)


# --- اقلام دکمه (صفحه‌ها) ----------------------------------------------------
def _screens_in(cat: str) -> list[str]:
    return [k for k, sc in ue.SCREENS.items() if ue.editable_buttons(k) and cat_of_screen(k) == cat]


def screens_in(cat: str) -> list[str]:
    return _screens_in(cat)


def button_count(cat: str) -> int:
    return sum(len(ue.editable_buttons(k)) for k in _screens_in(cat))


# --- کیبوردها -----------------------------------------------------------------
def _btn(text: str, cb: str, style: str = "primary", **kw) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text[:60], callback_data=cb, style=style, **kw)


def _pager(rows: list, page: int, total: int, cb_fmt: str) -> None:
    nav = []
    if page > 0:
        nav.append(_btn("⬅️ قبلی", cb_fmt.format(page - 1)))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(_btn("بعدی ➡️", cb_fmt.format(page + 1)))
    if nav:
        rows.append(nav)


def categories_keyboard(mode: str) -> InlineKeyboardMarkup:
    """mode: 'text' | 'buttons'"""
    rows = []
    tag = "t" if mode == "text" else "b"
    for cid, label in active_cats(mode):
        if mode == "text":
            n = len(items_map().get(cid, []))
            suffix = f" ({n} متن)"
        else:
            scs = _screens_in(cid)
            suffix = f" ({len(scs)} صفحه، {button_count(cid)} دکمه)"
        rows.append([_btn(label + suffix, f"ui_nav:{tag}c:{cid}:0")])
    rows.append([_btn("🔎 جستجو" + (" در متن‌ها" if mode == "text" else " در دکمه‌ها"), f"ui_nav:{tag}s")])
    rows.append([_btn("🔙 بازگشت", "admin_text_editor", "danger")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def text_list_keyboard(cat: str, page: int = 0) -> InlineKeyboardMarkup:
    items = items_map().get(cat, [])
    start = page * PAGE_SIZE
    rows = []
    for it in items[start:start + PAGE_SIZE]:
        mark = "✅ " if ue.has_text_override(it["key"]) else "✏️ "
        rows.append([_btn(mark + item_title(it), f"ui_nav:tk:{it['key']}")])
    _pager(rows, page, len(items), f"ui_nav:tc:{cat}:{{}}")
    rows.append([_btn("🔎 جستجو", "ui_nav:ts")])
    rows.append([_btn("🔙 بازگشت به دسته‌ها", "ui_mode:text", "danger")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pages_keyboard(cat: str, page: int = 0) -> InlineKeyboardMarkup:
    scs = _screens_in(cat)
    start = page * PAGE_SIZE
    rows = []
    for k in scs[start:start + PAGE_SIZE]:
        sc = ue.SCREENS[k]
        rows.append([_btn(f"{sc.get('label', k)} ({len(ue.editable_buttons(k))})", f"ui_screen:buttons:{k}")])
    _pager(rows, page, len(scs), f"ui_nav:bc:{cat}:{{}}")
    rows.append([_btn("🔎 جستجو", "ui_nav:bs")])
    rows.append([_btn("🔙 بازگشت به دسته‌ها", "ui_mode:buttons", "danger")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def text_detail_keyboard(key: str) -> InlineKeyboardMarkup:
    cat = cat_of_text_key(key)
    rows = [[_btn("✏️ ویرایش این متن", f"ui_nav:te:{key}")]]
    if ue.has_text_override(key):
        rows.append([_btn("♻️ بازگشت به پیش‌فرض", f"ui_nav:tr:{key}", "danger")])
    rows.append([_btn("🔙 به فهرست دسته", f"ui_nav:tc:{cat}:0", "danger"), _btn("🏠 دسته‌ها", "ui_mode:text", "danger")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("✅ ذخیره", "ui_nav:ok", "success"), _btn("❌ انصراف", "ui_nav:no", "danger")],
        [_btn("✏️ متن دیگر", "ui_nav:again")],
    ])


def after_save_keyboard(kind: str, key: str, screen_key: str = "", callback_key: str = "") -> InlineKeyboardMarkup:
    if kind == "button":
        cat = cat_of_screen(screen_key)
        rows = [
            [_btn("✏️ ویرایش دوباره", f"ui_button:{screen_key}:{callback_key}")],
            [_btn("🔙 به صفحه‌ی دکمه‌ها", f"ui_screen:buttons:{screen_key}", "danger")],
            [_btn("📂 دسته", f"ui_nav:bc:{cat}:0", "danger"), _btn("🏠 ویرایشگر", "admin_text_editor", "danger")],
        ]
    else:
        cat = cat_of_text_key(key)
        rows = [
            [_btn("✏️ ویرایش دوباره", f"ui_nav:te:{key}")],
            [_btn("🔙 به این متن", f"ui_nav:tk:{key}", "danger")],
            [_btn("📂 دسته", f"ui_nav:tc:{cat}:0", "danger"), _btn("🏠 ویرایشگر", "admin_text_editor", "danger")],
        ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# --- جستجو --------------------------------------------------------------------
def search_text(q: str) -> list[dict]:
    q = _norm(q).lower().strip()
    if not q:
        return []
    out = []
    for c, it in all_text_items():
        hay = _norm(" ".join([it["key"], it.get("label", ""), it.get("template", ""),
                              ue.get_text(it["key"], it.get("template", "")) or ""])).lower()
        if q in hay:
            out.append(it)
    return out


def search_buttons(q: str) -> list[tuple[str, str, str]]:
    """[(screen_key, callback_key, label)]"""
    q = _norm(q).lower().strip()
    if not q:
        return []
    out = []
    for sk, sc in ue.SCREENS.items():
        for cb, label in ue.editable_buttons(sk):
            cur = ue.get_button(sk, cb, label)
            if q in _norm(f"{label} {cur} {cb}").lower():
                out.append((sk, cb, cur))
    return out


def text_results_keyboard(q_items: list[dict], page: int = 0) -> InlineKeyboardMarkup:
    start = page * PAGE_SIZE
    rows = [[_btn(f"✏️ {item_title(it)}  ·  {_short(cat_label(cat_of_text_key(it['key'])), 14)}", f"ui_nav:tk:{it['key']}")]
            for it in q_items[start:start + PAGE_SIZE]]
    _pager(rows, page, len(q_items), "ui_nav:tsp:{}")
    rows.append([_btn("🔎 جستجوی دیگر", "ui_nav:ts"), _btn("🔙 دسته‌ها", "ui_mode:text", "danger")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def button_results_keyboard(res: list[tuple[str, str, str]], page: int = 0) -> InlineKeyboardMarkup:
    start = page * PAGE_SIZE
    rows = []
    for sk, cb, label in res[start:start + PAGE_SIZE]:
        rows.append([_btn(f"✏️ {label}", f"ui_button:{sk}:{cb}")])
        rows.append([_btn(f"📂 {ue.SCREENS[sk].get('label', sk)}", f"ui_screen:buttons:{sk}")])
    _pager(rows, page, len(res), "ui_nav:bsp:{}")
    rows.append([_btn("🔎 جستجوی دیگر", "ui_nav:bs"), _btn("🔙 دسته‌ها", "ui_mode:buttons", "danger")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# --- متغیرها ------------------------------------------------------------------
def variables_block(key: str) -> str:
    """فهرست کامل متغیرهای قابل‌استفاده (نام — کاربرد/توضیح) برای یک متن."""
    tpl = (ue.SCREENS.get(key) or {}).get("default") or ""
    if not tpl:
        fnd = ue.text_catalog_find(key)
        tpl = fnd[1] if fnd else ""
    if not tpl:
        tpl = (find_item(key) or {}).get("template", "") or ""
    return ue.variables_help(key, tpl)
