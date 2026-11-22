import asyncio
import sqlite3
import logging
import time
import aiohttp
import json
import os
import contextvars
from datetime import datetime
from io import BytesIO

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile, ReplyKeyboardRemove
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# =====================================================================
# [ កំណត់រចនាសម្ព័ន្ធទូទៅ ]
# =====================================================================
BOT_TOKEN = "8316333314:AAGNfkbnyQy5AZOBAmzQL6REbkZBPrNjm5M"
ADMIN_ID = 7708363434

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

_ctx_db_path: contextvars.ContextVar[str] = contextvars.ContextVar("ctx_db_path", default="topup_system.db")
_ctx_admin_id: contextvars.ContextVar[int] = contextvars.ContextVar("ctx_admin_id", default=ADMIN_ID)
_ctx_is_clone: contextvars.ContextVar[bool] = contextvars.ContextVar("ctx_is_clone", default=False)
_bot_configs: dict[int, tuple[str, int, bool]] = {}
_clone_tasks: dict[int, asyncio.Task] = {}

def get_admin_id() -> int:
    return _ctx_admin_id.get()

@dp.update.outer_middleware()
async def _clone_context_middleware(handler, event, data):
    b = data.get("bot")
    if b and b.id in _bot_configs:
        db_p, adm_id, is_cl = _bot_configs[b.id]
        t1 = _ctx_db_path.set(db_p)
        t2 = _ctx_admin_id.set(adm_id)
        t3 = _ctx_is_clone.set(is_cl)
        try:
            return await handler(event, data)
        finally:
            _ctx_db_path.reset(t1)
            _ctx_admin_id.reset(t2)
            _ctx_is_clone.reset(t3)
    return await handler(event, data)

# =====================================================================
# [ DATABASE ]
# =====================================================================
def init_db():
    init_db_for("topup_system.db", ADMIN_ID, is_clone=False)

def init_db_for(db_path: str, admin_id: int, is_clone: bool = False):
    parent_dir = os.path.dirname(db_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY, 
        balance REAL DEFAULT 0, 
        is_admin INTEGER DEFAULT 0, 
        name TEXT,
        total_spent REAL DEFAULT 0,
        total_orders INTEGER DEFAULT 0,
        last_order_date TEXT,
        is_premium INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS games (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        name TEXT, 
        game_code TEXT, 
        emoji_id TEXT,
        id_label TEXT,
        server_label TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS packages (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        game_id INTEGER, 
        name TEXT, 
        product_code TEXT, 
        price REAL, 
        emoji_id TEXT,
        tag TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS deposits (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        user_id INTEGER, 
        amount REAL, 
        ref_id TEXT, 
        status TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        user_id INTEGER, 
        game TEXT, 
        pack TEXT, 
        price REAL, 
        status TEXT, 
        ref_id TEXT, 
        date TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY, 
        value TEXT
    )""")

    try: c.execute("ALTER TABLE users ADD COLUMN total_spent REAL DEFAULT 0")
    except: pass
    try: c.execute("ALTER TABLE users ADD COLUMN total_orders INTEGER DEFAULT 0")
    except: pass
    try: c.execute("ALTER TABLE users ADD COLUMN last_order_date TEXT")
    except: pass
    try: c.execute("ALTER TABLE users ADD COLUMN is_premium INTEGER DEFAULT 0")
    except: pass
    try: c.execute("ALTER TABLE games ADD COLUMN id_label TEXT")
    except: pass
    try: c.execute("ALTER TABLE games ADD COLUMN server_label TEXT")
    except: pass
    try: c.execute("ALTER TABLE packages ADD COLUMN tag TEXT")
    except: pass

    if not is_clone:
        c.execute("""CREATE TABLE IF NOT EXISTS cloned_bots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER UNIQUE,
            username TEXT,
            token TEXT,
            admin_id INTEGER,
            db_path TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT
        )""")

    c.execute('INSERT OR IGNORE INTO users (id, is_admin, name) VALUES (?, 1, "Admin")', (admin_id,))
    c.execute('UPDATE users SET is_admin=1 WHERE id=?', (admin_id,))

    # Settings សម្រាប់ TOPUP API (khmer-topup.com) តាម api URL.py
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("topup_api", "https://khmer-topup.com/api/v1")')
    if not is_clone:
        c.execute('INSERT OR REPLACE INTO settings (key, value) VALUES ("topup_api", "https://khmer-topup.com/api/v1")')
        c.execute('INSERT OR REPLACE INTO settings (key, value) VALUES ("topup_key", "kt_92a981610e7ba1ebb35447447057406ab8ce1536")')
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("vng_api", "https://www.vngzz2game.site/api/v1")')
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("vng_key", "pwrUNoXbvETmidNt8DbF6jAsVJXqPY4W")')
    else:
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("topup_key", "")')
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("vng_api", "https://www.vngzz2game.site/api/v1")')
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("vng_key", "")')

    # Settings សម្រាប់ ABA PAYMENT (Khmer System) តាម bot.py
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("aba_base_url", "https://khmer-system.com")')
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("aba_create_url", "https://khmer-system.com/aba-api/generate-qr")')
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("aba_check_url", "https://khmer-system.com/aba-api/check-payment")')
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("aba_api_key", "")')
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("aba_merchant_id", "")')
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("aba_pay_enabled", "1")')

    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("profit_margin", "0")')
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("static_qr_file_id", "")')
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("static_qr_enabled", "1")')
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("maintenance_mode", "0")')
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("maintenance_text", "ប្រព័ន្ធកំពុងស្ថិតក្នុងការជួសជុល និងថែទាំបណ្ដោះអាសន្ន។ សូមអភ័យទោសចំពោះការរំខាន។")')
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("start_text", "")')
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("start_media_id", "")')
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("start_media_type", "")')

    conn.commit()
    conn.close()

def db_query(query, params=(), fetch=False, fetchall=False, db_path=None):
    conn = sqlite3.connect(db_path or _ctx_db_path.get())
    c = conn.cursor()
    c.execute(query, params)
    if fetchall: res = c.fetchall()
    elif fetch: res = c.fetchone()
    else:
        conn.commit()
        res = c.lastrowid
    conn.close()
    return res

init_db()

def get_setting(key):
    res = db_query("SELECT value FROM settings WHERE key=?", (key,), fetch=True)
    return res[0] if res else ""

def set_setting(key, value):
    db_query("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))

def is_user_admin(uid: int) -> bool:
    if uid == get_admin_id():
        return True
    res = db_query("SELECT is_admin FROM users WHERE id=?", (uid,), fetch=True)
    return bool(res and res[0] == 1)

def check_maintenance(uid: int) -> bool:
    if is_user_admin(uid):
        return False
    return get_setting("maintenance_mode") == "1"

# =====================================================================
# [ EMOJI PREMIUM & STYLE COLOR KEYBOARDS ]
# =====================================================================
def pemoji(emoji_id: str, fallback: str = "✨") -> str:
    """បង្ហាញ Custom Premium Animated Emoji ក្នុងអត្ថបទ Message"""
    if emoji_id:
        return f"<tg-emoji emoji-id='{emoji_id}'>{fallback}</tg-emoji>"
    return fallback

def IBtn(text, callback_data, style="primary", icon_custom_emoji_id=None):
    """ប៊ូតុង InlineKeyboard ជាមួយ Style Color (primary, success, danger) និង Emoji Premium"""
    btn = InlineKeyboardButton(text=text, callback_data=callback_data)
    if style: object.__setattr__(btn, 'style', style)
    if icon_custom_emoji_id:
        object.__setattr__(btn, 'icon_custom_emoji_id', str(icon_custom_emoji_id))
    return btn

def RBtn(text, style="primary", icon_custom_emoji_id=None):
    """ប៊ូតុង ReplyKeyboard ជាមួយ Style Color (primary, success, danger) និង Emoji Premium"""
    btn = KeyboardButton(text=text)
    if style: object.__setattr__(btn, 'style', style)
    if icon_custom_emoji_id:
        object.__setattr__(btn, 'icon_custom_emoji_id', str(icon_custom_emoji_id))
    return btn

CUSTOM_EMOJI_BUTTONS = [
    ("btn_account", "គណនី", "5458585579866307689"),
    ("btn_deposit", "បព្ចូាលលុយ", "6001434068435079689"),
    ("btn_topup", "ថប់អាប់ហ្គេម", "5427168083074628963"),
    ("btn_orders", "ការបព្ជាទិញ", "5884479287171485878"),
    ("btn_ticket", "សំបុត្រ", "5418010521309815154"),
    ("btn_top_buyers", "កំពូលអ្នកទិញ", "6194737030165959506"),
    ("btn_admin_panel", "ADMIN PANEL", "5895592588064328942"),
    ("btn_ord_all", "All (Orders)", "6154222749691679144"),
    ("btn_ord_pending", "Pending", "5386367538735104399"),
    ("btn_ord_completed", "Completed", "6023773095284707791"),
    ("btn_ord_failed", "Failed", "6176808917549453468"),
    ("btn_ord_canceled", "Canceled", "6176808917549453468"),
    ("btn_ord_search", "Search Ordes", "5445023138297447592"),
    ("btn_ord_dep_hist", "ប្រវត្តិការបព្ចូាលលុយ", "6023773095284707791"),
    ("btn_ord_back", "ត្រលប់ (Orders)", "6071034593287345457"),
    ("btn_tk_owner", "ធ្ញើសារទៅ Owner", "5335054400513649848"),
    ("btn_tk_diamond", "Diamon អត់ដំណើការ", "6176808917549453468"),
    ("btn_tk_money", "ដាក់លុយអត់ចូល", "6176808917549453468"),
    ("btn_tk_back", "Back To Menu", "5253997076169115797"),
    ("btn_page_prev", "ថយទំព័រវិញ", "6071034593287345457"),
    ("btn_page_next", "ទំព័រមួយទៀត", "6071226041454564573"),
    ("btn_inline_back", "ត្រលប់ (Game/Pack)", "5253997076169115797"),
    ("btn_confirm_buy", "យល់ព្រមទិញ", "6023773095284707791"),
    ("btn_cancel_buy", "មិនយល់ព្រមទិញ", "5253997076169115797"),
    ("btn_reenter_id", "វាយបញ្ចូល ID ម្ដងទៀត", ""),
    ("btn_khqr_pay", "បង់ប្រាក់ KHQR", "6314519407443845610"),
    ("btn_default_pack", "កញ្ចប់ហ្គេម (Packages)", "5427168083074628963"),
]

def get_btn_emoji(key: str, default_id: str = "") -> str | None:
    custom = get_setting(f"ce_{key}")
    if custom and str(custom).strip():
        return str(custom).strip()
    return default_id if default_id else None


def calc_price(base_price: float) -> float:
    try:
        pct = float(get_setting("profit_margin") or 0)
        if pct <= 0:
            return float(base_price)
        return float(base_price) * (1.0 + (pct / 100.0))
    except Exception:
        return float(base_price)

# =====================================================================
# [ ពិនិត្យ PLAYER ID ឆ្លាតវៃ និងលឿនរហ័ស (FAST PARALLEL CHECK) ]
# =====================================================================
def get_topup_headers():
    default_key = "" if _ctx_is_clone.get() else "kt_92a981610e7ba1ebb35447447057406ab8ce1536"
    key = get_setting("topup_key") or default_key
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

async def _check_single_vng(session, base_url, api_key, game, pid, zid):
    try:
        headers = {"X-API-Key": api_key, "User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        params = {"game": str(game).strip(), "userid": str(pid).strip()}
        if zid and str(zid).strip():
            params["zoneid"] = str(zid).strip()
        async with session.get(f"{base_url}/game/check_id", params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=4)) as resp:
            text = await resp.text()
            try: data = json.loads(text)
            except: return None
            if isinstance(data, dict):
                if data.get("valid") is True or str(data.get("status", "")).upper() in ["APPROVED", "SUCCESS"]:
                    uname = data.get("username") or data.get("name") or data.get("nickname")
                    if uname:
                        return str(uname).strip()
    except: pass
    return None

async def _check_single_kt(session, base_url, token, slug, pid, zid):
    try:
        headers = {"Authorization": f"Bearer {token}", "User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        params = {"slug": str(slug).strip(), "player_id": str(pid).strip()}
        if zid and str(zid).strip():
            params["server_id"] = str(zid).strip()
        async with session.get(f"{base_url}/check", params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=4)) as resp:
            text = await resp.text()
            try: data = json.loads(text)
            except: return None
            if isinstance(data, dict):
                if data.get("result") == "valid" or data.get("nickname"):
                    uname = data.get("nickname") or data.get("username") or data.get("name")
                    if uname:
                        return str(uname).strip()
    except: pass
    return None

# ឆែក Player ID លឿនបំផុតក្នុងរង្វង់ 1-2 វិនាទី គាំទ្រទាំង Free Fire (គ្រប់ server) និង Mobile Legends
async def api_topup_check_player(slug, player_id, server_id=None):
    clean_slug = str(slug or "").strip().lower()
    clean_pid = str(player_id or "").strip()
    clean_zid = str(server_id or "").strip()

    # សម្អាតចោលពាក្យ Menu ជៀសវាងការច្រឡំ Zone ID
    menu_words = ["admin panel", "គណនី", "ថប់អាប់ហ្គេម", "ការបព្ជាទិញ", "សំបុត្រ", "កំពូលអ្នកទិញ", "បព្ចូាលលុយ", "ត្រលប់", "none", "null"]
    if clean_zid.lower() in menu_words:
        clean_zid = ""

    if not clean_pid:
        return {"result": "invalid"}

    # បង្កើតបញ្ជីឈ្មោះ Game Code ដើម្បីស្វែងរកគ្រប់ Server
    slug_candidates = [clean_slug]
    if "free" in clean_slug:
        slug_candidates = ["freefire_sgmy", "freefire", "free-fire", "freefire_tw", "freefire_taiwan", "free-fire-global", clean_slug]
    elif "mobile" in clean_slug or "mlbb" in clean_slug:
        slug_candidates = ["mobile-legends", "mlbb", "mobile_legends", "mobile_legends_cambodia", clean_slug]
    elif "pubg" in clean_slug:
        slug_candidates = ["pubg-mobile", "pubgm", "pubg_mobile", clean_slug]
    elif "hok" in clean_slug or "honor" in clean_slug:
        slug_candidates = ["honor-of-kings", "hok", "honor_of_kings", clean_slug]

    seen = set()
    unique_slugs = [s for s in slug_candidates if not (s in seen or seen.add(s))]

    kt_api = (get_setting("topup_api") or "https://khmer-topup.com/api/v1").rstrip("/")
    kt_key = get_setting("topup_key") or ("" if _ctx_is_clone.get() else "kt_92a981610e7ba1ebb35447447057406ab8ce1536")

    vng_api = (get_setting("vng_api") or "https://www.vngzz2game.site/api/v1").rstrip("/")
    vng_key = get_setting("vng_key") or ("" if _ctx_is_clone.get() else "pwrUNoXbvETmidNt8DbF6jAsVJXqPY4W")

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
        tasks = []
        for s in unique_slugs[:4]:
            tasks.append(_check_single_vng(session, vng_api, vng_key, s, clean_pid, clean_zid))
            if clean_zid:
                tasks.append(_check_single_vng(session, vng_api, vng_key, s, clean_pid, ""))
            tasks.append(_check_single_kt(session, kt_api, kt_key, s, clean_pid, clean_zid))
            if clean_zid:
                tasks.append(_check_single_kt(session, kt_api, kt_key, s, clean_pid, ""))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if isinstance(res, str) and res.strip():
                return {"result": "valid", "nickname": res.strip()}

    return {"result": "unverified"}

async def api_topup_me():
    base = (get_setting("topup_api") or "https://khmer-topup.com/api/v1").rstrip("/")
    headers = get_topup_headers()
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(f"{base}/me", headers=headers) as resp:
                text = await resp.text()
                try: return json.loads(text)
                except: return await resp.json(content_type=None)
    except Exception as e:
        logging.error(f"API Topup Me Error: {e}")
    return None

async def api_topup_get_games():
    base = (get_setting("topup_api") or "https://khmer-topup.com/api/v1").rstrip("/")
    headers = get_topup_headers()
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.get(f"{base}/games", headers=headers) as resp:
                text = await resp.text()
                try: return json.loads(text)
                except: return await resp.json(content_type=None)
    except Exception as e:
        logging.error(f"API Topup Get Games Error: {e}")
    return None

async def api_topup_create_order(package_id, player_id, reference, server_id=None):
    base = (get_setting("topup_api") or "https://khmer-topup.com/api/v1").rstrip("/")
    headers = get_topup_headers()
    payload = {
        "package_id": int(package_id),
        "player_id": str(player_id).strip(),
        "reference": str(reference).strip()
    }
    if server_id and str(server_id).strip():
        payload["server_id"] = str(server_id).strip()

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
            async with session.post(f"{base}/orders", json=payload, headers=headers) as resp:
                text = await resp.text()
                try: return json.loads(text)
                except: return {"status": "error", "message": text[:500]}
    except Exception as e:
        logging.error(f"API Topup Create Order Error: {e}")
    return None

async def api_topup_get_order(order_code):
    base = (get_setting("topup_api") or "https://khmer-topup.com/api/v1").rstrip("/")
    headers = get_topup_headers()
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(f"{base}/orders/{order_code}", headers=headers) as resp:
                text = await resp.text()
                try: return json.loads(text)
                except: return None
    except Exception as e:
        logging.error(f"API Topup Get Order Error: {e}")
    return None

# =====================================================================
# [ ABA PAYMENT (Khmer System) ]
# =====================================================================
_active_deposits: dict[int, dict] = {}

async def api_aba_generate_qr(amount, username):
    create_url = get_setting("aba_create_url") or "https://khmer-system.com/aba-api/generate-qr"
    api_key = get_setting("aba_api_key")
    merchant_id = get_setting("aba_merchant_id")

    payload = {
        "api_key": api_key,
        "merchant_id": merchant_id,
        "username": str(username or "user")[:64],
        "amount": round(float(amount), 2)
    }
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as session:
            async with session.post(create_url, json=payload, headers=headers) as resp:
                text = await resp.text()
                try: data = json.loads(text)
                except: data = await resp.json(content_type=None)
                if isinstance(data, dict) and (data.get("ok") or data.get("payment_id") or (data.get("data") or {}).get("payment_id")):
                    return data
                return None
    except Exception as e:
        logging.error(f"ABA Generate QR Exception: {e}")
    return None

async def api_aba_check_paid(payment_id):
    if not payment_id:
        return False
    check_url = get_setting("aba_check_url") or "https://khmer-system.com/aba-api/check-payment"
    api_key = get_setting("aba_api_key")
    merchant_id = get_setting("aba_merchant_id")

    payload = {
        "api_key": api_key,
        "merchant_id": merchant_id,
        "payment_id": str(payment_id)
    }
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
            async with session.post(check_url, json=payload, headers=headers) as resp:
                text = await resp.text()
                try: data = json.loads(text)
                except: data = await resp.json(content_type=None)

                if isinstance(data, dict):
                    d = data.get("data") if isinstance(data.get("data"), dict) else {}
                    st = str(data.get("status") or data.get("payment_status") or d.get("status") or d.get("payment_status") or "").strip().upper()
                    if st in ("PAID", "SUCCESS", "COMPLETED", "APPROVED", "CONFIRMED"):
                        return True
                    if data.get("paid") is True or d.get("paid") is True:
                        return True
    except Exception as e:
        logging.error(f"ABA Check Paid Exception: {e}")
    return False

def extract_aba_fields(data: dict):
    d = data.get("data") if isinstance(data.get("data"), dict) else {}
    payment_id = data.get("payment_id") or d.get("payment_id") or data.get("id")
    qr_image = data.get("qr_image") or data.get("card_image") or data.get("image") or d.get("qr_image") or d.get("card_image")
    pay_url = data.get("pay_url") or data.get("checkout_url") or d.get("pay_url")
    return payment_id, qr_image, pay_url

async def poll_aba_payment_loop(bot: Bot, uid: int, chat_id: int, amount: float, payment_id: str, msg_id: int, max_minutes: int = 5, db_path: str = "topup_system.db", admin_id: int = ADMIN_ID):
    t1 = _ctx_db_path.set(db_path)
    t2 = _ctx_admin_id.set(admin_id)
    dep_key = (db_path, uid)
    try:
        deadline = time.time() + (max_minutes * 60)
        while time.time() < deadline:
            await asyncio.sleep(8)
            is_paid = await api_aba_check_paid(payment_id)
            if is_paid:
                dep = db_query("SELECT status FROM deposits WHERE ref_id=?", (str(payment_id),), fetch=True)
                if dep and dep[0] == "PAID":
                    return
                db_query("UPDATE deposits SET status='PAID' WHERE ref_id=?", (str(payment_id),))
                db_query("UPDATE users SET balance=balance+? WHERE id=?", (amount, uid))
                u = db_query("SELECT balance FROM users WHERE id=?", (uid,), fetch=True)
                new_bal = u[0] if u else amount

                try: await bot.delete_message(chat_id, msg_id)
                except: pass

                text = (f"{pemoji('6023773095284707791', '✅')} <b>ការទូទាត់ទទួលបានជោគជ័យ!</b>\n\n"
                        f"{pemoji('6001434068435079689', '💰')} ប្រាក់បញ្ចូល : <b>${amount:.2f}</b>\n"
                        f"{pemoji('5458585579866307689', '👤')} សមតុល្យថ្មី : <b>${new_bal:.2f}</b>\n\n"
                        f"សូមអរគុណបងដែលបានប្រើប្រាស់សេវាកម្មរបស់យើងខ្ញុំ!")
                await bot.send_message(uid, text)

                if admin_id:
                    try:
                        await bot.send_message(
                            admin_id,
                            f"{pemoji('6001434068435079689', '💰')} <b>Auto Deposit (ABA)</b>\nUser: <code>{uid}</code>\nAmount: <b>${amount:.2f}</b>\nRef: <code>{payment_id}</code>"
                        )
                    except: pass
                return

        db_query("UPDATE deposits SET status='EXPIRED' WHERE ref_id=? AND status='PENDING'", (str(payment_id),))
        try:
            await bot.delete_message(chat_id, msg_id)
            await bot.send_message(chat_id, f"{pemoji('6176808917549453468', '❌')} QR Code ផុតកំណត់ ឬមិនទាន់បានបង់ប្រាក់។ សូមបញ្ចូលម្ដងទៀត។")
        except: pass
    finally:
        _active_deposits.pop(dep_key, None)
        _ctx_db_path.reset(t1)
        _ctx_admin_id.reset(t2)

# =====================================================================
# [ STATES (FSM) ]
# =====================================================================
class FlowState(StatesGroup):
    dep_amount = State()
    wait_for_slip = State()
    topup_pid = State()
    topup_zone = State()
    check_order_id = State()
    ticket_msg = State()
    ticket_diamond = State()
    ticket_money = State()

class AdminState(StatesGroup):
    add_game_code = State()
    edit_pack_price = State()
    set_profit = State()
    edit_start_text = State()
    edit_start_media = State()
    bc_msg = State()
    bal_uid = State()
    bal_amt = State()
    rem_bal_uid = State()
    rem_bal_amt = State()
    set_topup_key = State()
    set_aba_key = State()
    set_aba_merchant = State()
    set_maintenance_text = State()
    add_adm_uid = State()
    static_qr_img = State()
    reply_ticket_uid = State()
    set_custom_emoji = State()
    clone_token = State()
    clone_admin_id = State()

# =====================================================================
# [ KEYBOARDS ជាមួយ STYLE COLOR ពេញលេញ ]
# =====================================================================
def main_menu(uid):
    is_admin = is_user_admin(uid)
    kb = [
        [
            RBtn("គណនី", style="primary", icon_custom_emoji_id=get_btn_emoji("btn_account", "5458585579866307689")),
            RBtn("បព្ចូាលលុយ", style="success", icon_custom_emoji_id=get_btn_emoji("btn_deposit", "6001434068435079689"))
        ],
        [
            RBtn("ថប់អាប់ហ្គេម", style=None, icon_custom_emoji_id=get_btn_emoji("btn_topup", "5427168083074628963")),
            RBtn("ការបព្ជាទិញ", style=None, icon_custom_emoji_id=get_btn_emoji("btn_orders", "5884479287171485878"))
        ],
        [
            RBtn("សំបុត្រ", style=None, icon_custom_emoji_id=get_btn_emoji("btn_ticket", "5418010521309815154")),
            RBtn("កំពូលអ្នកទិញ", style=None, icon_custom_emoji_id=get_btn_emoji("btn_top_buyers", "6194737030165959506"))
        ]
    ]
    if is_admin:
        kb.append([
            RBtn("ADMIN PANEL", style=None, icon_custom_emoji_id=get_btn_emoji("btn_admin_panel", "5895592588064328942"))
        ])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def orders_menu():
    kb = [
        [
            RBtn("All", style="primary", icon_custom_emoji_id=get_btn_emoji("btn_ord_all", "6154222749691679144")),
            RBtn("Pending", style="primary", icon_custom_emoji_id=get_btn_emoji("btn_ord_pending", "5386367538735104399"))
        ],
        [
            RBtn("Completed", style="success", icon_custom_emoji_id=get_btn_emoji("btn_ord_completed", "6023773095284707791")),
            RBtn("Failed", style="danger", icon_custom_emoji_id=get_btn_emoji("btn_ord_failed", "6176808917549453468"))
        ],
        [
            RBtn("Canceled", style="danger", icon_custom_emoji_id=get_btn_emoji("btn_ord_canceled", "6176808917549453468")),
            RBtn("Search Ordes", style="primary", icon_custom_emoji_id=get_btn_emoji("btn_ord_search", "5445023138297447592"))
        ],
        [
            RBtn("ប្រវត្តិការបព្ចូាលលុយ", style="success", icon_custom_emoji_id=get_btn_emoji("btn_ord_dep_hist", "6023773095284707791")),
            RBtn("ត្រលប់", style="danger", icon_custom_emoji_id=get_btn_emoji("btn_ord_back", "6071034593287345457"))
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def ticket_menu():
    kb = [
        [RBtn("ធ្ញើសារទៅ Owner", style="primary", icon_custom_emoji_id=get_btn_emoji("btn_tk_owner", "5335054400513649848"))],
        [RBtn("Diamon អត់ដំណើការ", style="danger", icon_custom_emoji_id=get_btn_emoji("btn_tk_diamond", "6176808917549453468"))],
        [RBtn("ដាក់លុយអត់ចូល", style="danger", icon_custom_emoji_id=get_btn_emoji("btn_tk_money", "6176808917549453468"))],
        [RBtn("Back To Menu", style="primary", icon_custom_emoji_id=get_btn_emoji("btn_tk_back", "5253997076169115797"))]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_pagination_kb(items, page, prefix, back_cb, items_per_page=8):
    total_pages = max(1, (len(items) + items_per_page - 1) // items_per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * items_per_page
    end = start + items_per_page
    page_items = items[start:end]

    kb = []
    for item in page_items:
        if len(item) == 4:
            price = calc_price(item[3])
            pkg_emoji = item[2] if item[2] else get_btn_emoji("btn_default_pack", "5427168083074628963")
            kb.append([
                IBtn(f"{item[1]} - ${price:.2f}", f"{prefix}_{item[0]}", style=None, icon_custom_emoji_id=pkg_emoji)
            ])
        else:
            game_emoji = item[2] if item[2] else "6131808852972144634"
            kb.append([
                IBtn(item[1], f"{prefix}_{item[0]}", style=None, icon_custom_emoji_id=game_emoji)
            ])

    prev_cb = f"page_{prefix}_{page-1}" if page > 0 else "noop_prev"
    next_cb = f"page_{prefix}_{page+1}" if (page + 1) < total_pages else "noop_next"
    nav_row = [
        IBtn("⬅️", prev_cb, style=None),
        IBtn(f"{page + 1}/{total_pages}", "noop_page", style=None),
        IBtn("➡️", next_cb, style=None)
    ]
    kb.append(nav_row)

    if back_cb:
        kb.append([
            IBtn("ត្រលប់", back_cb, style=None, icon_custom_emoji_id=get_btn_emoji("btn_inline_back", "5253997076169115797"))
        ])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def admin_menu_kb():
    kb = [
        [
            IBtn("Add Game", "adm_add_game", style=None, icon_custom_emoji_id="6131808852972144634"),
            IBtn("Edit Price", "adm_edit_price", style=None, icon_custom_emoji_id="5458382591121964689")
        ],
        [
            IBtn("ដាក់ប្រាក់ចំណេញ (%)", "adm_set_profit", style=None, icon_custom_emoji_id="5397916757333654639"),
            IBtn("Delete Game", "adm_del_game", style=None, icon_custom_emoji_id="5258130763148172425")
        ],
        [
            IBtn("Start and How to buy", "adm_start_settings", style=None, icon_custom_emoji_id="5258331647358540449"),
            IBtn("គ្រប់គ្រងទូទៅ", "adm_general_menu", style=None, icon_custom_emoji_id="5444869180899752137")
        ],
        [
            IBtn("Payment ABA", "adm_payment_aba", style=None, icon_custom_emoji_id="6138932923815960721"),
            IBtn("គ្រុបគ្រង ( អេតមីន )", "adm_admin", style=None, icon_custom_emoji_id="5895592588064328942")
        ],
        [
            IBtn("🎨 Custom Emoji", "adm_custom_emoji", style=None)
        ]
    ]
    if not _ctx_is_clone.get():
        kb[-1].append(IBtn("Clone", "adm_clone_menu", style=None, icon_custom_emoji_id="5445163772706582819"))
    return InlineKeyboardMarkup(inline_keyboard=kb)

# =====================================================================
# [ START & គណនី ]
# =====================================================================
@dp.message(Command("cancel"))
async def cancel_handler(msg: Message, state: FSMContext):
    cur_state = await state.get_state()
    if cur_state:
        await state.clear()
        await msg.answer("បានបោះបង់ប្រតិបត្តិការ!", reply_markup=main_menu(msg.from_user.id))

@dp.message(CommandStart())
async def start_cmd(msg: Message, state: FSMContext):
    await state.clear()
    uid = msg.from_user.id

    if check_maintenance(uid):
        mtn_text = get_setting("maintenance_text") or "ប្រព័ន្ធកំពុងស្ថិតក្នុងការជួសជុល និងថែទាំបណ្ដោះអាសន្ន។ សូមអភ័យទោសចំពោះការរំខាន។"
        return await msg.answer(mtn_text)

    db_query("INSERT OR IGNORE INTO users (id, name) VALUES (?, ?)", (uid, msg.from_user.full_name))

    custom_start = get_setting("start_text")
    if custom_start:
        text = custom_start.replace("{name}", msg.from_user.first_name or "").replace("{full_name}", msg.from_user.full_name or "")
    else:
        text = (f"{pemoji('5458904472598095631', '👋')} សួរស្ដីបង {msg.from_user.full_name} !\n\n"
                f"{pemoji('6073244216522186277', '🤖')} សូមស្វារគមន៍បងមកកាន់ប្រព័ន្វ Topup Game ដោយស្វ័យប្រវត្តិ\n"
                f"{pemoji('6071226041454564573', '👇')} សូមបងចុចបូតុងខាងក្រោមបានណា {pemoji('5231102735817918643', '🎮')}")

    media_id = get_setting("start_media_id")
    media_type = get_setting("start_media_type")

    if media_id:
        try:
            if media_type == "photo":
                return await msg.answer_photo(media_id, caption=text, reply_markup=main_menu(uid))
            elif media_type == "video":
                return await msg.answer_video(media_id, caption=text, reply_markup=main_menu(uid))
            elif media_type == "animation":
                return await msg.answer_animation(media_id, caption=text, reply_markup=main_menu(uid))
        except Exception as e:
            logging.error(f"Error sending start media: {e}")

    await msg.answer(text, reply_markup=main_menu(uid))

@dp.message(F.text == "គណនី")
async def acc_info(msg: Message):
    if check_maintenance(msg.from_user.id):
        return await msg.answer(get_setting("maintenance_text"))

    u = db_query("SELECT balance, total_orders FROM users WHERE id=?", (msg.from_user.id,), fetch=True)
    bal = u[0] if u else 0.0
    orders = u[1] if u else 0
    text = (f"{pemoji('5458585579866307689', '👤')} ព័ត៍មានគណនីរបស់អ្នក\n━━━━━━━━━━━━━━━━━━━━\n"
            f"{pemoji('5458585579866307689', '👤')} ឈ្មោះ : {msg.from_user.full_name}\n"
            f"{pemoji('5841276284155467413', '🆔')} លេខសម្គាល់ : <code>{msg.from_user.id}</code>\n"
            f"{pemoji('6001434068435079689', '💰')} សមតុល្យ : ${bal:.2f}\n"
            f"{pemoji('5884479287171485878', '🛒')} ការបព្ជាទិញ : {orders} ដង")
    await msg.answer(text)

# =====================================================================
# [ ការបញ្ជាទិញ (Orders) ]
# =====================================================================
@dp.message(F.text == "ការបព្ជាទិញ")
async def orders_menu_show(msg: Message, state: FSMContext):
    if check_maintenance(msg.from_user.id):
        return await msg.answer(get_setting("maintenance_text"))

    await state.clear()
    text = f"{pemoji('5884479287171485878', '🛒')} ការបញ្ជាទិញ\n\nសូមជ្រើសរើសប្រភេទ:"
    await msg.answer(text, reply_markup=orders_menu())

@dp.message(F.text.in_({"All", "Pending", "Completed", "Failed", "Canceled"}))
async def show_orders_status(msg: Message):
    if check_maintenance(msg.from_user.id):
        return await msg.answer(get_setting("maintenance_text"))

    uid = msg.from_user.id
    status_map = {
        "All": None,
        "Pending": "PENDING",
        "Completed": "SUCCESS",
        "Failed": "FAILED",
        "Canceled": "CANCELED"
    }
    st = status_map.get(msg.text)
    if st:
        orders = db_query("SELECT game, pack, price, status, date, ref_id FROM orders WHERE user_id=? AND status=? ORDER BY id DESC LIMIT 10", (uid, st), fetchall=True)
    else:
        orders = db_query("SELECT game, pack, price, status, date, ref_id FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 10", (uid,), fetchall=True)

    if not orders:
        return await msg.answer(f"មិនមានទិន្នន័យការបញ្ជាទិញប្រភេទ {msg.text} ទេ!")

    text = f"{pemoji('5884479287171485878', '🛒')} ប្រវត្តិការបញ្ជាទិញ {msg.text} (10 ចុងក្រោយ) របស់អ្នក៖\n\n"
    for o in orders:
        text += f"Game: {o[0]}\nPack: {o[1]}\nតម្លៃ: ${o[2]:.2f}\nស្ថានភាព: {o[3]}\nថ្ងៃទី: {o[4]}\nលេខប័ណ្ណ: <code>{o[5]}</code>\n━━━━━━━━━━━━━━━━━━━━\n"
    await msg.answer(text)

@dp.message(F.text == "Search Ordes")
async def search_orders_start(msg: Message, state: FSMContext):
    if check_maintenance(msg.from_user.id):
        return await msg.answer(get_setting("maintenance_text"))

    await msg.answer(f"{pemoji('5445023138297447592', '🔍')} សូមវាយលេខប័ណ្ណបញ្ជាទិញ (Order Code / Reference) របស់អ្នកដើម្បីស្វែងរក៖")
    await state.set_state(FlowState.check_order_id)

@dp.message(FlowState.check_order_id)
async def process_search_order(msg: Message, state: FSMContext):
    ref = msg.text.strip()
    o = db_query("SELECT game, pack, price, status, date, ref_id FROM orders WHERE ref_id=? AND user_id=?", (ref, msg.from_user.id), fetch=True)
    if not o:
        api_order = await api_topup_get_order(ref)
        if api_order and "order_code" in api_order:
            text = (f"{pemoji('6023773095284707791', '✅')} រកឃើញការបញ្ជាទិញក្នុង API៖\n\n"
                    f"Game: {api_order.get('game')}\nPack: {api_order.get('package')}\nតម្លៃ: ${api_order.get('price', 0):.2f}\n"
                    f"ស្ថានភាព: {api_order.get('status')}\nលេខប័ណ្ណ: <code>{api_order.get('order_code')}</code>")
            return await msg.answer(text)
        await msg.answer("រកមិនឃើញការបញ្ជាទិញនេះទេ! សូមពិនិត្យលេខប័ណ្ណឡើងវិញ។")
    else:
        text = (f"{pemoji('6023773095284707791', '✅')} រកឃើញការបញ្ជាទិញ៖\n\n"
                f"Game: {o[0]}\nPack: {o[1]}\nតម្លៃ: ${o[2]:.2f}\n"
                f"ស្ថានភាព: {o[3]}\nថ្ងៃទី: {o[4]}\nលេខប័ណ្ណ: <code>{o[5]}</code>")
        await msg.answer(text)
    await state.clear()

@dp.message(F.text == "ប្រវត្តិការបព្ចូាលលុយ")
async def show_deposit_history(msg: Message):
    if check_maintenance(msg.from_user.id):
        return await msg.answer(get_setting("maintenance_text"))

    deps = db_query("SELECT amount, status, ref_id FROM deposits WHERE user_id=? ORDER BY id DESC LIMIT 10", (msg.from_user.id,), fetchall=True)
    if not deps:
        return await msg.answer("មិនមានប្រវត្តិបញ្ចូលលុយទេ!")

    text = f"{pemoji('6001434068435079689', '💰')} ប្រវត្តិបញ្ចូលលុយ (10 ចុងក្រោយ) របស់អ្នក៖\n\n"
    for d in deps:
        text += f"ចំនួន: ${d[0]:.2f} | ស្ថានភាព: {d[1]}\nលេខសម្គាល់: <code>{d[2]}</code>\n━━━━━━━━━━━━━━━━━━━━\n"
    await msg.answer(text)

# =====================================================================
# [ សំបុត្រ (Tickets) ]
# =====================================================================
@dp.message(F.text == "សំបុត្រ")
async def ticket_menu_show(msg: Message):
    if check_maintenance(msg.from_user.id):
        return await msg.answer(get_setting("maintenance_text"))

    text = (f"═════════════════════\n"
            f"{pemoji('5418010521309815154', '🎫')} <b>សំបុត្រ</b>\n"
            f"═════════════════════\n\n"
            f"ជ្រើស ticket type:")
    await msg.answer(text, reply_markup=ticket_menu())

@dp.message(F.text == "Back To Menu")
@dp.message(F.text == "ត្រលប់")
async def back_to_main_menu(msg: Message, state: FSMContext):
    await start_cmd(msg, state)

@dp.message(F.text == "ធ្ញើសារទៅ Owner")
async def ticket_msg_owner(msg: Message, state: FSMContext):
    if check_maintenance(msg.from_user.id):
        return await msg.answer(get_setting("maintenance_text"))

    await msg.answer("សូមវាយបញ្ចូលសារដែលអ្នកចង់ផ្ញើទៅកាន់ Admin៖", reply_markup=ReplyKeyboardRemove())
    await state.set_state(FlowState.ticket_msg)

@dp.message(FlowState.ticket_msg)
async def ticket_msg_send(msg: Message, state: FSMContext, bot: Bot):
    user_info = f"សារពី User: {msg.from_user.full_name} (ID: <code>{msg.from_user.id}</code>)\n\nអត្ថបទ: {msg.text}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[IBtn("ឆ្លើយតប / Reply", f"reply_tk_{msg.from_user.id}", style=None)]])
    await bot.send_message(get_admin_id(), user_info, reply_markup=kb)
    await msg.answer("សាររបស់អ្នកត្រូវបានផ្ញើទៅកាន់ Admin រួចរាល់។", reply_markup=ticket_menu())
    await state.clear()

@dp.message(F.text == "Diamon អត់ដំណើការ")
async def ticket_diamond_err(msg: Message, state: FSMContext):
    if check_maintenance(msg.from_user.id):
        return await msg.answer(get_setting("maintenance_text"))

    await msg.answer("សូមវាយបញ្ចូលលេខ Orders របស់អ្នកដែលទិញហើយមិនចូល៖", reply_markup=ReplyKeyboardRemove())
    await state.set_state(FlowState.ticket_diamond)

@dp.message(FlowState.ticket_diamond)
async def ticket_diamond_send(msg: Message, state: FSMContext, bot: Bot):
    user_info = f"រាយការណ៍ Diamond មិនចូល!\nUser: {msg.from_user.full_name} (ID: <code>{msg.from_user.id}</code>)\nលេខ Order: <code>{msg.text}</code>"
    kb = InlineKeyboardMarkup(inline_keyboard=[[IBtn("ឆ្លើយតប / Reply", f"reply_tk_{msg.from_user.id}", style=None)]])
    await bot.send_message(get_admin_id(), user_info, reply_markup=kb)
    await msg.answer("របាយការណ៍របស់អ្នកត្រូវបានផ្ញើទៅ Admin។ យើងនឹងត្រួតពិនិត្យឆាប់ៗ។", reply_markup=ticket_menu())
    await state.clear()

@dp.message(F.text == "ដាក់លុយអត់ចូល")
async def ticket_money_err(msg: Message, state: FSMContext):
    if check_maintenance(msg.from_user.id):
        return await msg.answer(get_setting("maintenance_text"))

    await msg.answer("សូមវាយបញ្ចូលលេខ Payment ID / Transaction ID ដែលដាក់លុយមិនចូល៖", reply_markup=ReplyKeyboardRemove())
    await state.set_state(FlowState.ticket_money)

@dp.message(FlowState.ticket_money)
async def ticket_money_send(msg: Message, state: FSMContext, bot: Bot):
    user_info = f"រាយការណ៍ដាក់លុយមិនចូល!\nUser: {msg.from_user.full_name} (ID: <code>{msg.from_user.id}</code>)\nPayment Ref: <code>{msg.text}</code>"
    kb = InlineKeyboardMarkup(inline_keyboard=[[IBtn("ឆ្លើយតប / Reply", f"reply_tk_{msg.from_user.id}", style=None)]])
    await bot.send_message(get_admin_id(), user_info, reply_markup=kb)
    await msg.answer("របាយការណ៍របស់អ្នកត្រូវបានផ្ញើទៅ Admin។ យើងនឹងត្រួតពិនិត្យឆាប់ៗ។", reply_markup=ticket_menu())
    await state.clear()

@dp.callback_query(F.data.startswith("reply_tk_"))
async def admin_reply_ticket_cb(call: CallbackQuery, state: FSMContext):
    uid = int(call.data.split("_")[2])
    await state.update_data(reply_ticket_uid=uid)
    await call.message.answer(f"សូមវាយសារដើម្បីឆ្លើយតបទៅកាន់ User ID <code>{uid}</code>៖")
    await state.set_state(AdminState.reply_ticket_uid)

@dp.message(AdminState.reply_ticket_uid)
async def admin_send_ticket_reply(msg: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    uid = data['reply_ticket_uid']
    try:
        reply_text = f"សារឆ្លើយតបពី Admin៖\n\n{msg.text}"
        await bot.send_message(uid, reply_text)
        await msg.answer("បានផ្ញើសារឆ្លើយតបទៅកាន់ User រួចរាល់។")
    except Exception as e:
        await msg.answer("បរាជ័យក្នុងការផ្ញើសារឆ្លើយតប! User ប្រហែលជាបានបិទ Bot។")
    await state.clear()

# =====================================================================
# [ កំពូលអ្នកទិញ ]
# =====================================================================
@dp.message(F.text == "កំពូលអ្នកទិញ")
async def top_buyers(msg: Message):
    if check_maintenance(msg.from_user.id):
        return await msg.answer(get_setting("maintenance_text"))

    users = db_query("SELECT id, total_spent, total_orders, last_order_date FROM users WHERE total_orders > 0 ORDER BY total_spent DESC LIMIT 10", fetchall=True)
    if not users:
        text = f"{pemoji('6194737030165959506', '🏆')} មិនទាន់មាន អថិតិជនណាមួយបាន Topup ហ្គេមនៅឡើយតេ សូម Topup ហ្គេមជាមុនសិនទើបអាចជាប់ Top"
        return await msg.answer(text)

    text = f"{pemoji('6194737030165959506', '🏆')} <b>Top កំពូលអ្នកទិញចុងក្រោយ 10 នាក់</b>\n\n"
    for i, u in enumerate(users, 1):
        uid_str = str(u[0])
        hidden_id = "·" * 16 + uid_str[-2:] if len(uid_str) >= 2 else "·" * 16 + uid_str
        date_str = u[3] if u[3] else "មិនមានទិន្នន័យ"
        text += (f"{i} . {pemoji('5841276284155467413', '🆔')} {hidden_id}\n"
                 f"{pemoji('5278467510604160626', '💵')} សរុប : ${u[1]:.2f}\n"
                 f"{pemoji('5231200819986047254', '🎮')} ចំនួនទិញ : {u[2]}\n"
                 f"{pemoji('5283187967425268516', '📅')} ចូល : {date_str}\n\n")
    await msg.answer(text)

# =====================================================================
# [ ការបញ្ចូលលុយ (DEPOSIT & ABA AUTO PAYMENT) ]
# =====================================================================
@dp.message(F.text == "បព្ចូាលលុយ")
async def dep_start(msg: Message, state: FSMContext):
    if check_maintenance(msg.from_user.id):
        return await msg.answer(get_setting("maintenance_text"))

    text = (f"═════════════════════\n"
            f"{pemoji('6001434068435079689', '💰')} <b>បព្ចូាលុយ</b>\n"
            f"═════════════════════\n"
            f"សូមបញ្ចូលចំនួន USD (អប្បបរមា $0.50):\n\nឧទាហរណ៍: 1, 2, 5 ឬ 10.50")
    await msg.answer(text)
    await state.set_state(FlowState.dep_amount)

@dp.message(FlowState.dep_amount)
async def dep_choose_method(msg: Message, state: FSMContext, bot: Bot):
    try:
        amount = float(msg.text.strip().replace("$", ""))
        if amount < 0.50:
            return await msg.answer("ចំនួនទឹកប្រាក់អប្បបរមាគឺ $0.50!")
    except:
        return await msg.answer("ចំនួនមិនត្រឹមត្រូវ! សូមបញ្ចូលជាលេខ (ឧ. 5)")

    uid = msg.from_user.id
    username = msg.from_user.username or msg.from_user.first_name or str(uid)

    aba_enabled = get_setting("aba_pay_enabled") == "1"
    aba_api_key = get_setting("aba_api_key")
    aba_merchant_id = get_setting("aba_merchant_id")
    static_qr_enabled = get_setting("static_qr_enabled") == "1"
    static_qr = get_setting("static_qr_file_id")

    khqr_btn = IBtn("បង់ប្រាក់ KHQR", f"use_static_qr_{amount:.2f}", style="primary", icon_custom_emoji_id=get_btn_emoji("btn_khqr_pay", "6314519407443845610"))

    dep_key = (_ctx_db_path.get(), uid)
    if dep_key in _active_deposits and aba_enabled and aba_api_key and aba_merchant_id:
        await state.clear()
        return await msg.answer("មាន QR កំពុងរង់ចាំបង់។ សូមបញ្ចប់ ឬរង់ចាំផុតពេល មុនបង្កើតថ្មី។")

    if not aba_enabled or not aba_api_key or not aba_merchant_id:
        if static_qr_enabled and static_qr:
            kb = InlineKeyboardMarkup(inline_keyboard=[[khqr_btn]])
            await msg.answer(f"{pemoji('6001434068435079689', '💰')} ចំនួនទឹកប្រាក់ត្រូវបញ្ចូល៖ <b>${amount:.2f}</b>\nសូមចុចប៊ូតុងខាងក្រោមដើម្បីបង់ប្រាក់៖", reply_markup=kb)
            return await state.clear()
        return await msg.answer("ប្រព័ន្ធបង់ប្រាក់មិនទាន់ត្រូវបានបើក ឬកំណត់ដោយ Admin ទេ។ សូមទាក់ទង Admin។")

    load_msg = await msg.answer("កំពុងទាញយក ABA KHQR ពីប្រព័ន្ធ សូមរង់ចាំបន្តិច...")

    data = await api_aba_generate_qr(amount, username)
    if not data:
        try: await bot.delete_message(msg.chat.id, load_msg.message_id)
        except: pass
        if static_qr_enabled and static_qr:
            kb = InlineKeyboardMarkup(inline_keyboard=[[khqr_btn]])
            await msg.answer(f"បង្កើត ABA Auto QR បរាជ័យ! អ្នកអាចបង់ប្រាក់តាមប៊ូតុង KHQR ខាងក្រោម៖", reply_markup=kb)
            return await state.clear()
        return await msg.answer("បង្កើត QR បរាជ័យ! សូមព្យាយាមម្ដងទៀតនៅពេលក្រោយ ឬទាក់ទង Admin។")

    payment_id, qr_image, pay_url = extract_aba_fields(data)
    if not payment_id:
        try: await bot.delete_message(msg.chat.id, load_msg.message_id)
        except: pass
        return await msg.answer("មិនទទួលបាន Payment ID ពីធនាគារ ABA ទេ។")

    caption = (f"{pemoji('6314519407443845610', '🏦')} <b>ABA KHQR AUTO PAYMENT</b>\n\n"
               f"{pemoji('6001434068435079689', '💰')} ប្រាក់ត្រូវបង់ : <b>${amount:.2f}</b>\n"
               f"{pemoji('5794182096603847292', '💳')} សូម Scan QR តាមរយៈ ABA Mobile ឬគ្រប់ធនាគារក្នុងប្រទេសកម្ពុជា\n"
               f"{pemoji('5794303034292968945', '⏳')} បន្ទាប់ពីបង់ប្រាក់រួច ប្រព័ន្ធនឹងឆែក និងបញ្ចូលសមតុល្យចូលគណនីស្វ័យប្រវត្តិ!\n"
               f"Ref: <code>{payment_id}</code>\n"
               f"ផុតកំណត់: 5 នាទី")

    try: await bot.delete_message(msg.chat.id, load_msg.message_id)
    except: pass

    extra_kb = InlineKeyboardMarkup(inline_keyboard=[[khqr_btn]]) if (static_qr_enabled and static_qr) else None

    sent_msg = None
    if qr_image and str(qr_image).startswith("http"):
        try:
            sent_msg = await msg.answer_photo(qr_image, caption=caption, reply_markup=extra_kb)
        except:
            sent_msg = await msg.answer(caption, reply_markup=extra_kb)
    else:
        sent_msg = await msg.answer(caption, reply_markup=extra_kb)

    _active_deposits[dep_key] = {"payment_id": str(payment_id), "amount": amount, "started": time.time()}
    db_query("INSERT INTO deposits (user_id, amount, ref_id, status) VALUES (?, ?, ?, 'PENDING')", (uid, amount, str(payment_id)))
    asyncio.create_task(poll_aba_payment_loop(bot, uid, msg.chat.id, amount, str(payment_id), sent_msg.message_id, db_path=_ctx_db_path.get(), admin_id=get_admin_id()))
    await state.clear()

@dp.callback_query(F.data.startswith("use_static_qr_"))
async def use_static_qr_cb(call: CallbackQuery, state: FSMContext):
    if get_setting("static_qr_enabled") != "1":
        return await call.answer("មុខងារ QR នេះត្រូវបានបិទជាបណ្ដោះអាសន្ន!", show_alert=True)
    static_qr = get_setting("static_qr_file_id")
    if not static_qr:
        return await call.answer("មិនទាន់មានរូបភាព QR ទេ!", show_alert=True)
    amount = float(call.data.split("_")[3])
    await state.update_data(dep_amt=amount)
    await state.set_state(FlowState.wait_for_slip)
    await call.message.answer_photo(static_qr, caption=f"សូមផ្ញើប្រាក់ចំនួន <b>${amount:.2f}</b> ទៅកាន់ QR ខាងលើ រួចថតវិក្កយប័ត្រផ្ញើមកទីនេះ។")
    await call.answer()

@dp.message(FlowState.wait_for_slip, F.photo | F.document)
async def receive_slip(msg: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    amount = data.get('dep_amt', 0)
    uid = msg.from_user.id

    await msg.answer("វិក្កយប័ត្ររបស់អ្នកត្រូវបានបញ្ជូនទៅកាន់អេតមីនដើម្បីពិនិត្យ! សូមរង់ចាំបន្តិច...")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn("យល់ព្រម (Approve)", f"cfmslip_{uid}_{amount}", style=None), IBtn("បដិសេធ (Reject)", f"rejslip_{uid}", style=None)]
    ])
    admin_text = f"ការស្នើសុំដាក់ប្រាក់ដោយដៃ!\nUser ID: <code>{uid}</code>\nឈ្មោះ: {msg.from_user.full_name}\nចំនួន: ${amount:.2f}"
    await msg.copy_to(chat_id=get_admin_id(), caption=admin_text, reply_markup=kb)
    await state.clear()

@dp.callback_query(F.data.startswith("cfmslip_"))
async def admin_cfm_slip(call: CallbackQuery, bot: Bot):
    parts = call.data.split("_")
    uid = int(parts[1])
    amount = float(parts[2])

    db_query("UPDATE users SET balance=balance+? WHERE id=?", (amount, uid))
    u = db_query("SELECT balance FROM users WHERE id=?", (uid,), fetch=True)

    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.reply(f"បានយល់ព្រមទឹកប្រាក់ ${amount:.2f} ទៅកាន់ ID: {uid}")

    text = f"វិក្កយប័ត្ររបស់អ្នកត្រូវបានបញ្ជាក់!\nទទួលបាន : ${amount:.2f}\nសមតុល្យសរុប : ${u[0]:.2f}\nសូមអរគុណបង"
    try: await bot.send_message(uid, text)
    except: pass

@dp.callback_query(F.data.startswith("rejslip_"))
async def admin_rej_slip(call: CallbackQuery, bot: Bot):
    uid = int(call.data.split("_")[1])
    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.reply(f"បានបដិសេធវិក្កយប័ត្រពី ID: {uid}")
    try: await bot.send_message(uid, "វិក្កយប័ត្ររបស់អ្នកត្រូវបានបដិសេធដោយ Admin!")
    except: pass

# =====================================================================
# [ ការបញ្ជាទិញហ្គេម (TOPUP) ]
# =====================================================================
@dp.message(F.text == "ថប់អាប់ហ្គេម")
async def topup_game(msg: Message):
    if check_maintenance(msg.from_user.id):
        return await msg.answer(get_setting("maintenance_text"))

    await show_games(msg, page=0)

async def show_games(target, page=0, is_edit=False):
    games = db_query("SELECT id, name, emoji_id FROM games", fetchall=True)
    if not games:
        text = "មិនទាន់មានហ្គេមទេ! សូមប្រាប់ Admin ឲ្យ Add Game។"
        if is_edit: return await target.edit_text(text)
        else: return await target.answer(text)

    kb = get_pagination_kb(games, page, "gm", "cancel_to_start")
    text = f"{pemoji('5427168083074628963', '🎮')} <b>Game Service</b>\n🔽 សូមជ្រើសរើសហ្គេមខាងក្រោម៖"

    if is_edit: await target.edit_text(text, reply_markup=kb)
    else: await target.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "noop_page")
async def noop_page_cb(call: CallbackQuery):
    await call.answer()

@dp.callback_query(F.data == "noop_prev")
async def noop_prev_cb(call: CallbackQuery):
    await call.answer("អ្នកកំពុងស្ថិតនៅទំព័រដំបូងហើយ!")

@dp.callback_query(F.data == "noop_next")
async def noop_next_cb(call: CallbackQuery):
    await call.answer("អ្នកកំពុងស្ថិតនៅទំព័រចុងក្រោយហើយ!")

@dp.callback_query(F.data.startswith("page_gm_"))
async def page_games(call: CallbackQuery):
    page = int(call.data.split("_")[2])
    await show_games(call.message, page, is_edit=True)

@dp.callback_query(F.data == "cancel_to_start")
async def back_to_start_cmd(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.delete()
    text = f"{pemoji('6071226041454564573', '👇')} លោកអ្នកបានត្រលប់មកកាន់ម៉ឺនុយដើមវិញហើយ។ សូមបងចុចបូតុងខាងក្រោមបានណា {pemoji('5231102735817918643', '🎮')}"
    await call.message.answer(text, reply_markup=main_menu(call.from_user.id))

@dp.callback_query(F.data.startswith("gm_"))
async def topup_pack(call: CallbackQuery, state: FSMContext):
    gid = int(call.data.split("_")[1])
    await show_packs(call.message, gid, page=0, is_edit=True)

async def show_packs(msg, gid, page=0, is_edit=False):
    g = db_query("SELECT name, emoji_id FROM games WHERE id=?", (gid,), fetch=True)
    packs = db_query("SELECT id, name, emoji_id, price FROM packages WHERE game_id=?", (gid,), fetchall=True)
    if not packs:
        text = "មិនទាន់មានកញ្ចប់លុយទេ!"
        if is_edit: return await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[IBtn("ត្រលប់", "back_to_games", style=None, icon_custom_emoji_id=get_btn_emoji("btn_inline_back", "5253997076169115797"))]]))
        return await msg.answer(text)

    kb = get_pagination_kb(packs, page, f"pk_{gid}", "back_to_games")
    g_emoji = pemoji(g[1] if g and g[1] else "6131808852972144634", "🎮")
    text = f"{g_emoji} <b>{g[0]}</b>\n🔽 សូមជ្រើសរើស Packege ដែលចង់ទិញ៖"

    if is_edit: await msg.edit_text(text, reply_markup=kb)
    else: await msg.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "back_to_games")
async def back_to_games(call: CallbackQuery):
    await show_games(call.message, page=0, is_edit=True)

@dp.callback_query(F.data.startswith("page_pk_"))
async def page_packs(call: CallbackQuery):
    parts = call.data.split("_")
    gid = int(parts[2])
    page = int(parts[3])
    await show_packs(call.message, gid, page, is_edit=True)

@dp.callback_query(F.data.startswith("pk_"))
async def topup_id(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    gid = int(parts[1])
    pack_id = int(parts[2])
    await state.update_data(pack_id=pack_id, gid=gid)

    game_info = db_query("SELECT name, id_label, server_label FROM games WHERE id=?", (gid,), fetch=True)
    id_lbl = (game_info[1] if game_info and game_info[1] else "Player ID")

    kb = InlineKeyboardMarkup(inline_keyboard=[[IBtn("ត្រលប់", f"back_to_packs_{gid}", style="danger", icon_custom_emoji_id=get_btn_emoji("btn_inline_back", "5253997076169115797"))]])
    await call.message.edit_text(f"{pemoji('6154233835002271015', '🆔')} សូមបងវាយបញ្ចូល <b>{id_lbl}</b> របស់បងមកទីនេះ៖", reply_markup=kb)
    await state.set_state(FlowState.topup_pid)

@dp.callback_query(F.data.startswith("back_to_packs_"))
async def back_to_packs_cb(call: CallbackQuery, state: FSMContext):
    await state.clear()
    gid = int(call.data.split("_")[3])
    await show_packs(call.message, gid, page=0, is_edit=True)

@dp.message(FlowState.topup_pid)
async def topup_zone(msg: Message, state: FSMContext, bot: Bot):
    text_in = msg.text.strip()
    # ពិនិត្យមើលបើជាប៊ូតុង Menu ផ្ដាច់ State ភ្លាម
    menu_cmds = {"គណនី", "បព្ចូាលលុយ", "ថប់អាប់ហ្គេម", "ការបព្ជាទិញ", "សំបុត្រ", "កំពូលអ្នកទិញ", "ADMIN PANEL", "ត្រលប់", "/start", "/cancel"}
    if text_in in menu_cmds:
        await state.clear()
        return await start_cmd(msg, state)

    await state.update_data(player_id=text_in)
    data = await state.get_data()
    gid = data['gid']
    game_info = db_query("SELECT name, server_label, game_code FROM games WHERE id=?", (gid,), fetch=True)
    srv_lbl = game_info[1] if game_info and game_info[1] else None
    g_slug = str(game_info[2] or "").lower() if game_info else ""
    g_name = str(game_info[0] or "").lower() if game_info else ""

    # Free Fire ឬ PUBG មិនត្រូវការ Zone ID ទេ -> រំលងភ្លាមៗ
    if "free" in g_slug or "free" in g_name or "pubg" in g_slug or "pubg" in g_name:
        await state.update_data(zone_id="")
        return await process_topup_confirm(msg, state, bot, None)

    # បើហ្គេមជា Mobile Legends ឬមាន server_label ជាក់លាក់
    if srv_lbl or "mobile" in g_slug or "mlbb" in g_slug or "mobile" in g_name:
        label = srv_lbl or "Zone ID"
        kb = InlineKeyboardMarkup(inline_keyboard=[[IBtn("ត្រលប់", f"back_to_packs_{gid}", style="danger", icon_custom_emoji_id=get_btn_emoji("btn_inline_back", "5253997076169115797"))]])
        await msg.answer(f"{pemoji('5841276284155467413', '🆔')} សូមវាយបញ្ចូល <b>{label}</b> របស់អ្នក (ឧ. 1234)៖", reply_markup=kb)
        await state.set_state(FlowState.topup_zone)
    else:
        # បើហ្គេមផ្សេងៗ មិនត្រូវការ Zone
        await state.update_data(zone_id="")
        await process_topup_confirm(msg, state, bot, None)

@dp.message(FlowState.topup_zone)
async def topup_confirm_zone(msg: Message, state: FSMContext, bot: Bot):
    text_in = msg.text.strip()
    menu_cmds = {"គណនី", "បព្ចូាលលុយ", "ថប់អាប់ហ្គេម", "ការបព្ជាទិញ", "សំបុត្រ", "កំពូលអ្នកទិញ", "ADMIN PANEL", "ត្រលប់", "/start", "/cancel"}
    if text_in in menu_cmds:
        await state.clear()
        return await start_cmd(msg, state)

    await state.update_data(zone_id=text_in)
    await process_topup_confirm(msg, state, bot, None)

async def process_topup_confirm(msg: Message, state: FSMContext, bot: Bot, edit_msg_id=None):
    scan_text = f"{pemoji('5445023138297447592', '🔍')} សូមរង់ចាំបន្តិច ប្រព័ន្ធកំពុងស្គេនរកមើលឈ្មោះគណនីពី Player ID របស់បង....."

    scan_msg_id = None
    if edit_msg_id:
        try:
            await bot.edit_message_text(scan_text, chat_id=msg.chat.id, message_id=edit_msg_id)
            scan_msg_id = edit_msg_id
        except: pass

    if not scan_msg_id:
        scan_msg = await msg.answer(scan_text)
        scan_msg_id = scan_msg.message_id

    data = await state.get_data()
    pid = str(data.get('player_id') or '').strip()
    zid = str(data.get('zone_id') or '').strip()

    # សម្អាត Zone ID ប្រសិនបើមានពាក្យ Menu ជ្រៀតចូល
    if zid.lower() in ["admin panel", "none", "null", "គណនី", "ថប់អាប់ហ្គេម", "ត្រលប់"]:
        zid = ""

    pack = db_query(
        "SELECT p.name, p.price, g.name, g.game_code, p.product_code, p.id "
        "FROM packages p JOIN games g ON p.game_id=g.id WHERE p.id=?",
        (data.get('pack_id'),), fetch=True
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn("វាយបញ្ចូល ID ម្ដងទៀត", f"pk_{data.get('gid')}_{data.get('pack_id')}", style="primary")],
        [IBtn("ត្រលប់", f"back_to_packs_{data.get('gid')}", style="danger", icon_custom_emoji_id=get_btn_emoji("btn_inline_back", "5253997076169115797"))]
    ])

    if not pack:
        try: await bot.delete_message(msg.chat.id, scan_msg_id)
        except: pass
        return await bot.send_message(msg.chat.id, "រកកញ្ចប់ហ្គេមមិនឃើញទេ។ សូមត្រឡប់ទៅជ្រើសរើសកញ្ចប់ម្ដងទៀត។", reply_markup=kb)

    slug = str(pack[3] or '').strip()
    check_res = await api_topup_check_player(slug, pid, zid)

    is_valid = bool(check_res and check_res.get("result") == "valid")
    uname = check_res.get("nickname") if is_valid else None

    try: await bot.delete_message(msg.chat.id, scan_msg_id)
    except: pass

    final_price = calc_price(pack[1])

    zone_info = f" (Zone: <code>{zid}</code>)" if zid else ""
    if uname:
        name_display = f"<b>Name</b> : <b>{uname}</b>"
        note_display = ""
    else:
        name_display = f"<b>Name</b> : <i>(គណនីហ្គេម Player ID: <code>{pid}</code>)</i>"
        note_display = "\n⚠️ <i>ចំណាំ៖ សូមពិនិត្យមើល Player ID ឱ្យបានច្បាស់លាស់មុននឹងចុចយល់ព្រមទិញ។</i>\n"

    text = (f"{pemoji('5427168083074628963', '🎮')} <b>Game</b> : {pack[2]}\n"
            f"{pemoji('5841276284155467413', '🆔')} <b>Player ID</b> : <code>{pid}</code>{zone_info}\n"
            f"{pemoji('5458585579866307689', '👤')} {name_display}\n"
            f"{pemoji('5445023138297447592', '🔍')} <b>Packege</b> : {pack[0]}\n"
            f"{pemoji('6001434068435079689', '💰')} <b>តម្លៃ</b> : ${final_price:.2f}\n"
            f"{note_display}\n"
            f"បើបងយល់ព្រមសូមចុចប៊ូតុងខាងក្រោម៖")

    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            IBtn("យល់ព្រមទិញ", f"cfmbuy_{pack[5]}", style="success", icon_custom_emoji_id=get_btn_emoji("btn_confirm_buy", "6023773095284707791")),
            IBtn("មិនយល់ព្រមទិញ", f"back_to_packs_{data['gid']}", style="danger", icon_custom_emoji_id=get_btn_emoji("btn_cancel_buy", "5253997076169115797"))
        ],
        [
            IBtn("🔄 វាយបញ្ចូល ID ម្ដងទៀត", f"pk_{data.get('gid')}_{data.get('pack_id')}", style="primary", icon_custom_emoji_id=get_btn_emoji("btn_reenter_id", ""))
        ]
    ])
    await bot.send_message(msg.chat.id, text, reply_markup=confirm_kb)

@dp.callback_query(F.data.startswith("cfmbuy_"))
async def execute_buy(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    uid = call.from_user.id
    pack_id = int(call.data.split("_")[1])
    pack = db_query("SELECT p.name, p.price, g.name, p.product_code, g.game_code FROM packages p JOIN games g ON p.game_id=g.id WHERE p.id=?", (pack_id,), fetch=True)
    u = db_query("SELECT balance FROM users WHERE id=?", (uid,), fetch=True)

    final_price = calc_price(pack[1])

    if u[0] < final_price:
        return await call.answer("សមតុល្យមិនគ្រប់គ្រាន់ទេ! សូមបញ្ចូលលុយជាមុនសិន។", show_alert=True)

    await call.message.edit_text("កំពុងដំណើរការបញ្ជាទិញទៅកាន់ API សូមរង់ចាំបន្តិច...")

    ref = f"KT-ORD-{int(time.time())}"
    package_api_id = pack[3]
    res = await api_topup_create_order(package_api_id, data.get('player_id'), ref, data.get('zone_id', ''))

    order_st = str((res or {}).get("status", "")).lower()
    order_code = (res or {}).get("order_code") or ref

    if res and (order_st in ["processing", "completed", "success"] or (res or {}).get("order_code")):
        date_str = datetime.now().strftime("%Y-%m-%d")
        db_query("UPDATE users SET balance=balance-?, total_spent=total_spent+?, total_orders=total_orders+1, last_order_date=? WHERE id=?", (final_price, final_price, date_str, uid))
        db_query("INSERT INTO orders (user_id, game, pack, price, status, ref_id, date) VALUES (?, ?, ?, ?, ?, ?, ?)", (uid, pack[2], pack[0], final_price, "COMPLETED", order_code, date_str))

        text = (f"{pemoji('6023773095284707791', '✅')} <b>ការបញ្ជាទិញពេជ្រហ្គេមទទួលបានជោគជ័យ!</b>\n\n"
                f"Game: <b>{pack[2]}</b>\n"
                f"Pack: <b>{pack[0]}</b>\n"
                f"តម្លៃ: <b>${final_price:.2f}</b>\n"
                f"លេខប័ណ្ណ: <code>{order_code}</code>\n\n"
                f"ពេជ្រនឹងចូលទៅក្នុងអាខោនរបស់អ្នកដោយស្វ័យប្រវត្តិ។ សូមអរគុណ!")
        await call.message.edit_text(text)
    else:
        err_msg = (res or {}).get("message") or "API Error"
        date_str = datetime.now().strftime("%Y-%m-%d")
        db_query("INSERT INTO orders (user_id, game, pack, price, status, ref_id, date) VALUES (?, ?, ?, ?, ?, ?, ?)", (uid, pack[2], pack[0], final_price, "FAILED", ref, date_str))
        await call.message.edit_text(f"ការបញ្ជាទិញបរាជ័យ (Failed)៖ {err_msg}។ មិនមានការកាត់ប្រាក់ឡើយ។")

# =====================================================================
# [ ADMIN PANEL ]
# =====================================================================
@dp.message(F.text == "ADMIN PANEL")
async def admin_panel(msg: Message):
    if not is_user_admin(msg.from_user.id):
        return
    text = (f"{pemoji('5895592588064328942', '⚙️')} <b>ADMIN PANEL គ្រប់គ្រងប្រព័ន្ធ</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"សូមជ្រើសរើសមុខងារគ្រប់គ្រងខាងក្រោម៖")
    await msg.answer(text, reply_markup=admin_menu_kb())

@dp.callback_query(F.data == "back_admin")
async def back_adm_btn(call: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (f"{pemoji('5895592588064328942', '⚙️')} <b>ADMIN PANEL គ្រប់គ្រងប្រព័ន្ធ</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"សូមជ្រើសរើសមុខងារគ្រប់គ្រងខាងក្រោម៖")
    await call.message.edit_text(text, reply_markup=admin_menu_kb())

# --- 1. ADD GAME TO STORE ពី API ថ្មី (khmer-topup.com) ---
@dp.callback_query(F.data == "adm_add_game")
async def adm_add_game_cb(call: CallbackQuery, state: FSMContext):
    text = (f"{pemoji('6131808852972144634', '➕')} <b>ADD GAME TO STORE (khmer-topup.com)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"សូមបញ្ចូល Game Slug ដើម្បីទាញយកទំនិញពី API (ឬវាយពាក្យ <b>all</b> ដើម្បីទាញយកហ្គេមទាំងអស់)៖\n\n"
            f"ឧទាហរណ៍:\n"
            f"- mobile-legends\n"
            f"- freefire\n"
            f"- all\n\n"
            f"(ឬចុច /cancel ដើម្បីបោះបង់)")
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
        IBtn("ត្រលប់", "back_admin", icon_custom_emoji_id="5253997076169115797")
    ]]))
    await state.set_state(AdminState.add_game_code)

@dp.message(AdminState.add_game_code)
async def process_add_game_code(msg: Message, state: FSMContext, bot: Bot):
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear()
        return await msg.answer("បានបោះបង់!", reply_markup=main_menu(msg.from_user.id))

    input_slug = msg.text.strip().lower()
    load_msg = await msg.answer("កំពុងទាញយកទិន្នន័យពី khmer-topup.com សូមរង់ចាំបន្តិច...")

    api_data = await api_topup_get_games()
    games_list = (api_data or {}).get("games", [])

    if not games_list:
        try: await bot.delete_message(msg.chat.id, load_msg.message_id)
        except: pass
        return await msg.answer(f"មិនអាចទាញយកទិន្នន័យពី API បានទេ! សូមពិនិត្យមើល Topup Key ក្នុង Settings។")

    imported_games = 0
    imported_packs = 0

    target_games = games_list if input_slug in ["all", "ទាញយកទាំងអស់"] else [g for g in games_list if g.get("slug") == input_slug or g.get("slug") == input_slug.replace("_", "-")]

    if not target_games:
        try: await bot.delete_message(msg.chat.id, load_msg.message_id)
        except: pass
        avail_slugs = ", ".join([f"<code>{g.get('slug')}</code>" for g in games_list[:8]])
        return await msg.answer(f"រកមិនឃើញ Game Slug <code>{input_slug}</code> ទេ!\n\nហ្គេមដែលមានក្នុង API: {avail_slugs}\n\n(ឬវាយ <b>all</b> ដើម្បីទាញយកទាំងអស់)")

    for g in target_games:
        gname = g.get("name", "Unknown")
        gslug = g.get("slug", "")
        id_lbl = g.get("id_label", "User ID")
        srv_lbl = g.get("server_label")

        exist_game = db_query("SELECT id FROM games WHERE game_code=?", (gslug,), fetch=True)
        if exist_game:
            gid = exist_game[0]
            db_query("UPDATE games SET name=?, id_label=?, server_label=?, emoji_id=COALESCE(NULLIF(emoji_id, ''), ?) WHERE id=?", (gname, id_lbl, srv_lbl, "6131808852972144634", gid))
        else:
            gid = db_query("INSERT INTO games (name, game_code, emoji_id, id_label, server_label) VALUES (?, ?, ?, ?, ?)",
                            (gname, gslug, "6131808852972144634", id_lbl, srv_lbl))
        imported_games += 1

        for p in g.get("packages", []):
            p_api_id = str(p.get("package_id"))
            pname = p.get("name", "Diamond")
            price = float(p.get("price", 0.0))
            ptag = p.get("tag", "")

            exist_pkg = db_query("SELECT id FROM packages WHERE product_code=? AND game_id=?", (p_api_id, gid), fetch=True)
            if exist_pkg:
                db_query("UPDATE packages SET name=?, price=?, tag=?, emoji_id=COALESCE(NULLIF(emoji_id, ''), ?) WHERE id=?", (pname, price, ptag, "5427168083074628963", exist_pkg[0]))
            else:
                db_query("INSERT INTO packages (game_id, name, product_code, price, emoji_id, tag) VALUES (?, ?, ?, ?, ?, ?)",
                         (gid, pname, p_api_id, price, "5427168083074628963", ptag))
            imported_packs += 1

    try: await bot.delete_message(msg.chat.id, load_msg.message_id)
    except: pass

    added_game_ids = []
    for g in target_games:
        row = db_query("SELECT id, name FROM games WHERE game_code=?", (g.get("slug", ""),), fetch=True)
        if row:
            added_game_ids.append(row)
    emoji_kb = []
    for agid, agname in added_game_ids[:8]:
        emoji_kb.append([IBtn(f"🎨 ដាក់ Emoji: {agname}", f"ce_edit_game_{agid}", style=None)])
    emoji_kb.append([IBtn("🎨 Custom Emoji ទាំងអស់", "adm_custom_emoji", style=None)])
    emoji_kb.append([IBtn("⚙️ Admin Panel", "back_admin", style=None)])

    await msg.answer(
        f"{pemoji('6023773095284707791', '✅')} បានទាញយកហ្គេមចំនួន <b>{imported_games}</b> និងកញ្ចប់ចំនួន <b>{imported_packs}</b> ពី khmer-topup.com ដោយជោគជ័យ!\n\n👇 ចង់ដាក់ Emoji Premium ឱ្យហ្គេមដែលទើប Add សូមចុចខាងក្រោម៖",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=emoji_kb)
    )
    await state.clear()

# --- 2. EDIT PRICE (កែសម្រួលតម្លៃកញ្ចប់) ---
@dp.callback_query(F.data == "adm_edit_price")
async def adm_edit_price_cb(call: CallbackQuery):
    games = db_query("SELECT id, name FROM games", fetchall=True)
    if not games:
        return await call.answer("មិនទាន់មានហ្គេមទេ! សូម Add Game ជាមុនសិន។", show_alert=True)

    kb = []
    for g in games:
        kb.append([IBtn(g[1], f"edp_g_{g[0]}")])
    kb.append([IBtn("Back", "back_admin", icon_custom_emoji_id="5253997076169115797")])

    await call.message.edit_text(
        f"{pemoji('5458382591121964689', '📝')} <b>កែប្រែតម្លៃកញ្ចប់ហ្គេម (Edit Price)</b>\n━━━━━━━━━━━━━━━━━━━━\nសូមជ្រើសរើសហ្គេមដែលចង់កែប្រែតម្លៃ៖",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )

@dp.callback_query(F.data.startswith("edp_g_"))
async def adm_edit_price_packs(call: CallbackQuery):
    gid = int(call.data.split("_")[2])
    game = db_query("SELECT name FROM games WHERE id=?", (gid,), fetch=True)
    packs = db_query("SELECT id, name, price FROM packages WHERE game_id=?", (gid,), fetchall=True)

    if not packs:
        return await call.answer("ហ្គេមនេះមិនទាន់មានកញ្ចប់ទេ!", show_alert=True)

    kb = []
    for p in packs:
        kb.append([IBtn(f"{p[1]} - ${p[2]:.2f}", f"edp_p_{p[0]}")])
    kb.append([IBtn("ត្រលប់", "adm_edit_price", icon_custom_emoji_id="5253997076169115797")])

    await call.message.edit_text(
        f"{pemoji('5427168083074628963', '🎮')} <b>ហ្គេម៖ {game[0]}</b>\n━━━━━━━━━━━━━━━━━━━━\nសូមជ្រើសរើសកញ្ចប់ដែលចង់កែប្រែតម្លៃ៖",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )

@dp.callback_query(F.data.startswith("edp_p_"))
async def adm_edit_price_input(call: CallbackQuery, state: FSMContext):
    pid = int(call.data.split("_")[2])
    pkg = db_query("SELECT id, name, price, game_id FROM packages WHERE id=?", (pid,), fetch=True)
    if not pkg:
        return await call.answer("រកកញ្ចប់មិនឃើញ!", show_alert=True)

    await state.update_data(edp_pkg_id=pid, edp_game_id=pkg[3])
    text = (f"{pemoji('5458382591121964689', '📝')} <b>កែប្រែតម្លៃកញ្ចប់៖</b> {pkg[1]}\n"
            f"តម្លៃបច្ចុប្បន្ន៖ ${pkg[2]:.2f}\n\n"
            f"សូមបញ្ចូលតម្លៃថ្មីជាប្រាក់ USD (ឧទាហរណ៍: 0.50 ឬ 1.20)៖\n"
            f"(ឬចុច /cancel ដើម្បីបោះបង់)")
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
        IBtn("ត្រលប់", f"edp_g_{pkg[3]}", icon_custom_emoji_id="5253997076169115797")
    ]]))
    await state.set_state(AdminState.edit_pack_price)

@dp.message(AdminState.edit_pack_price)
async def adm_edit_price_save(msg: Message, state: FSMContext):
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear()
        return await msg.answer("បានបោះបង់!", reply_markup=main_menu(msg.from_user.id))

    try:
        new_price = float(msg.text.strip().replace("$", ""))
        if new_price < 0: raise ValueError
    except Exception:
        return await msg.answer("តម្លៃត្រូវតែជាលេខវិជ្ជមាន (ឧទាហរណ៍: 0.50)៖")

    data = await state.get_data()
    pid = data.get("edp_pkg_id")

    db_query("UPDATE packages SET price=? WHERE id=?", (new_price, pid))
    pkg = db_query("SELECT name FROM packages WHERE id=?", (pid,), fetch=True)
    pname = pkg[0] if pkg else "Package"

    await msg.answer(
        f"{pemoji('6023773095284707791', '✅')} បានកែប្រែតម្លៃកញ្ចប់ <b>{pname}</b> ទៅជា <b>${new_price:.2f}</b> ដោយជោគជ័យ!",
        reply_markup=admin_menu_kb()
    )
    await state.clear()

# --- 3. ដាក់ប្រាក់ចំណេញ (%) ---
@dp.callback_query(F.data == "adm_set_profit")
async def adm_set_profit_cb(call: CallbackQuery, state: FSMContext):
    cur_profit = get_setting("profit_margin") or "0"
    text = (f"{pemoji('5397916757333654639', '📈')} <b>ដាក់ប្រាក់ចំណេញ (%)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"ប្រាក់ចំណេញបច្ចុប្បន្ន៖ <b>+{cur_profit}%</b>\n\n"
            f"សូមបញ្ចូលភាគរយ (%) ដែលចង់បូកបន្ថែមលើតម្លៃដើមពី API:\n"
            f"(ឧទាហរណ៍: 5 សម្រាប់ 5%, 10 សម្រាប់ 10%)\n\n"
            f"(ឬចុច /cancel ដើម្បីបោះបង់)")
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
        IBtn("ត្រលប់", "back_admin", icon_custom_emoji_id="5253997076169115797")
    ]]))
    await state.set_state(AdminState.set_profit)

@dp.message(AdminState.set_profit)
async def adm_save_profit_msg(msg: Message, state: FSMContext):
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear()
        return await msg.answer("បានបោះបង់!", reply_markup=main_menu(msg.from_user.id))

    try:
        val = float(msg.text.strip().replace("%", ""))
        if val < 0: raise ValueError
        set_setting("profit_margin", str(val))
        await msg.answer(
            f"{pemoji('6023773095284707791', '✅')} បានកំណត់ប្រាក់ចំណេញបូកបន្ថែម <b>+{val:.2f}%</b> ដោយជោគជ័យ!",
            reply_markup=admin_menu_kb()
        )
        await state.clear()
    except Exception:
        await msg.answer("សូមបញ្ចូលជាលេខភាគរយត្រឹមត្រូវ (ឧទាហរណ៍: 5 ឬ 10.5)៖")

# --- 4. DELETE GAME (លុបទាំងហ្គេម និងកញ្ចប់) ---
@dp.callback_query(F.data == "adm_del_game")
@dp.callback_query(F.data.startswith("adm_del_game_p_"))
async def adm_del_game_cb(call: CallbackQuery):
    games = db_query("SELECT id, name FROM games ORDER BY id ASC", fetchall=True)
    if not games:
        return await call.answer("មិនមានហ្គេមសម្រាប់លុបទេ!", show_alert=True)

    page = 0
    if call.data.startswith("adm_del_game_p_"):
        page = int(call.data.split("_")[-1])

    per_page = 20
    total_pages = max(1, (len(games) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    page_games = games[page * per_page:(page + 1) * per_page]

    kb = [
        [
            IBtn("♻️ Reset Game ( Full )", "del_g_reset_full", style=None),
            IBtn("⚙️ Admin Panel", "back_admin", style=None)
        ]
    ]
    row = []
    for g in page_games:
        row.append(IBtn(f"🗑 {g[1]}", f"del_g_run_{g[0]}", style=None))
        if len(row) == 2:
            kb.append(row)
            row = []
    if row:
        kb.append(row)

    if total_pages > 1:
        prev_cb = f"adm_del_game_p_{page-1}" if page > 0 else "noop_prev"
        next_cb = f"adm_del_game_p_{page+1}" if (page + 1) < total_pages else "noop_next"
        kb.append([
            IBtn("⬅️", prev_cb, style=None),
            IBtn(f"{page + 1}/{total_pages}", "noop_page", style=None),
            IBtn("➡️", next_cb, style=None)
        ])

    await call.message.edit_text(
        f"{pemoji('5258130763148172425', '🗑')} <b>Delete Game</b> (សរុប {len(games)} ហ្គេម)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"ជ្រើសរើសហ្គេមដែលចង់លុប ឬចុច <b>♻️ Reset Game ( Full )</b> ដើម្បីលុបទាំងអស់៖",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )

@dp.callback_query(F.data.startswith("del_g_run_"))
async def adm_del_game_run(call: CallbackQuery):
    gid = int(call.data.split("_")[3])
    game = db_query("SELECT name FROM games WHERE id=?", (gid,), fetch=True)
    gname = game[0] if game else "Game"

    db_query("DELETE FROM packages WHERE game_id=?", (gid,))
    db_query("DELETE FROM games WHERE id=?", (gid,))

    await call.answer(f"បានលុបហ្គេម {gname} និងកញ្ចប់ទាំងអស់ជោគជ័យ!", show_alert=True)
    rem_games = db_query("SELECT id, name FROM games", fetchall=True)
    if not rem_games:
        return await call.message.edit_text(
            f"{pemoji('6023773095284707791', '✅')} បានលុបហ្គេមទាំងអស់រួចរាល់! មិនមានហ្គេមនៅសល់ទេ។",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[IBtn("⚙️ Admin Panel", "back_admin", style=None)]])
        )
    await adm_del_game_cb(call)

@dp.callback_query(F.data == "del_g_reset_full")
async def adm_del_game_reset_full_confirm(call: CallbackQuery):
    kb = [
        [
            IBtn("✅ បញ្ជាក់ Reset Game ( Full )", "del_g_reset_full_exec", style=None),
            IBtn("ត្រលប់", "adm_del_game", style=None, icon_custom_emoji_id="5253997076169115797")
        ],
        [
            IBtn("⚙️ Admin Panel", "back_admin", style=None)
        ]
    ]
    await call.message.edit_text(
        "⚠️ <b>បញ្ជាក់ការ Reset Game ( Full )</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "តើអ្នកពិតជាចង់លុបហ្គេម និងកញ្ចប់ទាំងអស់ចោលម្ដងទាំងអស់មែនទេ?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )

@dp.callback_query(F.data == "del_g_reset_full_exec")
async def adm_del_game_reset_full_exec(call: CallbackQuery):
    db_query("DELETE FROM packages")
    db_query("DELETE FROM games")
    await call.answer("បានលុបហ្គេម និងកញ្ចប់ទាំងអស់ដោយជោគជ័យ!", show_alert=True)
    await call.message.edit_text(
        f"{pemoji('6023773095284707791', '✅')} <b>បាន Reset Game ( Full ) រួចរាល់!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"ហ្គេម និងកញ្ចប់ទាំងអស់ត្រូវបានលុបចេញពីប្រព័ន្ធទាំងស្រុង។",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[IBtn("⚙️ Admin Panel", "back_admin", style=None)]])
    )

# --- 5. START AND HOW TO BUY ---
@dp.callback_query(F.data == "adm_start_settings")
async def adm_start_settings_cb(call: CallbackQuery):
    cur_start = get_setting("start_text") or (
        f"{pemoji('5458904472598095631', '👋')} សួរស្ដីបង {{full_name}} !\n\n"
        f"{pemoji('6073244216522186277', '🤖')} សូមស្វារគមន៍បងមកកាន់ប្រព័ន្វ Topup Game ដោយស្វ័យប្រវត្តិ\n"
        f"{pemoji('6071226041454564573', '👇')} សូមបងចុចបូតុងខាងក្រោមបានណា {pemoji('5231102735817918643', '🎮')}"
    )

    media_id = get_setting("start_media_id")
    media_type = get_setting("start_media_type")
    media_status = f"មាន ({media_type})" if media_id else "គ្មាន"

    text = (f"{pemoji('5258331647358540449', '✏️')} <b>Start and How to buy</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Start បច្ចុប្បន្ន៖\n{cur_start}\n\n"
            f"Media បច្ចុប្បន្ន៖ {media_status}\n━━━━━━━━━━━━━━━━━━━━\n"
            f"សូមជ្រើសរើសមុខងារកែប្រែខាងក្រោម៖")

    kb = [
        [
            IBtn("Edit Start", "adm_edit_start"),
            IBtn("Reset start", "adm_reset_start")
        ],
        [
            IBtn("Edit Video / photo / GIFs", "adm_edit_media"),
            IBtn("Reset Vdeo / GIF / Photo", "adm_reset_media")
        ],
        [
            IBtn("Back", "back_admin", icon_custom_emoji_id="5253997076169115797")
        ]
    ]
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "adm_edit_start")
async def adm_edit_start_cb(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(
        "សូមវាយបញ្ចូលអត្ថបទសម្រាប់ /start ថ្មី (អាចប្រើ {name} ឬ {full_name} សម្រាប់ឈ្មោះអ្នកប្រើប្រាស់)៖\n\n(ឬចុច /cancel ដើម្បីបោះបង់)"
    )
    await state.set_state(AdminState.edit_start_text)

@dp.message(AdminState.edit_start_text)
async def adm_save_start_text(msg: Message, state: FSMContext):
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear()
        return await msg.answer("បានបោះបង់!", reply_markup=main_menu(msg.from_user.id))

    set_setting("start_text", msg.text)
    await msg.answer("បានកែប្រែអត្ថបទ Start ថ្មីដោយជោគជ័យ!", reply_markup=admin_menu_kb())
    await state.clear()

@dp.callback_query(F.data == "adm_reset_start")
async def adm_reset_start_cb(call: CallbackQuery):
    set_setting("start_text", "")
    await call.answer("បាន Reset អត្ថបទ Start ទៅជាដើមវិញហើយ!", show_alert=True)
    await adm_start_settings_cb(call)

@dp.callback_query(F.data == "adm_edit_media")
async def adm_edit_media_cb(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(
        "សូមផ្ញើ រូបភាព (Photo), វីដេអូ (Video) ឬ GIFs (Animation) មកទីនេះដើម្បីដាក់ពីលើអក្សរ Start៖\n\n(ឬចុច /cancel ដើម្បីបោះបង់)"
    )
    await state.set_state(AdminState.edit_start_media)

@dp.message(AdminState.edit_start_media, F.photo | F.video | F.animation | F.document)
async def adm_save_start_media(msg: Message, state: FSMContext):
    media_id = ""
    media_type = ""
    if msg.photo:
        media_id = msg.photo[-1].file_id
        media_type = "photo"
    elif msg.video:
        media_id = msg.video.file_id
        media_type = "video"
    elif msg.animation:
        media_id = msg.animation.file_id
        media_type = "animation"
    elif msg.document:
        media_id = msg.document.file_id
        media_type = "animation"

    set_setting("start_media_id", media_id)
    set_setting("start_media_type", media_type)

    await msg.answer(f"បានកំណត់ Media ({media_type}) សម្រាប់ Start ដោយជោគជ័យ!", reply_markup=admin_menu_kb())
    await state.clear()

@dp.callback_query(F.data == "adm_reset_media")
async def adm_reset_media_cb(call: CallbackQuery):
    set_setting("start_media_id", "")
    set_setting("start_media_type", "")
    await call.answer("បានដក Media ចេញពី Start រួចរាល់!", show_alert=True)
    await adm_start_settings_cb(call)

# --- 6. គ្រប់គ្រងទូទៅ (GENERAL SYSTEM SETTINGS) ---
@dp.callback_query(F.data == "adm_general_menu")
async def adm_general_menu_cb(call: CallbackQuery):
    is_mtn = get_setting("maintenance_mode") == "1"
    mtn_btn_text = "បើក ជួលជុល" if is_mtn else "បិទ ជួលជុល"
    mtn_style = "success" if is_mtn else "danger"

    kb = [
        [
            IBtn("Broadcart", "adm_broadcast"),
            IBtn("ស្ថានភាព API game", "adm_api_status")
        ],
        [
            IBtn("ដាក់ប្រាក់ User", "adm_add_bal"),
            IBtn("ដកប្រាក់ User", "adm_rem_bal")
        ],
        [
            IBtn("ប្រាក់ចំណូល", "adm_income"),
            IBtn(mtn_btn_text, "adm_toggle_mtn")
        ],
        [
            IBtn("📦 Order", "adm_orders_list")
        ],
        [
            IBtn("Back", "back_admin", icon_custom_emoji_id="5253997076169115797")
        ]
    ]

    text = (f"{pemoji('5444869180899752137', '⚙️')} <b>គ្រប់គ្រងទូទៅ (General Settings)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"សូមជ្រើសរើសមុខងារខាងក្រោម៖")
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# Broadcast
@dp.callback_query(F.data == "adm_broadcast")
async def adm_bcast_cb(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(
        "<b>Broadcast ផ្ញើសារទៅកាន់ User ទាំងអស់</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "សូមផ្ញើសារដែលអ្នកចង់ Broadcast (អាចជា អត្ថបទ, រូបភាព, វីដេអូ, GIFs, Sticker, ឬ សំឡេង/Voice)៖\n\n"
        "(ឬចុច /cancel ដើម្បីបោះបង់)"
    )
    await state.set_state(AdminState.bc_msg)

@dp.message(AdminState.bc_msg)
async def adm_exec_bcast(msg: Message, state: FSMContext, bot: Bot):
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear()
        return await msg.answer("បានបោះបង់!", reply_markup=main_menu(msg.from_user.id))

    users = db_query("SELECT id FROM users", fetchall=True)
    status_msg = await msg.answer("កំពុងផ្ញើសារទៅកាន់ Users ទាំងអស់...")
    ok = 0
    fail = 0
    for u in users:
        try:
            await msg.copy_to(chat_id=u[0])
            ok += 1
            await asyncio.sleep(0.04)
        except Exception:
            fail += 1

    try: await bot.delete_message(msg.chat.id, status_msg.message_id)
    except Exception: pass

    await msg.answer(
        f"{pemoji('6023773095284707791', '✅')} បានផ្ញើសារជោគជ័យទៅកាន់ User ចំនួន <b>{ok}</b> នាក់! (បរាជ័យ: {fail})",
        reply_markup=admin_menu_kb()
    )
    await state.clear()

# ស្ថានភាព API Topup & ប្ដូរ Topup Key
@dp.callback_query(F.data == "adm_api_status")
async def adm_api_status_cb(call: CallbackQuery):
    topup_api = get_setting("topup_api") or "https://khmer-topup.com/api/v1"
    topup_key = get_setting("topup_key") or "kt_92a981610e7ba1ebb35447447057406ab8ce1536"
    prof = await api_topup_me()

    if prof and "username" in prof:
        uname = prof.get("username", "Unknown")
        bal = float(prof.get("balance", 0.0))
        role = prof.get("role", "reseller")
        curr = prof.get("currency", "USD")
        text = (f"{pemoji('5335054400513649848', '🔑')} <b>ស្ថានភាព TOPUP API (khmer-topup.com)</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"API URL: <b>{topup_api}</b>\n"
                f"Reseller: <b>{uname}</b>\n"
                f"សមតុល្យ API: <b>${bal:.2f} {curr}</b>\n"
                f"Role: <b>{role}</b>\n"
                f"Topup Key: <code>{topup_key}</code>")
    else:
        text = (f"<b>មិនអាចភ្ជាប់ទៅកាន់ TOPUP API បានទេ!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"API URL: {topup_api}\n"
                f"Topup Key: <code>{topup_key}</code>\n\n"
                f"សូមពិនិត្យមើល Topup Key ឡើងវិញ។")

    kb = [
        [IBtn("ប្ដូរ Topup API Key", "adm_change_topup_key")],
        [IBtn("ត្រលប់", "adm_general_menu", icon_custom_emoji_id="5253997076169115797")]
    ]
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "adm_change_topup_key")
async def adm_change_topup_key_cb(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("សូមវាយបញ្ចូល API Key ថ្មីរបស់អ្នក (khmer-topup.com)៖\n\n(ឬចុច /cancel ដើម្បីបោះបង់)")
    await state.set_state(AdminState.set_topup_key)

@dp.message(AdminState.set_topup_key)
async def adm_save_topup_key(msg: Message, state: FSMContext):
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear()
        return await msg.answer("បានបោះបង់!", reply_markup=main_menu(msg.from_user.id))

    new_key = msg.text.strip()
    set_setting("topup_key", new_key)
    await msg.answer(f"{pemoji('6023773095284707791', '✅')} បានកំណត់ Topup API Key ថ្មីដោយជោគជ័យ!\n<code>{new_key}</code>", reply_markup=admin_menu_kb())
    await state.clear()

# ដាក់ប្រាក់ / ដកប្រាក់ User
@dp.callback_query(F.data == "adm_add_bal")
async def adm_add_bal_cb(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("សូមបញ្ចូល ID របស់ User ដែលចង់បញ្ចូលលុយឲ្យ៖\n\n(ឬចុច /cancel ដើម្បីបោះបង់)")
    await state.set_state(AdminState.bal_uid)

@dp.message(AdminState.bal_uid)
async def adm_add_bal_uid(msg: Message, state: FSMContext):
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear()
        return await msg.answer("បានបោះបង់!", reply_markup=main_menu(msg.from_user.id))

    try: uid = int(msg.text.strip())
    except Exception: return await msg.answer("ID ត្រូវតែជាលេខ៖")

    u = db_query("SELECT id, name, balance FROM users WHERE id=?", (uid,), fetch=True)
    if not u:
        return await msg.answer(f"រកមិនឃើញ User ID {uid} នៅក្នុងប្រព័ន្ធទេ!")

    await state.update_data(b_uid=uid)
    await msg.answer(f"User: {u[1]} (ID: <code>{uid}</code>)\nសមតុល្យបច្ចុប្បន្ន: ${u[2]:.2f}\n\nសូមវាយចំនួនលុយដែលចង់បញ្ចូល (USD) ឧ. 10 ឬ 5.50 ៖")
    await state.set_state(AdminState.bal_amt)

@dp.message(AdminState.bal_amt)
async def adm_add_bal_amt(msg: Message, state: FSMContext, bot: Bot):
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear()
        return await msg.answer("បានបោះបង់!", reply_markup=main_menu(msg.from_user.id))

    try:
        amt = float(msg.text.strip().replace("$", ""))
        if amt <= 0: raise ValueError
    except Exception:
        return await msg.answer("ចំនួនលុយត្រូវតែជាលេខវិជ្ជមាន (ឧ. 5 ឬ 10.5)៖")

    data = await state.get_data()
    uid = data['b_uid']
    db_query("UPDATE users SET balance=balance+? WHERE id=?", (amt, uid))
    u = db_query("SELECT balance FROM users WHERE id=?", (uid,), fetch=True)

    try:
        await bot.send_message(uid, f"{pemoji('6023773095284707791', '✅')} គណនីរបស់អ្នកត្រូវបានបញ្ចូលទឹកប្រាក់ចំនួន <b>+${amt:.2f}</b> ដោយ Admin!\nសមតុល្យបច្ចុប្បន្ន៖ ${u[0]:.2f}")
    except Exception: pass

    await msg.answer(
        f"{pemoji('6023773095284707791', '✅')} បានបញ្ចូលប្រាក់ចំនួន <b>${amt:.2f}</b> ឲ្យ User ID <code>{uid}</code> ជោគជ័យ!\nសមតុល្យថ្មី៖ ${u[0]:.2f}",
        reply_markup=admin_menu_kb()
    )
    await state.clear()

@dp.callback_query(F.data == "adm_rem_bal")
async def adm_rem_bal_cb(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("សូមបញ្ចូល ID របស់ User ដែលចង់ដកលុយចេញ៖\n\n(ឬចុច /cancel ដើម្បីបោះបង់)")
    await state.set_state(AdminState.rem_bal_uid)

@dp.message(AdminState.rem_bal_uid)
async def adm_rem_bal_uid_input(msg: Message, state: FSMContext):
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear()
        return await msg.answer("បានបោះបង់!", reply_markup=main_menu(msg.from_user.id))

    try: uid = int(msg.text.strip())
    except Exception: return await msg.answer("ID ត្រូវតែជាលេខ៖")

    u = db_query("SELECT id, name, balance FROM users WHERE id=?", (uid,), fetch=True)
    if not u:
        return await msg.answer(f"រកមិនឃើញ User ID {uid} នៅក្នុងប្រព័ន្ធទេ!")

    await state.update_data(rem_uid=uid)
    await msg.answer(f"User: {u[1]} (ID: <code>{uid}</code>)\nសមតុល្យបច្ចុប្បន្ន: ${u[2]:.2f}\n\nសូមវាយចំនួនលុយដែលចង់ដកចេញ (USD) ឧ. 5 ឬ 2.50 ៖")
    await state.set_state(AdminState.rem_bal_amt)

@dp.message(AdminState.rem_bal_amt)
async def adm_rem_bal_amt_input(msg: Message, state: FSMContext, bot: Bot):
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear()
        return await msg.answer("បានបោះបង់!", reply_markup=main_menu(msg.from_user.id))

    try:
        amt = float(msg.text.strip().replace("$", ""))
        if amt <= 0: raise ValueError
    except Exception:
        return await msg.answer("ចំនួនលុយត្រូវតែជាលេខវិជ្ជមាន (ឧ. 5 ឬ 2.5)៖")

    data = await state.get_data()
    uid = data['rem_uid']
    u = db_query("SELECT balance FROM users WHERE id=?", (uid,), fetch=True)
    if u[0] < amt:
        return await msg.answer(f"សមតុល្យ User មានតែ ${u[0]:.2f} ប៉ុណ្ណោះ មិនអាចដក ${amt:.2f} បានទេ!")

    db_query("UPDATE users SET balance=balance-? WHERE id=?", (amt, uid))
    new_u = db_query("SELECT balance FROM users WHERE id=?", (uid,), fetch=True)

    try:
        await bot.send_message(uid, f"គណនីរបស់អ្នកត្រូវបានកាត់ដកប្រាក់ចំនួន <b>-${amt:.2f}</b> ដោយ Admin!\nសមតុល្យបច្ចុប្បន្ន៖ ${new_u[0]:.2f}")
    except Exception: pass

    await msg.answer(
        f"{pemoji('6023773095284707791', '✅')} បានដកប្រាក់ចំនួន <b>${amt:.2f}</b> ពី User ID <code>{uid}</code> ជោគជ័យ!\nសមតុល្យថ្មី៖ ${new_u[0]:.2f}",
        reply_markup=admin_menu_kb()
    )
    await state.clear()

# ប្រាក់ចំណូល (Income)
@dp.callback_query(F.data == "adm_income")
async def adm_income_cb(call: CallbackQuery):
    inc_dep = db_query("SELECT SUM(amount) FROM deposits WHERE status='PAID'", fetch=True)
    total_dep = inc_dep[0] if inc_dep and inc_dep[0] else 0.0

    inc_ord = db_query("SELECT SUM(price), COUNT(*) FROM orders WHERE status='COMPLETED'", fetch=True)
    total_ord = inc_ord[0] if inc_ord and inc_ord[0] else 0.0
    ord_cnt = inc_ord[1] if inc_ord and inc_ord[1] else 0

    u_cnt = db_query("SELECT COUNT(*) FROM users", fetch=True)[0]

    text = (f"<b>ស្ថិតិ និងប្រាក់ចំណូលសរុប</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"ប្រាក់បញ្ចូលសរុប (Deposits): <b>${total_dep:.2f}</b>\n"
            f"ការទិញពេជ្រសរុប (Orders): <b>${total_ord:.2f}</b>\n"
            f"ចំនួនការបញ្ជាទិញជោគជ័យ: <b>{ord_cnt} ដង</b>\n"
            f"អតិថិជនសរុប: <b>{u_cnt} នាក់</b>")
    await call.answer(f"ប្រាក់បញ្ចូល: ${total_dep:.2f} | ការទិញ: ${total_ord:.2f}", show_alert=True)

# បិទ/បើក ជួសជុល (Maintenance Mode)
@dp.callback_query(F.data == "adm_toggle_mtn")
async def adm_toggle_mtn_cb(call: CallbackQuery, state: FSMContext):
    cur = get_setting("maintenance_mode")
    if cur == "1":
        set_setting("maintenance_mode", "0")
        await call.answer("បានបើកដំណើរការ Bot ឡើងវិញជោគជ័យ! User អាចប្រើប្រាស់ Bot ធម្មតា។", show_alert=True)
        await adm_general_menu_cb(call)
    else:
        await call.message.edit_text(
            "<b>បិទដំណើរការ Bot ដើម្បីជួសជុល (Maintenance Mode)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "សូមវាយបញ្ចូលសារជូនដំណឹងប្រាប់ User ពេលពួកគេចុច /start ៖\n\n"
            "(ឬវាយពាក្យ 'skip' ដើម្បីប្រើសារលំនាំដើម)\n"
            "(ឬចុច /cancel ដើម្បីបោះបង់)"
        )
        await state.set_state(AdminState.set_maintenance_text)

@dp.message(AdminState.set_maintenance_text)
async def adm_save_mtn_text(msg: Message, state: FSMContext):
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear()
        return await msg.answer("បានបោះបង់!", reply_markup=main_menu(msg.from_user.id))

    if msg.text.strip().lower() == 'skip':
        mtn_text = "ប្រព័ន្ធកំពុងស្ថិតក្នុងការជួសជុល និងថែទាំបណ្ដោះអាសន្ន។ សូមអភ័យទោសចំពោះការរំខាន។"
    else:
        mtn_text = msg.text.strip()

    set_setting("maintenance_mode", "1")
    set_setting("maintenance_text", mtn_text)

    await msg.answer(
        f"{pemoji('6023773095284707791', '✅')} បានបិទដំណើរការ Bot ដើម្បីជួសជុលជោគជ័យ!\nUser ធម្មតានឹងមិនអាចប្រើប្រាស់ Bot បានឡើយរហូតដល់អ្នកបើកឡើងវិញ។",
        reply_markup=admin_menu_kb()
    )
    await state.clear()

# --- 7. PAYMENT ABA (Khmer System API) ---
@dp.callback_query(F.data == "adm_payment_aba")
async def adm_payment_aba_cb(call: CallbackQuery):
    aba_enabled = get_setting("aba_pay_enabled") == "1"
    static_qr_enabled = get_setting("static_qr_enabled") == "1"
    status_text = "កំពុងបើក (Active)" if aba_enabled else "កំពុងបិទ (Disabled)"
    qr_status_text = "កំពុងបើក (Active)" if static_qr_enabled else "កំពុងបិទ (Disabled)"
    api_key = get_setting("aba_api_key") or "មិនទាន់កំណត់"
    merchant_id = get_setting("aba_merchant_id") or "មិនទាន់កំណត់"

    text = (f"{pemoji('6138932923815960721', '💳')} <b>ការកំណត់ ABA AUTO PAYMENT (Khmer System)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"API Base: <code>https://khmer-system.com</code>\n"
            f"ស្ថានភាព ABA: <b>{status_text}</b>\n"
            f"ស្ថានភាព KHQR ផ្ទាល់ដៃ: <b>{qr_status_text}</b>\n"
            f"Merchant ID: <code>{merchant_id}</code>\n"
            f"API Key: <code>{api_key}</code>\n\n"
            f"សូមជ្រើសរើសមុខងារកែប្រែខាងក្រោម៖")

    tgl_btn_text = "បិទ ABA PAY" if aba_enabled else "បើក ABA PAY"
    qr_btn_text = "បិទ QR" if static_qr_enabled else "បើក QR"

    kb = [
        [
            IBtn("កំណត់ ABA API Key", "set_aba_key_btn", style=None),
            IBtn("កំណត់ Merchant ID", "set_aba_merchant_btn", style=None)
        ],
        [
            IBtn(tgl_btn_text, "toggle_aba_from_payment", style=None),
            IBtn("កំណត់ QR ផ្ទាល់ដៃ", "adm_set_qr_img", style=None)
        ],
        [
            IBtn(qr_btn_text, "toggle_static_qr", style=None)
        ],
        [
            IBtn("Back", "back_admin", style=None, icon_custom_emoji_id="5253997076169115797")
        ]
    ]

    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "set_aba_key_btn")
async def set_aba_key_cb(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("សូមវាយបញ្ចូល ABA API Key (Khmer System) របស់អ្នក៖\n\n(ឬចុច /cancel ដើម្បីបោះបង់)")
    await state.set_state(AdminState.set_aba_key)

@dp.message(AdminState.set_aba_key)
async def save_aba_key_msg(msg: Message, state: FSMContext):
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear()
        return await msg.answer("បានបោះបង់!", reply_markup=main_menu(msg.from_user.id))

    set_setting("aba_api_key", msg.text.strip())
    await msg.answer(f"{pemoji('6023773095284707791', '✅')} បានរក្សាទុក ABA API Key ជោគជ័យ!", reply_markup=admin_menu_kb())
    await state.clear()

@dp.callback_query(F.data == "set_aba_merchant_btn")
async def set_aba_merchant_cb(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("សូមវាយបញ្ចូល ABA Merchant ID (Khmer System) របស់អ្នក៖\n\n(ឬចុច /cancel ដើម្បីបោះបង់)")
    await state.set_state(AdminState.set_aba_merchant)

@dp.message(AdminState.set_aba_merchant)
async def save_aba_merchant_msg(msg: Message, state: FSMContext):
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear()
        return await msg.answer("បានបោះបង់!", reply_markup=main_menu(msg.from_user.id))

    set_setting("aba_merchant_id", msg.text.strip())
    await msg.answer(f"{pemoji('6023773095284707791', '✅')} បានរក្សាទុក ABA Merchant ID ជោគជ័យ!", reply_markup=admin_menu_kb())
    await state.clear()

@dp.callback_query(F.data == "toggle_aba_from_payment")
async def toggle_aba_from_payment_cb(call: CallbackQuery):
    cur = get_setting("aba_pay_enabled")
    new_status = "0" if cur == "1" else "1"
    set_setting("aba_pay_enabled", new_status)
    msg_text = "បានបើក ABA PAY រួចរាល់!" if new_status == "1" else "បានបិទ ABA PAY រួចរាល់!"
    await call.answer(msg_text, show_alert=True)
    await adm_payment_aba_cb(call)

# --- 8. គ្រុបគ្រង ( អេតមីន ) ---
@dp.callback_query(F.data == "adm_admin")
async def adm_admin(call: CallbackQuery):
    kb = [
        [
            IBtn("អេត អេតមីន", "add_adm", icon_custom_emoji_id="5895592588064328942"), 
            IBtn("ដក អេតមីន", "del_adm", icon_custom_emoji_id="6176808917549453468")
        ],
        [
            IBtn("Back", "back_admin", icon_custom_emoji_id="5253997076169115797")
        ]
    ]
    await call.message.edit_text(f"{pemoji('5895592588064328942', '👑')} <b>គ្រុបគ្រង អេតមីន:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "adm_set_qr_img")
async def adm_set_qr_img(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("សូមផ្ញើរូបភាព KHQR សម្រាប់អតិថិជនផ្ទេរលុយផ្ទាល់ដៃ៖\n\n(ឬចុច /cancel ដើម្បីបោះបង់)")
    await state.set_state(AdminState.static_qr_img)

@dp.message(AdminState.static_qr_img, F.photo)
async def adm_set_qr_img_sv(msg: Message, state: FSMContext):
    set_setting("static_qr_file_id", msg.photo[-1].file_id)
    await msg.answer(f"{pemoji('6023773095284707791', '✅')} បានកំណត់រូបភាព KHQR រួចរាល់!", reply_markup=admin_menu_kb())
    await state.clear()

@dp.callback_query(F.data == "add_adm")
async def add_adm(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("សូមវាយបញ្ជូល ID របស់អ្នកដែលចង់តម្លើងជា Admin:")
    await state.set_state(AdminState.add_adm_uid)

@dp.message(AdminState.add_adm_uid)
async def execute_add_adm(msg: Message, state: FSMContext, bot: Bot):
    try:
        new_adm_id = int(msg.text.strip())
        db_query("UPDATE users SET is_admin=1 WHERE id=?", (new_adm_id,))
        await msg.answer(f"{pemoji('6023773095284707791', '✅')} ជោគជ័យ! អ្នកប្រើប្រាស់នេះបានក្លាយជា Admin ហើយ។")
        try:
            text_notify = "អបអរសាទរ! អ្នកត្រូវបានតែងតាំងជា Admin។ នេះគឺជាម៉ឺនុយថ្មីរបស់អ្នកដែលមានប៊ូតុង ADMIN PANEL៖"
            await bot.send_message(chat_id=new_adm_id, text=text_notify, reply_markup=main_menu(new_adm_id))
        except: pass
    except:
        await msg.answer("ID ត្រូវតែជាលេខ!")
    await state.clear()

@dp.callback_query(F.data == "del_adm")
async def del_adm(call: CallbackQuery):
    adms = db_query("SELECT id, name FROM users WHERE is_admin=1", fetchall=True)
    kb = [[IBtn(f"ដក {a[1]}", f"rmadm_{a[0]}")] for a in adms]
    kb.append([IBtn("Back", "adm_admin", icon_custom_emoji_id="5253997076169115797")])
    await call.message.edit_text("ជ្រើសរើស Admin ដើម្បីដកសិទ្ធិ៖", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("rmadm_"))
async def execute_del_adm(call: CallbackQuery):
    uid = int(call.data.split("_")[1])
    if uid == get_admin_id(): return await call.answer("មិនអាចដកសិទ្ធិម្ចាស់ដើមបានទេ!", show_alert=True)
    db_query("UPDATE users SET is_admin=0 WHERE id=?", (uid,))
    await call.answer("បានដកសិទ្ធិ Admin ជោគជ័យ!", show_alert=True)
    await del_adm(call)

# =====================================================================

# --- 9. បិទ/បើក Static QR ---
@dp.callback_query(F.data == "toggle_static_qr")
async def toggle_static_qr_cb(call: CallbackQuery):
    cur = get_setting("static_qr_enabled")
    new_status = "0" if cur == "1" else "1"
    set_setting("static_qr_enabled", new_status)
    msg_text = "បានបើក QR រួចរាល់! ប៊ូតុង បង់ប្រាក់ KHQR នឹងបង្ហាញវិញ។" if new_status == "1" else "បានបិទ QR រួចរាល់! ប៊ូតុង បង់ប្រាក់ KHQR នឹងត្រូវលាក់។"
    await call.answer(msg_text, show_alert=True)
    await adm_payment_aba_cb(call)

# --- 10. 📦 Order & ♻️ Reset Order ---
@dp.callback_query(F.data == "adm_orders_list")
async def adm_orders_list_cb(call: CallbackQuery):
    orders = db_query("SELECT id, user_id, game, pack, price, status, ref_id, date FROM orders ORDER BY id DESC LIMIT 15", fetchall=True)
    total_cnt = db_query("SELECT COUNT(*) FROM orders", fetch=True)[0]

    if not orders:
        kb = [
            [IBtn("Back", "adm_general_menu", style=None, icon_custom_emoji_id="5253997076169115797")]
        ]
        return await call.message.edit_text("📦 <b>បញ្ជីការបញ្ជាទិញរបស់ភ្ញៀវ (Orders)</b>\n━━━━━━━━━━━━━━━━━━━━\nមិនទាន់មានការបញ្ជាទិញនៅឡើយទេ!", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

    text = f"📦 <b>ការបញ្ជាទិញរបស់ភ្ញៀវ (15 ចុងក្រោយ / សរុប {total_cnt})</b>\n━━━━━━━━━━━━━━━━━━━━\n"
    for o in orders:
        text += f"#{o[0]} | ID: <code>{o[1]}</code> | {o[2]} ({o[3]})\n💵 ${o[4]:.2f} | {o[5]} | {o[7]}\nRef: <code>{o[6]}</code>\n━━━━━━━━━━━━━━━━━━━━\n"

    kb = [
        [IBtn("♻️ Reset Order", "adm_reset_orders_confirm", style=None)],
        [IBtn("Back", "adm_general_menu", style=None, icon_custom_emoji_id="5253997076169115797")]
    ]
    await call.message.edit_text(text[:4000], reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "adm_reset_orders_confirm")
async def adm_reset_orders_confirm_cb(call: CallbackQuery):
    kb = [
        [
            IBtn("✅ បញ្ជាក់ Reset Order", "adm_reset_orders_exec", style=None),
            IBtn("ត្រលប់", "adm_orders_list", style=None, icon_custom_emoji_id="5253997076169115797")
        ]
    ]
    await call.message.edit_text(
        "⚠️ <b>បញ្ជាក់ការ Reset ទិន្នន័យ Order</b>\n━━━━━━━━━━━━━━━━━━━━\nតើអ្នកពិតជាចង់លុបទិន្នន័យ Order ចាស់ៗទាំងអស់មែនទេ?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )

@dp.callback_query(F.data == "adm_reset_orders_exec")
async def adm_reset_orders_exec_cb(call: CallbackQuery):
    db_query("DELETE FROM orders")
    db_query("UPDATE users SET total_orders=0, total_spent=0, last_order_date=NULL")
    await call.answer("បាន Reset ទិន្នន័យ Order ចាស់ៗទាំងអស់ដោយជោគជ័យ!", show_alert=True)
    await adm_orders_list_cb(call)

# --- 11. 🎨 CUSTOM EMOJI (PREMIUM) ---
def _get_all_custom_emoji_items():
    items = []
    custom_count = 0
    for key, label, default_id in CUSTOM_EMOJI_BUTTONS:
        val = get_setting(f"ce_{key}")
        is_set = bool(val and str(val).strip())
        if is_set:
            custom_count += 1
        items.append(("btn", key, label, is_set, val if is_set else default_id))

    games = db_query("SELECT id, name, emoji_id FROM games ORDER BY id ASC", fetchall=True)
    for gid, gname, gemoji in games:
        is_set = bool(gemoji and str(gemoji).strip() and str(gemoji).strip() != "6131808852972144634")
        if is_set:
            custom_count += 1
        items.append(("game", str(gid), f"🎮 {gname}", is_set, gemoji if is_set else "6131808852972144634"))
    return items, custom_count

async def show_custom_emoji_menu(call: CallbackQuery, page: int = 0):
    items, custom_count = _get_all_custom_emoji_items()
    per_page = 16
    start = page * per_page
    end = start + per_page
    page_items = items[start:end]

    text = (
        f"🎨 Custom Emoji (Premium)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ = កំណត់រួច · ▫️ = ប្រើ Emoji ដើម\n"
        f"🎯 កំណត់រួច: {custom_count} ប៊ូតុង\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"សូមជ្រើសរើសប៊ូតុងដែលចង់ដូរ Emoji៖"
    )

    kb = []
    row = []
    for kind, item_id, label, is_set, current_eid in page_items:
        mark = "✅" if is_set else "▫️"
        cb = f"ce_edit_btn_{item_id}" if kind == "btn" else f"ce_edit_game_{item_id}"
        row.append(IBtn(f"{mark} {label}", cb, style=None))
        if len(row) == 2:
            kb.append(row)
            row = []
    if row:
        kb.append(row)

    nav_row = []
    if page > 0:
        nav_row.append(IBtn("⬅️ ថយទំព័រ", f"ce_page_{page-1}", style=None))
    if end < len(items):
        nav_row.append(IBtn("ទំព័រ​បន្ទាប់ ➡️", f"ce_page_{page+1}", style=None))
    if nav_row:
        kb.append(nav_row)

    kb.append([
        IBtn("♻️ Reset Emoji", "ce_reset_all", style=None),
        IBtn("Back", "back_admin", style=None, icon_custom_emoji_id="5253997076169115797")
    ])

    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "adm_custom_emoji")
async def adm_custom_emoji_cb(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_custom_emoji_menu(call, page=0)

@dp.callback_query(F.data.startswith("ce_page_"))
async def ce_page_cb(call: CallbackQuery):
    page = int(call.data.split("_")[2])
    await show_custom_emoji_menu(call, page=page)

@dp.callback_query(F.data == "ce_reset_all")
async def ce_reset_all_cb(call: CallbackQuery):
    for key, _, _ in CUSTOM_EMOJI_BUTTONS:
        set_setting(f"ce_{key}", "")
    db_query("UPDATE games SET emoji_id=NULL")
    await call.answer("បាន Reset Emoji ទាំងអស់ទៅជាដើមវិញហើយ!", show_alert=True)
    await show_custom_emoji_menu(call, page=0)

@dp.callback_query(F.data.startswith("ce_edit_btn_"))
async def ce_edit_btn_cb(call: CallbackQuery, state: FSMContext):
    key = call.data[len("ce_edit_btn_"):]
    label = next((lbl for k, lbl, _ in CUSTOM_EMOJI_BUTTONS if k == key), key)
    await state.update_data(ce_kind="btn", ce_target=key, ce_label=label)
    await state.set_state(AdminState.set_custom_emoji)
    text = (
        f"🎨 ដូរ Emoji សម្រាប់ប៊ូតុង: {label}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"សូមផ្ញើ Emoji Premium មកផ្ទាល់ (បើអ្នកមាន Telegram Premium)\n"
        f"ឬផ្ញើលេខ custom_emoji_id ដែលបានពី @ShowJsonBot\n\n"
        f"ឧទាហរណ៍\n"
        f"•5391044040860906456\n\n"
        f"🗑️ ផ្ញើ remove ដើម្បីត្រឡប់ទៅ Emoji ដើម\n"
        f"❌ ចុច /cancel ដើម្បីបោះបង់"
    )
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
        IBtn("ត្រលប់", "adm_custom_emoji", style=None, icon_custom_emoji_id="5253997076169115797")
    ]]))

@dp.callback_query(F.data.startswith("ce_edit_game_"))
async def ce_edit_game_cb(call: CallbackQuery, state: FSMContext):
    gid = int(call.data[len("ce_edit_game_"):])
    g = db_query("SELECT name FROM games WHERE id=?", (gid,), fetch=True)
    label = g[0] if g else f"Game #{gid}"
    await state.update_data(ce_kind="game", ce_target=str(gid), ce_label=label)
    await state.set_state(AdminState.set_custom_emoji)
    text = (
        f"🎨 ដូរ Emoji សម្រាប់ប៊ូតុង: {label}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"សូមផ្ញើ Emoji Premium មកផ្ទាល់ (បើអ្នកមាន Telegram Premium)\n"
        f"ឬផ្ញើលេខ custom_emoji_id ដែលបានពី @ShowJsonBot\n\n"
        f"ឧទាហរណ៍\n"
        f"•5391044040860906456\n\n"
        f"🗑️ ផ្ញើ remove ដើម្បីត្រឡប់ទៅ Emoji ដើម\n"
        f"❌ ចុច /cancel ដើម្បីបោះបង់"
    )
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
        IBtn("ត្រលប់", "adm_custom_emoji", style=None, icon_custom_emoji_id="5253997076169115797")
    ]]))

@dp.callback_query(F.data == "ce_preview_noop")
async def ce_preview_noop_cb(call: CallbackQuery):
    await call.answer("👁 នេះជាការបង្ហាញសាកល្បង Emoji Premium!", show_alert=False)

@dp.message(AdminState.set_custom_emoji)
async def ce_save_custom_emoji_msg(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    if txt == "/cancel":
        await state.clear()
        return await msg.answer("បានបោះបង់!", reply_markup=main_menu(msg.from_user.id))

    data = await state.get_data()
    kind = data.get("ce_kind")
    target = data.get("ce_target")
    label = data.get("ce_label", "Button")

    if txt.lower() == "remove":
        if kind == "btn":
            set_setting(f"ce_{target}", "")
            default_id = next((d for k, _, d in CUSTOM_EMOJI_BUTTONS if k == target), "")
        else:
            db_query("UPDATE games SET emoji_id=NULL WHERE id=?", (int(target),))
            default_id = "5427168083074628963"

        await state.clear()
        return await msg.answer(
            f"✅ បានត្រឡប់ទៅ Emoji ដើមរួចរាល់!\n━━━━━━━━━━━━━━━━━━━━\n- ប៊ូតុង: {label}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [IBtn(label, "ce_preview_noop", style=None, icon_custom_emoji_id=default_id or None)],
                [IBtn("⚙️Admin Panel", "back_admin", style=None)]
            ])
        )

    emoji_id = None
    if msg.entities:
        for ent in msg.entities:
            if getattr(ent, "type", None) == "custom_emoji" and getattr(ent, "custom_emoji_id", None):
                emoji_id = str(ent.custom_emoji_id)
                break
    if not emoji_id and txt.isdigit():
        emoji_id = txt

    if not emoji_id:
        return await msg.answer("❌ ទម្រង់មិនត្រឹមត្រូវ! សូមផ្ញើ Emoji Premium ផ្ទាល់ ឬលេខ custom_emoji_id (ឧ. 5391044040860906456) ឬផ្ញើ remove។")

    if kind == "btn":
        set_setting(f"ce_{target}", emoji_id)
    else:
        db_query("UPDATE games SET emoji_id=? WHERE id=?", (emoji_id, int(target)))

    await state.clear()
    res_text = (
        f"✅ បានដូរ Emoji រួចរាល់!\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"- ប៊ូតុង: {label}\n"
        f"- Emoji ID: <code>{emoji_id}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👁 ខាងក្រោមនេះជាការបង្ហាញសាកល្បង៖"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(label, "ce_preview_noop", style=None, icon_custom_emoji_id=emoji_id)],
        [IBtn("⚙️Admin Panel", "back_admin", style=None)]
    ])
    await msg.answer(res_text, reply_markup=kb)


# --- 12. CLONE BOT & MY BOT (IN-PROCESS ASYNCIO) ---
async def _clone_polling_loop(clone_bot: Bot, db_path: str, clone_admin_id: int):
    _bot_configs[clone_bot.id] = (db_path, clone_admin_id, True)
    try:
        await clone_bot.delete_webhook(drop_pending_updates=True)
        offset = None
        while True:
            try:
                updates = await clone_bot.get_updates(
                    offset=offset,
                    timeout=30,
                    allowed_updates=dp.resolve_used_update_types()
                )
                for upd in updates:
                    offset = upd.update_id + 1
                    asyncio.create_task(dp.feed_update(clone_bot, upd))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logging.error(f"Clone bot {clone_bot.id} polling error: {e}")
                await asyncio.sleep(3)
    finally:
        _clone_tasks.pop(clone_bot.id, None)
        try:
            await clone_bot.session.close()
        except Exception:
            pass

def start_clone_bot_task(bot_id: int, token: str, db_path: str, clone_admin_id: int):
    existing = _clone_tasks.get(bot_id)
    if existing and not existing.done():
        return False
    init_db_for(db_path, clone_admin_id, is_clone=True)
    clone_bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    task = asyncio.create_task(_clone_polling_loop(clone_bot, db_path, clone_admin_id))
    _clone_tasks[bot_id] = task
    return True

async def stop_clone_bot_task(bot_id: int):
    task = _clone_tasks.pop(bot_id, None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

@dp.callback_query(F.data == "adm_clone_menu")
async def adm_clone_menu_cb(call: CallbackQuery, state: FSMContext):
    if _ctx_is_clone.get():
        return await call.answer("មុខងារនេះសម្រាប់តែ Bot មេប៉ុណ្ណោះ!", show_alert=True)
    await state.clear()
    text = (
        f"{pemoji('5445163772706582819', '🤖')} <b>សូមរើសមុខងារ Clone Bot ដើម្បីបង្កើត Bot Topup អោយភ្ញៀវ៖</b>\n"
        f"🔽 ជ្រើសរើស"
    )
    kb = [
        [
            IBtn("Clone Bot", "adm_clone_start", style=None, icon_custom_emoji_id="5445163772706582819"),
            IBtn("My Bot", "adm_my_bots", style=None, icon_custom_emoji_id="5258093637450866522")
        ],
        [
            IBtn("Back", "back_admin", style=None, icon_custom_emoji_id="5253997076169115797")
        ]
    ]
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "adm_clone_start")
async def adm_clone_start_cb(call: CallbackQuery, state: FSMContext):
    if _ctx_is_clone.get():
        return
    text = (
        f"🔑 <b>Token</b> លេខសម្ងាត់របស់ Bot ដែលយកមកពី @botfather\n"
        f"⚠️ សូមប្រុងប្រយ័ត្នកុំអោយអ្នកដ៏ទ័យគេឃើញ Token\n\n"
        f"👉 ដាក់ចូលមកទីនេះមក (\n"
        f"ឧ . <code>12345678:YcUfHtdBtdNyFbyfbydbydvurcbugbTrcYfbhy</code>\n\n"
        f"(ឬចុច /cancel ដើម្បីបោះបង់)"
    )
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
        IBtn("ត្រលប់", "adm_clone_menu", style=None, icon_custom_emoji_id="5253997076169115797")
    ]]))
    await state.set_state(AdminState.clone_token)

@dp.message(AdminState.clone_token)
async def adm_clone_token_input(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    if txt == "/cancel":
        await state.clear()
        return await msg.answer("បានបោះបង់!", reply_markup=main_menu(msg.from_user.id))

    if ":" not in txt or len(txt) < 20:
        return await msg.answer("❌ Token មិនត្រឹមត្រូវទេ! សូមផ្ញើ Token ពី @BotFather ម្ដងទៀត (ឬ /cancel)៖")

    temp_bot = Bot(token=txt)
    try:
        me = await temp_bot.get_me()
    except Exception:
        try: await temp_bot.session.close()
        except Exception: pass
        return await msg.answer("❌ មិនអាចភ្ជាប់ Token នេះបានទេ! សូមពិនិត្យ Token ឡើងវិញ (ឬ /cancel)៖")
    try:
        await temp_bot.session.close()
    except Exception:
        pass

    exist = db_query("SELECT id FROM cloned_bots WHERE bot_id=?", (me.id,), fetch=True, db_path="topup_system.db")
    if exist:
        return await msg.answer(f"⚠️ Bot @{me.username} នេះត្រូវបាន Clone រួចហើយ! សូមពិនិត្យក្នុង My Bot ឬប្រើ Token ថ្មី។")

    await state.update_data(clone_token=txt, clone_bot_id=me.id, clone_username=me.username or str(me.id))
    await state.set_state(AdminState.clone_admin_id)

    text = (
        f"🔑 <b>Token Bot :</b> <code>{txt}</code>\n"
        f"🤖 <b>Username :</b> @{me.username}\n\n"
        f"👉 សូមដាក់ ID Telegram របស់បងមកទីនេះមកណា ខ្ញុំនឹងដាក់បងជា Admin Bot ៖"
    )
    await msg.answer(text)

@dp.message(AdminState.clone_admin_id)
async def adm_clone_admin_id_input(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    if txt == "/cancel":
        await state.clear()
        return await msg.answer("បានបោះបង់!", reply_markup=main_menu(msg.from_user.id))

    try:
        clone_adm_id = int(txt)
    except Exception:
        return await msg.answer("❌ ID Telegram ត្រូវតែជាលេខ (ឧ. 123456789)៖")

    data = await state.get_data()
    token = data["clone_token"]
    bot_id = data["clone_bot_id"]
    username = data["clone_username"]
    db_path = f"clone_bots/bot_{bot_id}.db"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    db_query(
        "INSERT INTO cloned_bots (bot_id, username, token, admin_id, db_path, is_active, created_at) VALUES (?, ?, ?, ?, ?, 1, ?)",
        (bot_id, username, token, clone_adm_id, db_path, now_str),
        db_path="topup_system.db"
    )
    start_clone_bot_task(bot_id, token, db_path, clone_adm_id)
    await state.clear()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn("My Bot", "adm_my_bots", style=None, icon_custom_emoji_id="5258093637450866522")],
        [IBtn("⚙️ Admin Panel", "back_admin", style=None)]
    ])
    await msg.answer(
        f"{pemoji('6023773095284707791', '✅')} <b>បាន Clone Bot ជោគជ័យ និងដំណើរការភ្លាមៗ!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 Bot: @{username}\n"
        f"👑 Admin ID: <code>{clone_adm_id}</code>\n"
        f"🟢 ស្ថានភាព: <b>កំពុងដំណើរការ</b>",
        reply_markup=kb
    )

@dp.callback_query(F.data == "adm_my_bots")
async def adm_my_bots_cb(call: CallbackQuery):
    if _ctx_is_clone.get():
        return
    bots = db_query("SELECT id, bot_id, username, admin_id, is_active FROM cloned_bots ORDER BY id DESC", fetchall=True, db_path="topup_system.db")
    if not bots:
        return await call.message.edit_text(
            f"{pemoji('5258093637450866522', '🤖')} <b>My Bot</b>\n━━━━━━━━━━━━━━━━━━━━\nមិនទាន់មាន Bot ដែលបាន Clone នៅឡើយទេ!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [IBtn("Clone Bot", "adm_clone_start", style=None, icon_custom_emoji_id="5445163772706582819")],
                [IBtn("Back", "adm_clone_menu", style=None, icon_custom_emoji_id="5253997076169115797")]
            ])
        )

    kb = []
    for cid, bid, uname, adm_id, is_act in bots:
        running = (bid in _clone_tasks and not _clone_tasks[bid].done())
        icon = "🟢" if (is_act and running) else "🔴"
        kb.append([IBtn(f"{icon} @{uname} (Admin: {adm_id})", f"adm_clone_view_{cid}", style=None)])
    kb.append([IBtn("Back", "adm_clone_menu", style=None, icon_custom_emoji_id="5253997076169115797")])

    await call.message.edit_text(
        f"{pemoji('5258093637450866522', '🤖')} <b>My Bot (សរុប {len(bots)})</b>\n━━━━━━━━━━━━━━━━━━━━\nសូមជ្រើសរើស Bot ដើម្បីគ្រប់គ្រង៖",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )

@dp.callback_query(F.data.startswith("adm_clone_view_"))
async def adm_clone_view_cb(call: CallbackQuery):
    cid = int(call.data.split("_")[-1])
    row = db_query("SELECT id, bot_id, username, admin_id, is_active, created_at FROM cloned_bots WHERE id=?", (cid,), fetch=True, db_path="topup_system.db")
    if not row:
        await call.answer("រកមិនឃើញ Bot នេះទេ!", show_alert=True)
        return await adm_my_bots_cb(call)

    _, bid, uname, adm_id, is_act, created_at = row
    running = (bid in _clone_tasks and not _clone_tasks[bid].done())
    status_str = "🟢 កំពុងដំណើរការ" if (is_act and running) else "🔴 បានបញ្ឈប់"

    text = (
        f"{pemoji('5258093637450866522', '🤖')} <b>គ្រប់គ្រង Bot: @{uname}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 Bot ID: <code>{bid}</code>\n"
        f"👑 Admin ID: <code>{adm_id}</code>\n"
        f"📡 ស្ថានភាព: <b>{status_str}</b>\n"
        f"📅 បង្កើតនៅ: {created_at}"
    )
    kb = [
        [
            IBtn("បពា្ឈប Bot", f"adm_clone_stop_{cid}", style=None, icon_custom_emoji_id="6323489940562780480"),
            IBtn("បពា្ឈេះ Bot", f"adm_clone_start_bot_{cid}", style=None, icon_custom_emoji_id="6323433929894272747")
        ],
        [
            IBtn("លុប Bot ចោល", f"adm_clone_del_{cid}", style=None, icon_custom_emoji_id="6325455545230697610")
        ],
        [
            IBtn("Back", "adm_my_bots", style=None, icon_custom_emoji_id="5253997076169115797")
        ]
    ]
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("adm_clone_stop_"))
async def adm_clone_stop_cb(call: CallbackQuery):
    cid = int(call.data.split("_")[-1])
    row = db_query("SELECT bot_id, username FROM cloned_bots WHERE id=?", (cid,), fetch=True, db_path="topup_system.db")
    if not row:
        return await call.answer("រកមិនឃើញ Bot នេះទេ!", show_alert=True)
    bid, uname = row
    await stop_clone_bot_task(bid)
    db_query("UPDATE cloned_bots SET is_active=0 WHERE id=?", (cid,), db_path="topup_system.db")
    await call.answer(f"បានបញ្ឈប់ Bot @{uname} រួចរាល់!", show_alert=True)
    call_copy = call.model_copy(update={"data": f"adm_clone_view_{cid}"})
    await adm_clone_view_cb(call_copy)

@dp.callback_query(F.data.startswith("adm_clone_start_bot_"))
async def adm_clone_start_bot_cb(call: CallbackQuery):
    cid = int(call.data.split("_")[-1])
    row = db_query("SELECT bot_id, username, token, admin_id, db_path FROM cloned_bots WHERE id=?", (cid,), fetch=True, db_path="topup_system.db")
    if not row:
        return await call.answer("រកមិនឃើញ Bot នេះទេ!", show_alert=True)
    bid, uname, token, adm_id, db_path = row
    db_query("UPDATE cloned_bots SET is_active=1 WHERE id=?", (cid,), db_path="topup_system.db")
    started = start_clone_bot_task(bid, token, db_path, adm_id)
    msg = f"បានបញ្ឆេះ Bot @{uname} ដំណើរការវិញភ្លាម!" if started else f"Bot @{uname} កំពុងដំណើរការស្រាប់ហើយ!"
    await call.answer(msg, show_alert=True)
    call_copy = call.model_copy(update={"data": f"adm_clone_view_{cid}"})
    await adm_clone_view_cb(call_copy)

@dp.callback_query(F.data.startswith("adm_clone_del_"))
async def adm_clone_del_cb(call: CallbackQuery):
    cid = int(call.data.split("_")[-1])
    row = db_query("SELECT bot_id, username, db_path FROM cloned_bots WHERE id=?", (cid,), fetch=True, db_path="topup_system.db")
    if not row:
        return await call.answer("រកមិនឃើញ Bot នេះទេ!", show_alert=True)
    bid, uname, db_path = row
    await stop_clone_bot_task(bid)
    db_query("DELETE FROM cloned_bots WHERE id=?", (cid,), db_path="topup_system.db")
    if db_path and os.path.exists(db_path):
        try: os.remove(db_path)
        except Exception: pass
    await call.answer(f"បានលុប Bot @{uname} ចោលរួចរាល់!", show_alert=True)
    await adm_my_bots_cb(call)

# =====================================================================
# [ MAIN LOOP ]
# =====================================================================
async def main():
    active_clones = db_query("SELECT bot_id, token, db_path, admin_id FROM cloned_bots WHERE is_active=1", fetchall=True, db_path="topup_system.db")
    for bid, tok, dbp, adm in active_clones:
        try:
            start_clone_bot_task(bid, tok, dbp, adm)
        except Exception as e:
            logging.error(f"Failed to start clone bot {bid}: {e}")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())