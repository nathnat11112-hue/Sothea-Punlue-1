# ====================================================================================================
# 🤖 NAJA  MOD KEY BOT - AUTOMATION SYSTEM (ULTIMATE UPDATE PRO)
# ====================================================================================================

import os
import re
import shutil
import asyncio
import sqlite3
import logging
import time
import aiohttp
import base64
import hashlib
import json
import contextvars
import urllib.parse
from datetime import datetime, timedelta
from typing import Any, Dict
from io import BytesIO

# អីមផត Library ថ្មីសម្រាប់គូរ KHQR
import qrcode
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from aiogram import Bot, Dispatcher, F, html, BaseMiddleware
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile, TelegramObject, BotCommand, WebAppInfo
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# ====================================================================================================
# [ កំណត់រចនាសម្ព័ន្ធទូទៅ ]
# ====================================================================================================

BOT_TOKEN = ""
OWNER_ID = 8824068178
MAIN_BOT_ID = int(BOT_TOKEN.split(':')[0])

# 🚀 ABA API URL (https://khmer-system.com)
ABA_BASE_URL = "https://khmer-system.com"
ABA_CREATE_URL = "https://khmer-system.com/aba-api/generate-qr"
ABA_CHECK_URL = "https://khmer-system.com/aba-api/check-payment"
ABA_TRANSACTIONS_URL = "https://khmer-system.com/aba-api/transactions"
ABA_MARK_CREDITED_URL = "https://khmer-system.com/aba-api/mark-credited"

# 🚀 KHQRPAY.SITE ABA API
KHQRPAY_ABA_CREATE_URL = "https://khqrpay.site/api/v1/aba/create"
KHQRPAY_BAKONG_CREATE_URL = "https://khqrpay.site/api/v1/bakong/create"
KHQRPAY_CHECK_URL = "https://khqrpay.site/api/v1/payment"
KHQRPAY_PAYMENTS_URL = "https://khqrpay.site/api/v1/payments"

# 🚀 BAKONG CLIENT (Based on bakong_client.py with proxy support)
try:
    from bakong_khqr import KHQR
except Exception:
    KHQR = None

CAMRAPID_API_KEY_DEFAULT = "d9f5828e6913f9fccb3b9b2368aee92312f2a17a2c091947f4beb7ea579a60f4"
CAMRAPID_CREATE_URL = "https://pay.camrapidpay.com/api/v1/khqr/create-payments"
CAMRAPID_CHECK_URL = "https://pay.camrapidpay.com/check-transaction-api"
BAKONG_API_BASE_DEFAULT = os.getenv("BAKONG_API_BASE", "https://pay.camrapidpay.com").rstrip("/")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger("vbenstoreBot")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Context variables សម្រាប់បំបែក Database និង Owner ដាច់ដោយឡែកពីគ្នាគ្រប់ Bot កូនទាំងអស់
current_db_var = contextvars.ContextVar('current_db', default='vbenstore.db')
current_owner_var = contextvars.ContextVar('current_owner', default=OWNER_ID)
is_clone_var = contextvars.ContextVar('is_clone', default=False)

def get_current_owner():
    return current_owner_var.get()

def is_clone_bot():
    return is_clone_var.get()

background_tasks = set()
def run_bg_task(coro):
    task = asyncio.create_task(coro)
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)

cloned_bot_tasks = {}

async def clone_bot_poller(bot_instance):
    try:
        await bot_instance.delete_webhook(drop_pending_updates=True)
        await bot_instance.set_my_commands([
            BotCommand(command="start", description="ចាប់ផ្ដើមបត"),
            BotCommand(command="shop", description="🛍 ទិញទំនិញ / Buy Store"),
        ])
        offset = None
        while True:
            try:
                updates = await bot_instance.get_updates(offset=offset, timeout=10)
                for update in updates:
                    offset = update.update_id + 1
                    await dp.feed_update(bot_instance, update)
            except Exception as e:
                if not isinstance(e, asyncio.TimeoutError):
                    await asyncio.sleep(5)
            await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        pass
    finally:
        try: await bot_instance.session.close()
        except: pass

async def start_cloned_bot(token, bot_id):
    cb = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    # បង្កើត Database ដាច់ដោយឡែកសម្រាប់បតកូន
    row = execute_db('SELECT owner_id FROM cloned_bots WHERE id=?', (bot_id,), fetch=True, db_path='vbenstore.db')
    clone_owner = row[0] if row else 0
    tg_bot_id = int(token.split(':')[0])
    init_db(f"vbenstore_{tg_bot_id}.db", clone_owner, is_main=False)
    
    task = asyncio.create_task(clone_bot_poller(cb))
    cloned_bot_tasks[bot_id] = {'bot': cb, 'task': task}

# ====================================================================================================
# [ មូលដ្ឋានទិន្នន័យ (DATABASE) ]
# ====================================================================================================

DEFAULT_START_TEXT = """<tg-emoji emoji-id="5458904472598095631">👋</tg-emoji> <b>{bot_name}</b> សូមស្វារគមន៍ {name} !

Please Select: / សូមជ្រើសរើស៖"""

def init_db(db_path='vbenstore.db', owner_id=OWNER_ID, is_main=True):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, is_admin INTEGER DEFAULT 0, is_reseller INTEGER DEFAULT 0, first_name TEXT, username TEXT, is_banned INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, icon TEXT, media_data TEXT, description TEXT)''')
    try: c.execute('ALTER TABLE categories ADD COLUMN description TEXT')
    except: pass
    c.execute('''CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY AUTOINCREMENT, cat_id INTEGER, name TEXT, price REAL, reseller_price REAL, icon TEXT, post_media TEXT, is_infinite INTEGER DEFAULT 0, infinite_data TEXT)''')
    try: c.execute('ALTER TABLE items ADD COLUMN is_infinite INTEGER DEFAULT 0')
    except: pass
    try: c.execute('ALTER TABLE items ADD COLUMN infinite_data TEXT')
    except: pass
    try: c.execute('ALTER TABLE items ADD COLUMN reseller_vip_price REAL DEFAULT 0.0')
    except: pass
    try: c.execute('ALTER TABLE items ADD COLUMN api_package_id INTEGER DEFAULT NULL')
    except: pass
    try: c.execute('ALTER TABLE users ADD COLUMN is_reseller_vip INTEGER DEFAULT 0')
    except: pass
    try: c.execute('ALTER TABLE users ADD COLUMN balance REAL DEFAULT 0.0')
    except: pass
    try: c.execute('ALTER TABLE categories ADD COLUMN is_disabled INTEGER DEFAULT 0')
    except: pass
    c.execute('''CREATE TABLE IF NOT EXISTS stock (id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER, key_data TEXT, is_sold INTEGER DEFAULT 0, type TEXT DEFAULT 'text')''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item_id INTEGER, qty INTEGER, total_price REAL, date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS cloned_bots (id INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT, bot_username TEXT, bot_name TEXT, owner_id INTEGER, is_active INTEGER DEFAULT 1)''')
    c.execute('''CREATE TABLE IF NOT EXISTS pending_payments (payment_id TEXT PRIMARY KEY, pay_type TEXT, user_id INTEGER, chat_id INTEGER, item_id INTEGER, qty INTEGER, msg_id INTEGER, total REAL, item_name TEXT, created_at REAL, is_done INTEGER DEFAULT 0)''')
    
    try: c.execute('ALTER TABLE users ADD COLUMN first_name TEXT')
    except: pass
    try: c.execute('ALTER TABLE users ADD COLUMN username TEXT')
    except: pass
    try: c.execute('ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0')
    except: pass
    try: c.execute('ALTER TABLE orders ADD COLUMN key_data TEXT')
    except: pass
    
    if owner_id:
        c.execute('INSERT OR IGNORE INTO users (id, is_admin) VALUES (?, 1)', (owner_id,))
        c.execute('UPDATE users SET is_admin=1 WHERE id=?', (owner_id,))
    
    # Default settings
    if is_main:
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('aba_api_key', 'PK_3f705d8861aa25b2c2f3319bd51ad942a73586b2'))
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('aba_merchant_id', 'LM2cgk'))
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('aba_pay_status', 'on'))
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('aba_qr_name', 'ITACHI BOT 24 H'))
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('contact_admin_url', 'https://t.me/Vbenstore168'))
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('manual_khqr_status', 'off'))
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('bakong_api_key', CAMRAPID_API_KEY_DEFAULT))
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('bakong_username_id', ''))
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('bakong_pay_status', 'off'))
    else:
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('aba_api_key', ''))
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('aba_merchant_id', ''))
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('aba_pay_status', 'off'))
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('aba_qr_name', 'ITACHI BOT 24 H'))
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('manual_khqr_status', 'off'))
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('bakong_api_key', ''))
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('bakong_username_id', ''))
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('bakong_pay_status', 'off'))
        
    c.execute("UPDATE settings SET value=? WHERE key='start_text'", (DEFAULT_START_TEXT,))
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('start_text', DEFAULT_START_TEXT))
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('reseller_api_url', 'https://reseller.panelkey.shop/api/v1/reseller'))
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('reseller_api_token', 'pk_e4d53cb2d92afba51cbb896ff40f882706afdc5e064dd243'))
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('profit_margin', '0.0'))
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('khqrpay_api_key', ''))
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('khqrpay_pay_status', 'off'))
    
    conn.commit()
    conn.close()

def execute_db(query, params=(), fetch=False, fetchall=False, db_path=None):
    target_db = db_path if db_path else current_db_var.get()
    conn = sqlite3.connect(target_db, timeout=30)
    c = conn.cursor()
    try:
        c.execute(query, params)
        if fetchall: res = c.fetchall()
        elif fetch: res = c.fetchone()
        else: 
            conn.commit()
            res = c.lastrowid
        return res
    except Exception as e:
        logger.error(f"DB Error ({target_db}): {e}")
        return None
    finally:
        conn.close()

# Auto-migrate from zento_store.db to vbenstore.db if needed
if os.path.exists("zento_store.db") and not os.path.exists("vbenstore.db"):
    try:
        import shutil
        shutil.copyfile("zento_store.db", "vbenstore.db")
        logger.info("Migrated zento_store.db to vbenstore.db successfully.")
    except Exception as e:
        logger.warning(f"Could not copy zento_store.db: {e}")

init_db('vbenstore.db', OWNER_ID, is_main=True)

# ====================================================================================================
# [ BAN & USER TRACKING & MULTI-BOT CONTEXT MIDDLEWARE ]
# ====================================================================================================

class BanCheckMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: Dict[str, Any]) -> Any:
        bot_obj: Bot = data.get("bot")
        if bot_obj and bot_obj.id != MAIN_BOT_ID:
            db_name = f"vbenstore_{bot_obj.id}.db"
            row = execute_db('SELECT owner_id FROM cloned_bots WHERE token LIKE ?', (f"{bot_obj.id}:%",), fetch=True, db_path='vbenstore.db')
            clone_owner = row[0] if row else 0
            init_db(db_name, clone_owner, is_main=False)
            current_db_var.set(db_name)
            current_owner_var.set(clone_owner)
            is_clone_var.set(True)
        else:
            current_db_var.set('vbenstore.db')
            current_owner_var.set(OWNER_ID)
            is_clone_var.set(False)

        user = data.get("event_from_user")
        if user:
            execute_db('UPDATE users SET first_name=?, username=? WHERE id=?', (user.first_name, user.username, user.id))
            banned_check = execute_db('SELECT is_banned FROM users WHERE id=?', (user.id,), fetch=True)
            if banned_check and banned_check[0] == 1:
                if isinstance(event, Message):
                    await event.answer("🚫 គណនីរបស់អ្នកត្រូវបាន Ban មិនអាចប្រើប្រាស់ប្រព័ន្ធបានទេ!")
                elif isinstance(event, CallbackQuery):
                    await event.answer("🚫 គណនីរបស់អ្នកត្រូវបាន Ban!", show_alert=True)
                return
        return await handler(event, data)

dp.update.middleware(BanCheckMiddleware())
# ====================================================================================================
# [ 👑 PREMIUM & NORMAL EMOJI MAPPING - COMPLETE BOT CATALOG (ALL 87 IDS) ]
# ====================================================================================================

ALL_BOT_BTN_EMOJIS = [
    ("🎬 Upload Video/Photo/GIF", "🎬", "5445373981290952548"),
    ("💬 អក្សរ Welcome", "💬", "6138589833238422233"),
    ("📋 បញ្ជី Reseller + VIP", "📋", "6154222749691679144"),
    ("🛒 BUY NOW", "🛒", "5447319442562251569"),
    ("🔑 My Key", "🔑", "5447387942995655277"),
    ("👑 ADMIN PANEL", "👑", "5444869180899752137"),
    ("👨‍💻 Contact Admin", "👨‍💻", "5447510826304959724"),
    ("🔢 ចំនួនផ្ទាល់ខ្លួន", "🔢", "5213305971891248967"),
    ("🔙 Back / Back to Category", "🔙", "5352759161945867747"),
    ("🔙 Back (Admin)", "🔙", "6035130900075777681"),
    ("🚪 ចាកចេញពីរ Ai", "🚪", "5447651546613449378"),
    ("💳 Pay with ABA", "💳", "6314519407443845610"),
    ("🏦 Setting Payment ABA", "🏦", "6316599954026535998"),
    ("🏦 Pay/Setting Bakong", "🏦", "6095690437165586962"),
    ("🟡 Pay/Setting Binance Pay", "🟡", "5793944030861598035"),
    ("💳 Pay with KHQR", "💳", "5422814644093868925"),
    ("💳 Open App ABA Mobile", "💳", "6068999010717277166"),
    ("💳 បើក App ABA ទូរទាត់", "💳", "6325675417491481533"),
    ("✏️ Edit Contact Admin", "✏️", "6154233835002271015"),
    ("👑 Premium emoji Setting", "👑", "6314076231243404806"),
    ("📦 គ្រុបគ្រងផលលិតផល", "📦", "5312361253610475399"),
    ("👀 មើលស្តុក ( Views Stock )", "👀", "6138721800403559725"),
    ("➕ គ្រប់គ្រងស្តុក ( Add/Delete )", "➕", "6138856219995021560"),
    ("📢 Broadcast", "📢", "5260268501515377807"),
    ("👥 គ្រប់គ្រង់ ( Reseller )", "👥", "6136265963873511020"),
    ("⚙️ Setting", "⚙️", "6151986639393531426"),
    ("📝 Bot Content Setting", "📝", "5226513232549664618"),
    ("📢 កំណត់ Group/Chanel វិក្កយប័ត្រ", "📢", "5445221832074483553"),
    ("🎬 ដាក់វីដេអូ/រូបភាព /start", "🎬", "6138556641731159070"),
    ("❌ ដកវីដេអូ / រូបភាព", "❌", "6176808917549453468"),
    ("🎛 រៀបចំបូតុង", "🎛", "5335054400513649848"),
    ("✅ Verify Payment", "✅", "6023773095284707791"),
    ("⚡ Verify Payment (Auto)", "⚡", "5904704361182798355"),
    ("❌ បោះបង់", "❌", "6102914615107133393"),
    ("🏷 ID Merchants", "🏷", "6231134485702779241"),
    ("🔑 API Key", "🔑", "6230825600244784296"),
    ("➕ Add Mapping", "➕", "6033108614724456536"),
    ("⭐️ Switch Account", "⭐️", "6068828835523073231"),
    ("💬 Reply Chat", "💬", "5188481279963715781"),
    ("💬 Chat Admin", "💬", "5235570365094188078"),
    ("🔙 ត្រលប់ទៅបូតុងភ្ញៀវ", "🔙", "5253997076169115797"),
    ("🤖 My Bots", "🤖", "5258093637450866522"),
    ("🤖 Clone Bots", "🤖", "5258362837411045098"),
    ("🤖 Clone Bot (Admin)", "🤖", "5364125616801073577"),
    ("🗑️ លុប / ដកស្តុក", "🗑️", "5258130763148172425"),
    ("✏️ កែសារជូនដំណឹង", "✏️", "5258331647358540449"),
    ("🗑️ Del Reseller VIP", "🗑️", "5301240299085906131"),
    ("🎛️ រៀបបូតុងបព្ឈទាំងអស់", "🎛️", "5307739641166700726"),
    ("📥 ទាញយក", "📥", "5307746710682869587"),
    ("🎛️ រៀបបូតុង ផលលិតផល", "🎛️", "5352896944496728039"),
    ("➕ បន្ថែមស្តុក", "➕", "5397916757333654639"),
    ("🎬 ដាក់ វីដេអូ / រូបភាព / អត្ថបទ", "🎬", "5407025283456835913"),
    ("📝 ដាក់អត្ថបទ (ផលលិតផល)", "📝", "5444988177263654261"),
    ("✏️ កែឈ្មោះផលលិតផល", "✏️", "5445128296276718145"),
    ("🛒 Buy Now / ទិញឥឡូវនេះ", "🛒", "5445146945024720188"),
    ("❌ ដកអត្ថបទ (ផលលិតផល)", "❌", "5447385112612208213"),
    ("🎛️ រៀបបូតុង កន្លែងរើសវិធីបង់ប្រាក់", "🎛️", "5472238215748397135"),
    ("🎛️ រៀបបូតុង ទំនិញ", "🎛️", "5884479287171485878"),
    ("🗑️ លុប Admin ID", "🗑️", "5891207662678317861"),
    ("🎛️ រៀបបូតុង Admin ទាំងអស់", "🎛️", "5895592588064328942"),
    ("➕ បន្ថែម Admin ថ្មី", "➕", "6033108709213736873"),
    ("✅ បព្ជាក់សំណើរ", "✅", "6102563003314479651"),
    ("⏳ បោះបង់សំណើរ", "⏳", "6253758805755038090"),
    ("🛒 Buy Now / ទិញឥឡូវនេះ", "🛒", "5445146945024720188"),
    ("💵 Top Up / បព្ចូាលទឹកប្រាក់", "💵", "5447579253723918909"),
    ("📦 My Orders / ការបព្ជាទិញរបស់ខ្ញុំ", "📦", "5445023138297447592"),
    ("💳 Balance / តុល្យភាព", "💳", "5444960062407732826"),
    ("📞 Contact Admin / ទាក់ទងអ្នកគ្រប់គ្រង", "📞", "5445046442789999895"),
    ("💰 Pay Balance", "💰", "5444860552310457690"),
    ("🔑 Manager Add Game / del", "🔑", "5445023138297447592"),
    ("🎮 Add Game (API)", "🎮", "5258508428212445001"),
    ("💰 ដាក់ប្រាក់ចំណេញ", "💰", "5814557301196984341"),
    ("🔌 ប្ដូរ api", "🔌", "5447420365703773550"),
    ("📦 គ្រុបគ្រង (add stock / views Stock )", "📦", "5447479640547428304"),
    ("➕ Add Stock / ដោយដៃ", "➕", "5444908424015934570"),
    ("👀 មើលស្តុក", "👀", "5447607759421863856"),
]

ALL_BOT_MSG_EMOJIS = [
    ("👋 Welcome Start", "👋", "5413694143601842851"),
    ("✨ Star / Sparkle", "✨", "6147647300790396307"),
    ("🚀 Auto Delivery", "🚀", "5940672865450860704"),
    ("🛡 Security / Trust", "🛡", "5940466152969871694"),
    ("👉 Point / Click", "👉", "6071034593287345457"),
    ("📦 Product / Stock", "📦", "5231102735817918643"),
    ("🛒 Choose Category", "🛒", "5447319442562251569"),
    ("💰 Total / Price", "💰", "5444860552310457690"),
    ("📅 Order Date", "📅", "5445350406215465190"),
    ("⏱️ Duration Package", "⏱️", "5447253390260207116"),
    ("🔑 Key Data", "🔑", "5445023138297447592"),
    ("⚠️ Warning / Alert", "⚠️", "5258514780469075716"),
    ("✅ Verified / Completed", "✅", "6102563003314479651"),
    ("❌ Rejected / Cancel", "❌", "6102914615107133393"),
    ("⏳ Pending / Timeout", "⏳", "6253758805755038090"),
    ("🧾 Invoice / Bill", "🧾", "5197269100878907942"),
    ("🎮 Game Category", "🎮", "5258049708525380488"),
    ("🔰 Member Role", "🔰", "5287231198098117669"),
    ("🔢 Custom Qty Prompt", "🔢", "5213305971891248967"),
    ("⚡ Instant Auto", "⚡", "5904704361182798355"),
    ("🏛️ Checkout Header", "🏛️", "5332455502917949981"),
    ("💰 Quantity/Total Checkout", "💰", "6285019600664928290"),
    ("👤 User Info", "👤", "5409250385753829649"),
    ("🔑 Key Received", "🔑", "5413395871008058098"),
    ("⏱ Duration Item", "⏱", "5431897022456145283"),
    ("🙏 Thank You Purchase", "🙏", "5436040291507247633"),
    ("✅ QR Bakong Scan", "✅", "5445195276291693508"),
    ("🔑 Token Bot", "🔑", "5258215635996908355"),
    ("🏷 Name Bot", "🏷", "5258328383183396223"),
    ("👑 ID Owner Bot", "👑", "5841276284155467413"),
    ("⚙️ Admin Panel Header", "⚙️", "5890864241388293875"),
    ("📊 Report / Stats", "📊", "6100288912620528566"),
    ("📊 Transfer Note", "📊", "6035162669948867129"),
    ("💰 Amount Paid Note", "💰", "6235459831302460476"),
    ("📦 Item Purchased", "📦", "6242308461598610637"),
    ("📦 Stock Arrived Alert", "📦", "6269366244462301331"),
    ("💬 Notification Text", "💬", "5257965810634202885"),
    ("🛒 Buy Now Notification", "🛒", "6071226041454564573"),
]

ID_TO_CHAR_MAP = {}
for _, char, eid in ALL_BOT_BTN_EMOJIS + ALL_BOT_MSG_EMOJIS:
    ID_TO_CHAR_MAP[str(eid).strip()] = char
ID_TO_CHAR_MAP["6154222749691679144"] = "📋"
ID_TO_CHAR_MAP["5445373981290952548"] = "🎬"
ID_TO_CHAR_MAP["6138589833238422233"] = "💬"
ID_TO_CHAR_MAP["5258508428212445001"] = "🎮"
ID_TO_CHAR_MAP["5814557301196984341"] = "💰"
ID_TO_CHAR_MAP["5447420365703773550"] = "🔌"
ID_TO_CHAR_MAP["5447479640547428304"] = "📦"
ID_TO_CHAR_MAP["5444908424015934570"] = "➕"
ID_TO_CHAR_MAP["5447607759421863856"] = "👀"
ID_TO_CHAR_MAP["5458904472598095631"] = "👋"
ID_TO_CHAR_MAP["5447579253723918909"] = "💵"
ID_TO_CHAR_MAP["5444960062407732826"] = "💳"
ID_TO_CHAR_MAP["5445046442789999895"] = "📞"
ID_TO_CHAR_MAP["6325675417491481533"] = "💳"
ID_TO_CHAR_MAP["5307905813451397794"] = "⏳"


# ====================================================================================================
# [ CUSTOM UI HELPERS & QR GENERATOR ]
# ====================================================================================================

def escape_html(text):
    if not text: return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def render_clean_text(text: str) -> str:
    if not text:
        return ""
    mode = get_setting("emoji_mode", "premium")
    if mode == "normal":
        def _replace_tg(m):
            inner = m.group(2)
            if inner and inner.strip():
                return inner.strip()
            eid_m = re.search(r'emoji-id=["\']?(\d+)["\']?', m.group(1))
            if eid_m:
                return ID_TO_CHAR_MAP.get(eid_m.group(1), "")
            return ""
        return re.sub(r'<tg-emoji([^>]*)>(.*?)</tg-emoji>', _replace_tg, text)
    return text
def IBtn(text, callback_data=None, style=None, icon_custom_emoji_id=None, url=None, web_app=None, btn_key=None):
    mode = get_setting("emoji_mode", "premium")
    use_prem = (mode == "premium")
    
    custom_icon = None
    if btn_key: custom_icon = get_setting(f"btn_emoji_{btn_key}")
    if not custom_icon and callback_data:
        custom_icon = get_setting(f"btn_emoji_{callback_data}")
        if not custom_icon and "_" in callback_data:
            cb_prefix = callback_data.split("_")[0]
            custom_icon = get_setting(f"btn_emoji_{cb_prefix}")
            
    final_icon = custom_icon if custom_icon is not None else icon_custom_emoji_id
    
    btn_text = text
    if not use_prem and final_icon:
        emoji_char = ID_TO_CHAR_MAP.get(str(final_icon).strip())
        if emoji_char and not btn_text.startswith(emoji_char):
            btn_text = f"{emoji_char} {btn_text}"
            
    if web_app:
        btn = InlineKeyboardButton(text=btn_text, web_app=web_app)
    elif url:
        btn = InlineKeyboardButton(text=btn_text, url=url)
    else:
        btn = InlineKeyboardButton(text=btn_text, callback_data=callback_data)
        
    if style:
        try: object.__setattr__(btn, 'style', style)
        except Exception: pass
        
    if use_prem and final_icon:
        s_icon = str(final_icon).strip()
        if any(c.isdigit() for c in s_icon):
            try: object.__setattr__(btn, 'icon_custom_emoji_id', s_icon)
            except Exception: pass
        else:
            if not btn.text.startswith(s_icon):
                btn.text = f"{s_icon} {btn.text}"
    return btn

def RBtn(text, style=None, icon_custom_emoji_id=None, btn_key=None):
    mode = get_setting("emoji_mode", "premium")
    use_prem = (mode == "premium")
    
    custom_icon = get_setting(f"btn_emoji_{btn_key}") if btn_key else None
    final_icon = custom_icon if custom_icon is not None else icon_custom_emoji_id
    
    btn_text = text
    if not use_prem and final_icon:
        emoji_char = ID_TO_CHAR_MAP.get(str(final_icon).strip())
        if emoji_char and not btn_text.startswith(emoji_char):
            btn_text = f"{emoji_char} {btn_text}"
            
    btn = KeyboardButton(text=btn_text)
    if style:
        try: object.__setattr__(btn, 'style', style)
        except Exception: pass
    if use_prem and final_icon and any(c.isdigit() for c in str(final_icon)):
        try: object.__setattr__(btn, 'icon_custom_emoji_id', str(final_icon))
        except Exception: pass
    return btn

def cancel_inline():
    return InlineKeyboardMarkup(inline_keyboard=[[IBtn(text="❌ បោះបង់", callback_data="cancel_action", style="danger", icon_custom_emoji_id="6102914615107133393")]])

def get_item_stock(item_id):
    inf_chk = execute_db('SELECT is_infinite FROM items WHERE id=?', (item_id,), fetch=True)
    if inf_chk and inf_chk[0]:
        return 9999
    res = execute_db('SELECT COUNT(*) FROM stock WHERE item_id=? AND is_sold=0', (item_id,), fetch=True)
    return res[0] if res else 0

def admin_back_inline(cb="adm_manage_products", text="ត្រលប់"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text=text, callback_data=cb, style="primary", icon_custom_emoji_id="5253997076169115797")]
    ])

def skip_emoji_inline(skip_cb):
    return InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="រំលង ( មិនមានpremium )", callback_data=skip_cb, style="primary")],
        [IBtn(text="❌ បោះបង់", callback_data="cancel_action", style="danger", icon_custom_emoji_id="6102914615107133393")]
    ])


EMOJI_PATTERN = re.compile(
    r"^(?:[🌀-🫿☀-➿🇠-🇿"
    r"✂-➰Ⓜ-🉑😀-🙏"
    r"🚀-🛿‍️⃣"
    r"🤀-🧿⌚-⌛⏩-⏳"
    r"▪-◾⬅-⬇⤴-⤵"
    r"⬛-⭕\s]+)"
)

def _strip_leading_emoji(text: str) -> str:
    if not text:
        return text
    return EMOJI_PATTERN.sub("", text).strip()

def get_setting(key, default=None):
    res = execute_db('SELECT value FROM settings WHERE key=?', (key,), fetch=True)
    return res[0] if res else default

async def alert_to_channel(text, current_bot: Bot):
    chan_id = get_setting('channel_id')
    if chan_id:
        try: await current_bot.send_message(chan_id, text)
        except: pass

def get_emoji_str(icon_id, fallback="📦"):
    if not icon_id: return fallback
    mode = get_setting("emoji_mode", "premium")
    s_id = str(icon_id).strip()
    if mode == "normal":
        return ID_TO_CHAR_MAP.get(s_id, fallback)
    if s_id.isdigit():
        char = ID_TO_CHAR_MAP.get(s_id, fallback)
        return f"<tg-emoji emoji-id='{s_id}'>{char}</tg-emoji>"
    return s_id


# Helper Functions សម្រាប់គូរ KHQR ដូច cards.py
def _font(size: int, bold: bool = False, italic: bool = False):
    try:
        if bold and italic:
            return ImageFont.truetype("arialbi.ttf", size)
        elif bold:
            return ImageFont.truetype("arialbd.ttf", size)
        else:
            return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default(size)

def _center(d, text, y, font, fill, cx):
    box = d.textbbox((0, 0), text, font=font)
    d.text((cx - (box[2] - box[0]) / 2 - box[0], y), text, font=font, fill=fill)

# គូរ KHQR ABA អោយដូចរូបភាពពិតៗ ១០០% (ABA' QR 900x1104)
def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc

def generate_bakong_khqr_string(account_id: str, amount: float, merchant_name: str = "ITACHI STORE", bill_no: str = "") -> str:
    def tlv(tag: int, val: str) -> str:
        s = str(val)
        b_len = len(s.encode('utf-8'))
        return f"{tag:02d}{b_len:02d}{s}"
    
    acc = str(account_id or "").strip()
    if not acc:
        acc = "itachi_store@bakong"
    elif "@" not in acc:
        acc = f"{acc}@bakong"

    m_name = (merchant_name or "ITACHI STORE").strip()[:25]
    b_no = (bill_no or "").strip()[:25]

    res = tlv(0, "01") + tlv(1, "12") # Dynamic QR
    sub29 = tlv(0, acc)
    res += tlv(29, sub29)
    res += tlv(52, "5999") # MCC
    res += tlv(53, "840")  # USD
    res += tlv(54, f"{float(amount):.2f}")
    res += tlv(58, "KH")
    res += tlv(59, m_name)
    res += tlv(60, "Phnom Penh")
    sub62 = ""
    if b_no:
        sub62 += tlv(1, b_no)
    sub62 += tlv(7, "Terminal")
    if sub62:
        res += tlv(62, sub62)
    payload = res + "6304"
    crc = crc16_ccitt(payload.encode('utf-8'))
    return payload + f"{crc:04X}"

def create_custom_bakong_khqr(qr_string, amount, merchant_name=None, bakong_id=None):
    if not merchant_name:
        merchant_name = get_setting('aba_qr_name', 'ITACHI STORE') or 'ITACHI STORE'
        
    cw, ch = 900, 1104
    BG_COLOR = (237, 238, 243)
    NAVY_TITLE = (11, 35, 63)
    NAVY_BAR = (13, 34, 65)
    RED_COLOR = (204, 0, 25)
    DARK_TEXT = (26, 32, 44)
    GRAY_CCY = (113, 128, 150)
    DASH_LINE = (203, 213, 225)
    SUB_TEXT = (126, 147, 172)

    img = Image.new("RGB", (cw, ch), BG_COLOR)
    d = ImageDraw.Draw(img)

    f_title = _font(56, bold=True)
    _center(d, "BAKONG KHQR", 55, f_title, NAVY_TITLE, cx=cw // 2)

    L, T, R, B = 110, 160, 790, 980
    radius = 22
    d.rounded_rectangle((L, T, R, B), radius=radius, fill=(255, 255, 255))

    hdr_h = 68
    hdr_mask = Image.new("L", (R - L, hdr_h), 0)
    hd = ImageDraw.Draw(hdr_mask)
    hd.rounded_rectangle((0, 0, R - L, hdr_h + 30), radius=radius, fill=255)
    red_hdr = Image.new("RGB", (R - L, hdr_h), RED_COLOR)
    img.paste(red_hdr, (L, T), hdr_mask)

    f_khqr = _font(32, bold=True)
    _center(d, "KHQR", T + 18, f_khqr, (255, 255, 255), cx=cw // 2)

    f_name = _font(28, bold=True)
    disp_name = str(merchant_name).upper()
    if bakong_id and "@" in str(bakong_id):
        disp_name = f"{disp_name} ({bakong_id})"
    _center(d, disp_name[:26], T + 92, f_name, DARK_TEXT, cx=cw // 2)

    amt_str = f"{amount:,.2f}"
    f_amt = _font(52, bold=True)
    f_ccy = _font(26, bold=False)

    aw = d.textlength(amt_str, font=f_amt)
    cw_box = d.textlength(" USD", font=f_ccy)
    total_w = aw + cw_box

    start_x = (cw - total_w) / 2
    d.text((start_x, T + 135), amt_str, font=f_amt, fill=DARK_TEXT)
    d.text((start_x + aw + 8, T + 155), "USD", font=f_ccy, fill=GRAY_CCY)

    dash_y = T + 205
    x = L + 30
    while x < R - 30:
        d.line([(x, dash_y), (min(x + 10, R - 30), dash_y)], fill=DASH_LINE, width=2)
        x += 18

    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=0)
    qr.add_data(qr_string)
    qr.make(fit=True)
    q = qr.make_image(fill_color="black", back_color="white").convert('RGB')

    qr_size = 490
    q = q.resize((qr_size, qr_size), Image.NEAREST if q.width <= qr_size else Image.LANCZOS)
    qx = (cw - qr_size) // 2
    qy = T + 235
    img.paste(q, (qx, qy))

    cx = qx + qr_size // 2
    cy = qy + qr_size // 2
    badge_r = 43
    d.ellipse((cx - badge_r, cy - badge_r, cx + badge_r, cy + badge_r), fill=RED_COLOR)

    f_logo = _font(22, bold=True)
    bb = d.textbbox((0, 0), "KHQR", font=f_logo)
    d.text((cx - (bb[2] - bb[0]) / 2 - bb[0], cy - (bb[3] - bb[1]) / 2 - bb[1]), "KHQR", font=f_logo, fill=(255, 255, 255))

    d.rectangle((0, 1018, cw, ch), fill=NAVY_BAR)
    f_bank = _font(24, bold=True)
    f_sub = _font(13, bold=False)
    _center(d, "BAKONG PAYMENT NETWORK", 1032, f_bank, (255, 255, 255), cx=cw // 2)
    _center(d, "NATIONAL BANK OF CAMBODIA", 1066, f_sub, SUB_TEXT, cx=cw // 2)

    bio = BytesIO()
    img.save(bio, format='PNG')
    bio.seek(0)
    return bio.getvalue()

def create_clean_qr_image(qr_string: str) -> bytes:
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=12,
        border=3,
    )
    qr.add_data(str(qr_string).strip())
    qr.make(fit=True)
    pil_img = qr.make_image(fill_color="black", back_color="white")
    if hasattr(pil_img, "get_image"):
        pil_img = pil_img.get_image()
    pil_img = pil_img.convert("RGB")
    bio = BytesIO()
    pil_img.save(bio, format="PNG")
    bio.seek(0)
    return bio.getvalue()

def create_custom_khqr(qr_string, amount, merchant_name=None):
    if not merchant_name:
        merchant_name = get_setting('aba_qr_name', 'ITACHI BOT 24 H') or 'ITACHI BOT 24 H'
        
    cw, ch = 900, 1104
    BG_COLOR = (237, 238, 243)
    NAVY_TITLE = (11, 35, 63)
    NAVY_BAR = (13, 34, 65)
    RED_COLOR = (204, 0, 25)
    DARK_TEXT = (26, 32, 44)
    GRAY_CCY = (113, 128, 150)
    DASH_LINE = (203, 213, 225)
    SUB_TEXT = (126, 147, 172)

    img = Image.new("RGB", (cw, ch), BG_COLOR)
    d = ImageDraw.Draw(img)

    # 1. Top Title: ABA' QR
    f_title = _font(56, bold=True)
    _center(d, "ABA' QR", 55, f_title, NAVY_TITLE, cx=cw // 2)

    # 2. White Card Bounds
    L, T, R, B = 110, 160, 790, 980
    radius = 22
    d.rounded_rectangle((L, T, R, B), radius=radius, fill=(255, 255, 255))

    # 3. Red Header inside card: KHQR
    hdr_h = 68
    hdr_mask = Image.new("L", (R - L, hdr_h), 0)
    hd = ImageDraw.Draw(hdr_mask)
    hd.rounded_rectangle((0, 0, R - L, hdr_h + 30), radius=radius, fill=255)
    red_hdr = Image.new("RGB", (R - L, hdr_h), RED_COLOR)
    img.paste(red_hdr, (L, T), hdr_mask)

    f_khqr = _font(32, bold=True)
    _center(d, "KHQR", T + 18, f_khqr, (255, 255, 255), cx=cw // 2)

    # 4. Merchant Name
    f_name = _font(28, bold=True)
    _center(d, str(merchant_name).upper(), T + 92, f_name, DARK_TEXT, cx=cw // 2)

    # 5. Amount & Currency
    amt_str = f"{amount:,.2f}"
    f_amt = _font(52, bold=True)
    f_ccy = _font(26, bold=False)

    aw = d.textlength(amt_str, font=f_amt)
    cw_box = d.textlength(" USD", font=f_ccy)
    total_w = aw + cw_box

    start_x = (cw - total_w) / 2
    d.text((start_x, T + 135), amt_str, font=f_amt, fill=DARK_TEXT)
    d.text((start_x + aw + 8, T + 155), "USD", font=f_ccy, fill=GRAY_CCY)

    # 6. Dashed Separator
    dash_y = T + 205
    x = L + 30
    while x < R - 30:
        d.line([(x, dash_y), (min(x + 10, R - 30), dash_y)], fill=DASH_LINE, width=2)
        x += 18

    # 7. QR Generator
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=0)
    qr.add_data(qr_string)
    qr.make(fit=True)
    q = qr.make_image(fill_color="black", back_color="white").convert('RGB')

    qr_size = 490
    q = q.resize((qr_size, qr_size), Image.NEAREST if q.width <= qr_size else Image.LANCZOS)
    qx = (cw - qr_size) // 2
    qy = T + 235
    img.paste(q, (qx, qy))

    # 8. Center Red Logo Badge with 'ABA'
    cx = qx + qr_size // 2
    cy = qy + qr_size // 2
    badge_r = 43
    d.ellipse((cx - badge_r, cy - badge_r, cx + badge_r, cy + badge_r), fill=RED_COLOR)

    f_logo = _font(24, bold=True)
    bb = d.textbbox((0, 0), "ABA", font=f_logo)
    d.text((cx - (bb[2] - bb[0]) / 2 - bb[0], cy - (bb[3] - bb[1]) / 2 - bb[1]), "ABA", font=f_logo, fill=(255, 255, 255))

    # 9. Bottom Navy Bar
    d.rectangle((0, 1018, cw, ch), fill=NAVY_BAR)
    f_bank = _font(26, bold=True)
    f_sub = _font(13, bold=False)
    _center(d, "ABA BANK", 1032, f_bank, (255, 255, 255), cx=cw // 2)
    _center(d, "NATIONAL BANK OF CANADA GROUP", 1066, f_sub, SUB_TEXT, cx=cw // 2)

    bio = BytesIO()
    img.save(bio, format='PNG')
    bio.seek(0)
    return bio.getvalue()

# ====================================================================================================
# [ API FUNCTIONS ]
# ====================================================================================================

async def aba_generate_qr_async(amount, ref_id, username="user01"):
    api_key = (os.getenv('ABA_WEBSITE_API_KEY', '') or get_setting('aba_api_key', '') or '').strip()
    merchant_id = (os.getenv('ABA_MERCHANT_ID', '') or get_setting('aba_merchant_id', '') or '').strip()
    if not api_key or not merchant_id:
        logger.error("ABA API key or merchant_id is not configured")
        return None
    payload = {
        "api_key": api_key,
        "merchant_id": merchant_id,
        "username": str(username or ref_id)[:60],
        "amount": round(float(amount), 2),
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(ABA_CREATE_URL, json=payload,
                    headers={"Content-Type": "application/json"}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json(content_type=None)
                if resp.status >= 400 or (isinstance(data, dict) and data.get("ok") is False):
                    logger.error("ABA QR API error HTTP %s: %s", resp.status, data)
                    return None
                return data
    except Exception as e:
        logger.error("ABA QR create failed: %s", e)
        return None

async def aba_check_paid_async(payment_id):
    api_key = (os.getenv('ABA_WEBSITE_API_KEY', '') or get_setting('aba_api_key', '') or '').strip()
    merchant_id = (os.getenv('ABA_MERCHANT_ID', '') or get_setting('aba_merchant_id', '') or '').strip()
    if not api_key or not merchant_id or not payment_id:
        return False
    payload = {
        "api_key": api_key,
        "merchant_id": merchant_id,
        "payment_id": str(payment_id),
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(ABA_CHECK_URL, json=payload,
                    headers={"Content-Type": "application/json"}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json(content_type=None)
                if resp.status < 400 and isinstance(data, dict):
                    status = str(data.get("status") or "").strip().upper()
                    paid_flag = data.get("paid") is True
                    if paid_flag or status in ("PAID", "SUCCESS", "COMPLETED", "APPROVED", "CONFIRMED"):
                        return True
    except Exception as e:
        logger.warning("ABA payment check failed: %s", e)
        return False
    return False

async def aba_transactions_async(status="PAID", limit=20):
    api_key = (os.getenv('ABA_WEBSITE_API_KEY', '') or get_setting('aba_api_key', '') or '').strip()
    merchant_id = (os.getenv('ABA_MERCHANT_ID', '') or get_setting('aba_merchant_id', '') or '').strip()
    if not api_key or not merchant_id:
        return []
    payload = {
        "api_key": api_key,
        "merchant_id": merchant_id,
        "status": status,
        "limit": int(limit),
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(ABA_TRANSACTIONS_URL, json=payload,
                    headers={"Content-Type": "application/json"}, timeout=20) as resp:
                data = await resp.json(content_type=None)
                if resp.status < 400 and isinstance(data, dict) and data.get("ok"):
                    return data.get("transactions") or []
    except Exception as e:
        logger.warning("ABA transactions fetch failed: %s", e)
    return []

async def resolve_aba_app_url(res: dict, payment_id: str, qr_string: str = None) -> str:
    qr_val = qr_string or (res.get("qr_string") if isinstance(res, dict) else None)
    if qr_val and str(qr_val).strip():
        encoded_qr = urllib.parse.quote(str(qr_val).strip(), safe="")
        return f"https://dpayment-epreprod.ababank.com/deep-link?type=payway&qrcode={encoded_qr}"
    pay_url = res.get("pay_url") if isinstance(res, dict) else None
    if pay_url and str(pay_url).startswith("http"):
        return str(pay_url).strip()
    if payment_id:
        return f"https://khmer-system.com/aba/pay/{urllib.parse.quote(str(payment_id).strip(), safe='')}"
    return "https://khmer-system.com"

async def aba_mark_credited_async(payment_id):
    api_key = (os.getenv('ABA_WEBSITE_API_KEY', '') or get_setting('aba_api_key', '') or '').strip()
    merchant_id = (os.getenv('ABA_MERCHANT_ID', '') or get_setting('aba_merchant_id', '') or '').strip()
    if not api_key or not merchant_id or not payment_id:
        return False
    payload = {
        "api_key": api_key,
        "merchant_id": merchant_id,
        "payment_id": str(payment_id),
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(ABA_MARK_CREDITED_URL, json=payload,
                    headers={"Content-Type": "application/json"}, timeout=15) as resp:
                data = await resp.json(content_type=None)
                return bool(resp.status < 400 and isinstance(data, dict) and data.get("ok"))
    except Exception as e:
        logger.warning("ABA mark-credited failed: %s", e)
    return False

# --- KHQRPAY.SITE ABA API MODULE ---

async def khqrpay_create_aba_async(amount: float) -> dict | None:
    api_key = (os.getenv('KHQRPAY_API_KEY', '') or get_setting('khqrpay_api_key', '') or '').strip()
    if not api_key:
        logger.error("khqrpay.site API key is not configured")
        return None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {"amount": round(float(amount), 2)}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
            async with session.post(KHQRPAY_ABA_CREATE_URL, json=payload, headers=headers) as resp:
                data = await resp.json(content_type=None)
                if resp.status < 400 and isinstance(data, dict) and data.get("ok"):
                    return data
                logger.error("khqrpay.site ABA create error HTTP %s: %s", resp.status, data)
    except Exception as e:
        logger.error("khqrpay.site ABA create failed: %s", e)
    return None

def _khqrpay_is_paid_obj(obj) -> bool:
    if not isinstance(obj, dict):
        return False
    for candidate in (obj, obj.get("payment"), obj.get("data"), obj.get("result")):
        if not isinstance(candidate, dict):
            continue
        if candidate.get("paid") is True or candidate.get("is_paid") is True:
            return True
        st = str(candidate.get("status") or candidate.get("payment_status") or "").strip().lower()
        if st in ("paid", "success", "successful", "completed", "approved", "confirmed", "settled"):
            return True
    return False

async def _khqrpay_check_by_id(api_key: str, payment_id: str) -> bool:
    if not api_key or not payment_id:
        return False
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    pid_str = str(payment_id).strip()
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as session:
            # 1. Check /api/v1/payment?id=...
            async with session.get(f"{KHQRPAY_CHECK_URL}?id={urllib.parse.quote(pid_str, safe='')}", headers=headers) as resp:
                if resp.status < 400:
                    data = await resp.json(content_type=None)
                    if _khqrpay_is_paid_obj(data):
                        return True
            # 2. Fallback: check /api/v1/payments?limit=20
            async with session.get(f"{KHQRPAY_PAYMENTS_URL}?limit=20", headers=headers) as resp2:
                if resp2.status < 400:
                    data2 = await resp2.json(content_type=None)
                    if isinstance(data2, dict):
                        items = data2.get("payments") or data2.get("data") or data2.get("items") or []
                        if isinstance(items, list):
                            for it in items:
                                if not isinstance(it, dict):
                                    continue
                                it_id = str(it.get("id") or it.get("payment_id") or "").strip()
                                if it_id == pid_str and _khqrpay_is_paid_obj(it):
                                    return True
    except Exception as e:
        logger.warning("khqrpay.site check payment failed: %s", e)
    return False

async def khqrpay_check_paid_async(payment_id) -> bool:
    api_key = (
        os.getenv('KHQRPAY_API_KEY', '')
        or get_setting('khqrpay_api_key', '')
        or get_setting('bakong_api_key', '')
        or ''
    ).strip()
    return await _khqrpay_check_by_id(api_key, str(payment_id or ""))

async def khqrpay_list_payments_async(limit: int = 20) -> list:
    api_key = (os.getenv('KHQRPAY_API_KEY', '') or get_setting('khqrpay_api_key', '') or '').strip()
    if not api_key:
        return []
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.get(f"{KHQRPAY_PAYMENTS_URL}?limit={int(limit)}", headers=headers) as resp:
                if resp.status < 400:
                    data = await resp.json(content_type=None)
                    if isinstance(data, dict) and data.get("ok"):
                        return data.get("payments") or data.get("data") or []
    except Exception as e:
        logger.warning("khqrpay.site list payments failed: %s", e)
    return []

# --- BAKONG CLIENT MODULE (KHQRPAY.SITE API) ---

def _get_bakong_api_key() -> str:
    bkg_key = (get_setting('bakong_api_key', '') or get_setting('bakong_token', '') or '').strip()
    khqr_key = (get_setting('khqrpay_api_key', '') or os.getenv('KHQRPAY_API_KEY', '') or '').strip()
    # Ignore legacy CamRapidPay key if khqrpay sk_ key is configured
    if bkg_key == CAMRAPID_API_KEY_DEFAULT and khqr_key:
        return khqr_key
    if bkg_key and not bkg_key.startswith("sk_") and khqr_key.startswith("sk_"):
        return khqr_key
    return (bkg_key or khqr_key or os.getenv('BAKONG_TOKEN', '') or '').strip()

async def bakong_fetch_api_qr(amount: float, ref_id: str) -> dict | None:
    """
    Create Bakong KHQR payment via khqrpay.site API:
    POST https://khqrpay.site/api/v1/bakong/create
    """
    api_key = _get_bakong_api_key()
    if not api_key:
        logger.error("Bakong khqrpay.site API key is not configured")
        return None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {"amount": round(float(amount), 2)}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.post(KHQRPAY_BAKONG_CREATE_URL, json=payload, headers=headers) as resp:
                data = await resp.json(content_type=None)
                if resp.status < 400 and isinstance(data, dict) and data.get("ok"):
                    qr_str = data.get("qr") or data.get("qr_string")
                    pid = data.get("id") or data.get("payment_id") or str(ref_id)
                    if qr_str:
                        return {
                            "qr_string": qr_str,
                            "transaction_id": str(pid),
                            "checkout_url": data.get("checkout_url"),
                            "merchant_name": data.get("merchant_name"),
                            "md5": data.get("md5"),
                            "amount": data.get("amount"),
                        }
                logger.error("khqrpay.site Bakong create error HTTP %s: %s", resp.status, data)
    except Exception as e:
        logger.error("khqrpay.site Bakong create failed: %s", e)
    return None

async def check_bakong_payment_status(payment_id: str) -> str:
    """
    Check Bakong payment status via khqrpay.site API:
    GET https://khqrpay.site/api/v1/payment?id=... (and /api/v1/payments fallback)
    Returns 'PAID' or 'UNPAID'
    """
    api_key = _get_bakong_api_key()
    if await _khqrpay_check_by_id(api_key, str(payment_id or "")):
        return "PAID"
    return "UNPAID"

async def bakong_check_paid_async(payment_id):
    if not payment_id:
        return False
    return (await check_bakong_payment_status(str(payment_id))) == "PAID"

# ====================================================================================================
# [ FSM STATES ]
# ====================================================================================================

class OrderFSM(StatesGroup): custom_qty = State()
class AdminAddCat(StatesGroup): name = State(); icon = State()
class AdminAddItem(StatesGroup): cat_id = State(); name = State(); price = State(); reseller_price = State(); reseller_vip_price = State(); icon = State()
class AdminAddStock(StatesGroup): item_id = State(); keys = State()
class AdminBroadcast(StatesGroup): msg = State()
class AdminReseller(StatesGroup): add_id = State(); add_admin = State(); del_id = State(); add_vip_id = State(); del_vip_id = State()
class AdminChannel(StatesGroup): channel_id = State()
class AdminStartMedia(StatesGroup): media = State()
class AdminCatMedia(StatesGroup): cat_id = State(); media = State()
class AdminCatDesc(StatesGroup): text = State()
class AdminRenameCat(StatesGroup): name = State(); icon = State()
class AdminRenameItem(StatesGroup): name = State(); icon = State()
class AdminAddInfinite(StatesGroup): data = State()
class AdminPostMedia(StatesGroup): item_id = State(); media = State()
class AdminEditPrice(StatesGroup): new_price = State()
class AdminABA(StatesGroup): api_key = State(); merchant_id = State(); qr_name = State()
class AdminKhqrPay(StatesGroup): api_key = State()
class AdminBakong(StatesGroup): api_key = State(); username_id = State(); api_base = State()
class AdminManualQR(StatesGroup): photo = State()
class UserWaitReceipt(StatesGroup): receipt = State()
class AdminClone(StatesGroup): token = State(); owner_id = State()
class AdminContentSetting(StatesGroup): start_text = State(); help_media = State(); contact_url = State()
class AdminSetupEmoji(StatesGroup): emoji = State()
class UserChatAdmin(StatesGroup): message = State()
class AdminReplyChat(StatesGroup): reply_msg = State()
class AdminEmojiMap(StatesGroup):
    waiting_input = State()
class AdminBinance(StatesGroup):
    pay_id = State()
    binance_id = State()
    api_key = State()
    api_secret = State()
class UserBinanceOrder(StatesGroup):
    order_id = State()
class AdminApiAddGame(StatesGroup):
    game_name = State()
    stock_qty = State()
    icon = State()
class AdminSetProfit(StatesGroup):
    amount = State()
class AdminChangeApi(StatesGroup):
    api_url = State()
    api_token = State()
class AdminResellerPkgPrice(StatesGroup):
    reseller_price = State()
    vip_price = State()
class AdminAddStockAuto(StatesGroup):
    qty = State()
class AdminApiDeposit(StatesGroup):
    amount = State()

# ====================================================================================================
# [ 🌐 RESELLER API CLIENT (ASYNC) ]
# ====================================================================================================

class ResellerApiError(Exception):
    def __init__(self, code, message):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message

class ResellerAPIAsync:
    def __init__(self, base_url=None, token=None):
        self.base_url = (base_url or get_setting('reseller_api_url', 'https://reseller.panelkey.shop/api/v1/reseller') or 'https://reseller.panelkey.shop/api/v1/reseller').strip().rstrip('/')
        self.token = (token or get_setting('reseller_api_token', 'pk_e4d53cb2d92afba51cbb896ff40f882706afdc5e064dd243') or '').strip()

    def _call_sync(self, method, path, body=None):
        import urllib.request
        import urllib.error
        url = self.base_url + path
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "reseller-client/1.0"
        }
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")

        # 1. Try curl_cffi (best Cloudflare TLS impersonation if installed)
        try:
            from curl_cffi import requests as cffi_req
            r = cffi_req.request(method, url, headers=headers, json=body, impersonate="chrome120", timeout=45)
            try:
                ans = r.json()
                if not ans.get("ok"):
                    err = ans.get("error") or {}
                    raise ResellerApiError(err.get("code", "ERROR"), err.get("message", "Unknown API Error"))
                return ans.get("data")
            except ValueError:
                if r.status_code != 403:
                    raise ResellerApiError(f"HTTP_{r.status_code}", r.text[:200])
        except ImportError:
            pass
        except ResellerApiError:
            raise
        except Exception:
            pass

        # 2. Try cloudscraper (if installed)
        try:
            import cloudscraper
            scraper = cloudscraper.create_scraper()
            r = scraper.request(method, url, headers=headers, json=body, timeout=45)
            try:
                ans = r.json()
                if not ans.get("ok"):
                    err = ans.get("error") or {}
                    raise ResellerApiError(err.get("code", "ERROR"), err.get("message", "Unknown API Error"))
                return ans.get("data")
            except ValueError:
                if r.status_code != 403:
                    raise ResellerApiError(f"HTTP_{r.status_code}", r.text[:200])
        except ImportError:
            pass
        except ResellerApiError:
            raise
        except Exception:
            pass

        # 3. Standard urllib.request (matches main.py reseller_client.py)
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
                answer = json.loads(raw)
        except urllib.error.HTTPError as error:
            raw = error.read().decode("utf-8", "replace")
            try:
                answer = json.loads(raw)
            except ValueError:
                raise ResellerApiError(f"HTTP_{error.code}", raw[:200])
        if not answer.get("ok"):
            err = answer.get("error") or {}
            raise ResellerApiError(err.get("code", "ERROR"), err.get("message", "Unknown API Error"))
        return answer.get("data")

    async def _call(self, method, path, body=None):
        return await asyncio.to_thread(self._call_sync, method, path, body)

    async def ping(self):
        return await self._call("GET", "/ping")

    async def me(self):
        return await self._call("GET", "/me")

    async def balance(self):
        return await self._call("GET", "/balance")

    async def catalog(self):
        return await self._call("GET", "/catalog")

    async def generate(self, package_id, quantity=1, reference=None):
        body = {"package_id": int(package_id), "quantity": int(quantity)}
        if reference:
            body["reference"] = str(reference)
        return await self._call("POST", "/generate", body)

    async def history(self, page=1, limit=20):
        return await self._call("GET", f"/history?page={page}&limit={limit}")

    async def order(self, order_number):
        return await self._call("GET", "/orders/" + urllib.parse.quote(str(order_number), safe=""))

# ====================================================================================================
# [ ផ្នែក ADMIN - គ្រប់គ្រងទូទៅ ]
# ====================================================================================================

async def render_admin_panel(event, allow_all=True):
    owner_id = get_current_owner()
    uid = event.from_user.id
    execute_db('INSERT OR IGNORE INTO users (id, is_admin) VALUES (?, 0)', (uid,))
    
    admin_defs = {
        "content_setting": ("Bot Content setting", "adm_content_setting", "primary", "6138899547625102613"),
        "manage_products": ("គ្រុបគ្រងផលលិតផល", "adm_manage_products", "primary", "5312361253610475399"),
        "stock_hub": ("គ្រុបគ្រង (add stock / views Stock )", "adm_stock_hub", "success", "5447479640547428304"),
        "broadcast": ("Broadcast", "adm_broadcast", "primary", "5260268501515377807"),
        "reseller": ("គ្រប់គ្រង់ ( Reseller )", "adm_reseller", "primary", "6136265963873511020"),
        "settings": ("Setting", "adm_settings", "primary", "6151986639393531426"),
        "channel": ("កំណត់ Group/Chanel វិក្កយប័ត្រ", "adm_channel", "primary", "5445221832074483553"),
        "prem_emoji": ("Premium emoji Setting", "adm_emoji", "primary", "6314076231243404806")
    }
    
    rows = []
    raw_l = get_setting("org_layout_admin")
    raw_s = get_setting("org_styles_admin")
    if raw_l:
        try:
            c_layout = json.loads(raw_l)
            c_styles = json.loads(raw_s) if raw_s else {}
            for r in c_layout:
                row_btns = []
                for k in r:
                    if k in admin_defs:
                        txt, cb, def_st, icon_id = admin_defs[k]
                        st = c_styles.get(k, def_st)
                        row_btns.append(IBtn(text=txt, callback_data=cb, style=st, icon_custom_emoji_id=icon_id, btn_key=k))
                if row_btns: rows.append(row_btns)
            placed_keys = {k for row in c_layout for k in row}
            for k in ["stock_hub", "prem_emoji"]:
                if k in admin_defs and k not in placed_keys:
                    txt, cb, def_st, icon_id = admin_defs[k]
                    rows.append([IBtn(text=txt, callback_data=cb, style=def_st, icon_custom_emoji_id=icon_id, btn_key=k)])
        except:
            rows = []

    if not rows:
        rows = [
            [IBtn(text="Bot Content setting", callback_data="adm_content_setting", style="primary", icon_custom_emoji_id="6138899547625102613", btn_key="content_setting")],
            [IBtn(text="គ្រុបគ្រងផលលិតផល", callback_data="adm_manage_products", style="primary", icon_custom_emoji_id="5312361253610475399", btn_key="manage_products")],
            [IBtn(text="គ្រុបគ្រង (add stock / views Stock )", callback_data="adm_stock_hub", style="success", icon_custom_emoji_id="5447479640547428304", btn_key="stock_hub")],
            [IBtn(text="Broadcast", callback_data="adm_broadcast", style="primary", icon_custom_emoji_id="5260268501515377807", btn_key="broadcast")],
            [IBtn(text="គ្រប់គ្រង់ ( Reseller )", callback_data="adm_reseller", style="primary", icon_custom_emoji_id="6136265963873511020", btn_key="reseller")],
            [IBtn(text="Setting", callback_data="adm_settings", style="primary", icon_custom_emoji_id="6151986639393531426", btn_key="settings")],
            [IBtn(text="កំណត់ Group/Chanel វិក្កយប័ត្រ", callback_data="adm_channel", style="primary", icon_custom_emoji_id="5445221832074483553", btn_key="channel")],
            [IBtn(text="Premium emoji Setting", callback_data="adm_emoji", style="primary", icon_custom_emoji_id="6314076231243404806", btn_key="prem_emoji")]
        ]
    
    if not is_clone_bot() and event.from_user.id == OWNER_ID:
        rows.append([IBtn(text="Clone Bot", callback_data="adm_clone_bot", style="primary", icon_custom_emoji_id="5364125616801073577")])
        
    rows.append([
        IBtn(text="ត្រលប់ទៅបូតុងភ្ញៀវ", callback_data="back_to_start", style="danger", icon_custom_emoji_id="5253997076169115797")
    ])
    
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    text = "<tg-emoji emoji-id=\"5890864241388293875\">⚙️</tg-emoji> <b>ផ្ទាំងគ្របគ្រង់អេតមីនឆ្លាតវ័យ</b>\nសូមជ្រើសរើសមុខងារខាងក្រោម៖"
    rendered_text = render_clean_text(text)
    
    if isinstance(event, CallbackQuery):
        try: await event.message.edit_text(rendered_text, reply_markup=kb)
        except Exception:
            try: await event.message.answer(rendered_text, reply_markup=kb)
            except Exception:
                plain = re.sub(r'<[^>]+>', '', rendered_text)
                await event.message.answer(plain, reply_markup=kb, parse_mode=None)
    else:
        try: await event.answer(rendered_text, reply_markup=kb)
        except Exception:
            plain = re.sub(r'<[^>]+>', '', rendered_text)
            try: await event.answer(plain, reply_markup=kb, parse_mode=None)
            except Exception: pass

@dp.message(Command("admin"), StateFilter("*"))
@dp.message(StateFilter("*"), F.text.contains("ADMIN PANEL") | F.text.contains("admin panel") | F.text.contains("អ្នកកាន់បត") | F.text.contains("Admin"))
async def open_admin(msg: Message, state: FSMContext):
    await state.clear()
    uid = msg.from_user.id
    execute_db('INSERT OR IGNORE INTO users (id, is_admin) VALUES (?, 0)', (uid,))
    await render_admin_panel(msg, allow_all=True)
@dp.callback_query(F.data == "admin_panel")
@dp.callback_query(F.data == "back_admin")
async def back_to_admin(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer()
    await render_admin_panel(call)

# ====================================================================================================
# [ ផ្នែក ADMIN - BOT CONTENT SETTING ]
# ====================================================================================================

# ====================================================================================================
# [ ផ្នែក ADMIN - SETUP EMOJI PREMIUM & DEL START MEDIA ]
# ====================================================================================================

@dp.callback_query(F.data == "adm_del_start_media")
async def adm_del_start_media_handler(call: CallbackQuery):
    execute_db('DELETE FROM settings WHERE key="start_media"')
    await call.answer("✅ បានដក វីដេអូ/រូបភាព /start រួចរាល់!", show_alert=True)
    await render_admin_panel(call)

# ====================================================================================================
# [ 👑 PREMIUM EMOJI SETTINGS & MAPPING (SMM ARCHITECTURE) ]
# ====================================================================================================

# [Emoji lists and mappings defined at top of file]
def load_emoji_char_map() -> dict:
    raw = get_setting("emoji_char_map", "")
    data = {}
    if raw:
        try:
            data = json.loads(raw)
        except Exception:
            pass
    for _, char, eid in ALL_BOT_BTN_EMOJIS + ALL_BOT_MSG_EMOJIS:
        if char not in data:
            data[char] = eid
    return data

def save_emoji_char_map(m: dict):
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('emoji_char_map', json.dumps(m, ensure_ascii=False)))

@dp.callback_query(F.data == "adm_emoji")
async def adm_emoji_settings_handler(call: CallbackQuery):
    try: await call.answer()
    except Exception: pass
    
    mapping = load_emoji_char_map()
    mode = get_setting("emoji_mode", "premium")
    
    lines = [
        "👑 ការកំណត់ផែនទីសញ្ញាអារម្មណ៍ពិសេស",
        "─────────────────────",
        "",
        "ម៉ឺនុយនេះអនុញ្ញាតឱ្យអ្នកភ្ជាប់សញ្ញាអារម្មណ៍/តួអក្សរធម្មតាទៅនឹងលេខសម្គាល់សញ្ញាអារម្មណ៍ Telegram Premium/ផ្ទាល់ខ្លួន។",
        "",
        "• Emoji ➔ ID Emoji",
        "",
        "• Current Mappings:",
        "",
        "⁃ សម្រាប់ Button ទាំងអស់"
    ]
    seen_btn = set()
    for _, ch, def_id in ALL_BOT_BTN_EMOJIS:
        if ch in seen_btn: continue
        seen_btn.add(ch)
        eid = mapping.get(ch) or def_id
        lines.append(f"• {ch} ➔ {eid}")
        
    lines.append("")
    lines.append("⁃ សម្រាប់សារទាំងអស់")
    seen_msg = set()
    for _, ch, def_id in ALL_BOT_MSG_EMOJIS:
        if ch in seen_msg: continue
        seen_msg.add(ch)
        eid = mapping.get(ch) or def_id
        lines.append(f"• {ch} ➔ {eid}")
        
    body = "\n".join(lines)
    if len(body) > 3900:
        body = body[:3900] + "\n…"
        
    toggle_label = "Switch to Normal Account" if mode == "premium" else "Switch to Premium Account"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="Add / Edit Mapping ( បន្ថែម / កែប្រែ )", callback_data="adm_emoji_edit", style="success", icon_custom_emoji_id="6033108614724456536")],
        [IBtn(text="Delete Mapping ( លុប )", callback_data="adm_emoji_del", style="danger", icon_custom_emoji_id="6176808917549453468")],
        [IBtn(text=toggle_label, callback_data="adm_toggle_emoji", style="primary", icon_custom_emoji_id="6068828835523073231")],
        [IBtn(text="Back", callback_data="admin_panel", style="danger", icon_custom_emoji_id="6035130900075777681")]
    ])
    try:
        await call.message.edit_text(body, reply_markup=kb, parse_mode=None)
    except Exception as e:
        logger.warning(f"Failed to edit_text in emoji settings: {e}")
        try:
            await call.message.answer(body, reply_markup=kb, parse_mode=None)
        except Exception:
            pass

@dp.callback_query(F.data == "adm_toggle_emoji")
async def adm_toggle_emoji_handler(call: CallbackQuery, bot: Bot):
    curr = get_setting("emoji_mode", "premium")
    new_mode = "normal" if curr == "premium" else "premium"
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('emoji_mode', new_mode))
    if new_mode == "premium":
        msg = "⭐️ Premium Account ON\nButtons and messages use Premium custom emoji icons."
    else:
        msg = "🥰 Normal Account ON\nButtons and messages use normal unicode emoji only."
    try: await call.answer(msg, show_alert=True)
    except: pass
    
    try:
        await bot.send_message(
            call.message.chat.id,
            f"🔄 <b>ប្ដូររបៀប Emoji ជោគជ័យ៖</b> {('⭐️ Premium Account' if new_mode == 'premium' else '🥰 Normal Account')}"
        )
    except Exception as e:
        logger.warning(f"Could not notify emoji toggle: {e}")
        
    await adm_emoji_settings_handler(call)

@dp.callback_query(F.data == "adm_emoji_edit")
async def adm_emoji_edit_prompt(call: CallbackQuery, state: FSMContext):
    await call.answer()
    prompt = """✍️ <b>សូមបញ្ចូល Emoji + Custom Emoji ID</b>
(អាចផ្ញើច្រើនជួរក្នុងមួយសារ)

👉 មួយ:
👾 5433696429069580735

👉 ច្រើន:
👤 5818715087237549366
💰 6311835757258478003

ឬផ្ញើ Premium emoji ផ្ទាល់ពី Telegram"""
    await call.message.edit_text(render_clean_text(prompt), reply_markup=cancel_inline())
    await state.set_state(AdminEmojiMap.waiting_input)

@dp.message(AdminEmojiMap.waiting_input)
async def process_emoji_mapping_input(msg: Message, state: FSMContext):
    mapping = load_emoji_char_map()
    added_count = 0
    
    if msg.entities:
        for ent in msg.entities:
            if ent.type == "custom_emoji" and ent.custom_emoji_id:
                char = msg.text[ent.offset : ent.offset + ent.length]
                mapping[char] = str(ent.custom_emoji_id)
                added_count += 1
                
    if msg.text:
        for line in msg.text.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = re.split(r'[\s:➔\->]+', line)
            if len(parts) >= 2:
                char = parts[0].strip()
                eid = parts[1].strip()
                if eid.isdigit() and len(eid) > 6:
                    mapping[char] = eid
                    added_count += 1
                    
    save_emoji_char_map(mapping)
    await state.clear()
    await msg.answer(f"✅ បានបន្ថែម/កែប្រែចំនួន <b>{added_count}</b> Emoji Mapping ជោគជ័យ!", reply_markup=admin_back_inline("adm_emoji"))

@dp.callback_query(F.data == "adm_emoji_del")
async def adm_emoji_del_handler(call: CallbackQuery):
    await call.answer()
    mapping = load_emoji_char_map()
    rows = []
    for e, eid in list(mapping.items())[:30]:
        rows.append([IBtn(text=f"❌ {e} ➔ {eid}", callback_data=f"adm_emojirm_{e}", style="danger")])
    if not rows:
        rows.append([IBtn(text="📭 គ្មាន Mappings ទេ", callback_data="adm_emoji", style="primary")])
    rows.append([IBtn(text="Back", callback_data="adm_emoji", style="danger", icon_custom_emoji_id="6035130900075777681")])
    
    await call.message.edit_text("❌ <b>Delete Mapping</b>\n\nសូមចុចលើ Emoji ដែលចង់លុបចេញភ្លាមៗ៖", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@dp.callback_query(F.data.startswith("adm_emojirm_"))
async def adm_emoji_rm_item_handler(call: CallbackQuery):
    target = call.data.replace("adm_emojirm_", "")
    mapping = load_emoji_char_map()
    if target in mapping:
        del mapping[target]
        save_emoji_char_map(mapping)
        await call.answer(f"✅ បានលុប {target} រួចរាល់!", show_alert=True)
    else:
        await call.answer("រកមិនឃើញ", show_alert=True)
    await adm_emoji_del_handler(call)


@dp.callback_query(F.data == "adm_content_setting")
async def adm_content_setting_handler(call: CallbackQuery):
    try: await call.answer()
    except: pass
    curr_msg = get_setting('start_text', DEFAULT_START_TEXT)
    text = f"""<tg-emoji emoji-id="6138899547625102613">📝</tg-emoji> <b>Bot Content Setting ៖</b>
——————————————————————-
<tg-emoji emoji-id="6138589833238422233">💬</tg-emoji> <b>អក្សរ Welcome បច្ចុប្បន្ន៖</b>
{curr_msg}
——————————————————————-"""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="Edit Welcome", callback_data="adm_edit_start_text", style="primary", icon_custom_emoji_id="5445373981290952548")],
        [IBtn(text="Upload Video / Photo / GIFs", callback_data="adm_set_start_media", style="primary", icon_custom_emoji_id="5445373981290952548")],
        [IBtn(text="Del Video / Photo / GiFs", callback_data="adm_del_start_media", style="danger", icon_custom_emoji_id="5445373981290952548")],
        [IBtn(text="Back", callback_data="admin_panel", style="danger", icon_custom_emoji_id="6035130900075777681")]
    ])
    try: await call.message.edit_text(render_clean_text(text), reply_markup=kb)
    except: await call.message.answer(render_clean_text(text), reply_markup=kb)

@dp.callback_query(F.data == "adm_set_start_media")
async def adm_set_start_media_handler(call: CallbackQuery, state: FSMContext):
    try: await call.answer()
    except: pass
    await call.message.edit_text("🎬 <b>សូមផ្ញើ វីដេអូ (Video), រូបភាព (Photo), ឬ GIF សម្រាប់បង្ហាញលើសារ /start មកទីនេះ៖</b>", reply_markup=cancel_inline())
    await state.set_state(AdminStartMedia.media)

@dp.message(AdminStartMedia.media)
async def save_start_media_handler(msg: Message, state: FSMContext):
    if msg.video:
        val = f"video:{msg.video.file_id}"
    elif msg.photo:
        val = f"photo:{msg.photo[-1].file_id}"
    elif msg.animation:
        val = f"animation:{msg.animation.file_id}"
    elif msg.document:
        val = f"animation:{msg.document.file_id}"
    else:
        return await msg.answer("❌ សូមផ្ញើជា វីដេអូ រូបភាព ឬ GIF!", reply_markup=cancel_inline())
        
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('start_media', val))
    await msg.answer("✅ បានដាក់ Video / Photo / GIFs សម្រាប់ /start ជោគជ័យ!", reply_markup=admin_back_inline("adm_content_setting"))
    await state.clear()

@dp.callback_query(F.data == "adm_del_start_media")
async def adm_del_start_media_handler(call: CallbackQuery):
    execute_db('DELETE FROM settings WHERE key="start_media"')
    try: await call.answer("✅ បានដក Video / Photo / GIFs (/start) រួចរាល់!", show_alert=True)
    except: pass
    await adm_content_setting_handler(call)

@dp.callback_query(F.data == "adm_edit_contact_url")
async def adm_edit_contact_url_prompt(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("✏️ សូមវាយបញ្ចូល Link Telegram ថ្មីសម្រាប់ទាក់ទង Admin (ឧទាហរណ៍: https://t.me/Vbenstore168) ៖", reply_markup=cancel_inline())
    await state.set_state(AdminContentSetting.contact_url)
    await call.answer()

@dp.message(AdminContentSetting.contact_url)
async def save_contact_url_handler(msg: Message, state: FSMContext):
    url = msg.text.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://{url}"
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('contact_admin_url', url))
    await msg.answer(f"✅ បានកែប្រែ Link Contact Admin ទៅជា: <b>{url}</b> ជោគជ័យ!")
    await state.clear()

@dp.callback_query(F.data == "adm_edit_start_text")
async def adm_edit_start_text_prompt(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("✏️ សូមវាយបញ្ចូលសារជូនដំណឹងថ្មីសម្រាប់ពេលចុច /start ៖", reply_markup=cancel_inline())
    await state.set_state(AdminContentSetting.start_text)
    await call.answer()

@dp.message(AdminContentSetting.start_text)
async def save_start_text(msg: Message, state: FSMContext):
    new_text = msg.html_text if msg.html_text else msg.text
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('start_text', new_text))
    await msg.answer("✅ បានកែសារជូនដំណឹងជោគជ័យ!")
    await state.clear()

# ====================================================================================================
# [ ផ្នែក ADMIN - មើលស្តុក ( VIEWS STOCK ) & Manage Stock & Clone Bot & Others ... ]
# ====================================================================================================

@dp.callback_query(F.data == "adm_set_help_media")
async def adm_set_help_media_handler(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("✏️ សូមផ្ញើ វីដេអូ / រូបភាព / ឬអត្ថបទ សម្រាប់បង្ហាញពេល User ចុច /help ៖", reply_markup=cancel_inline())
    await state.set_state(AdminContentSetting.help_media)
    await call.answer()

@dp.message(AdminContentSetting.help_media)
async def save_help_media_handler(msg: Message, state: FSMContext):
    cap = msg.html_text if (msg.caption or msg.text) else ""
    if msg.video:
        val = f"video:{msg.video.file_id}:{cap}"
    elif msg.photo:
        val = f"photo:{msg.photo[-1].file_id}:{cap}"
    elif msg.text:
        val = f"text:{msg.html_text}"
    else:
        return await msg.answer("❌ សូមផ្ញើជា វីដេអូ រូបភាព ឬ អត្ថបទ!", reply_markup=cancel_inline())

    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('help_media', val))
    await msg.answer("✅ បានដាក់ វីដេអូ/រូបភាព/អត្ថបទ សម្រាប់ /help ជោគជ័យ!")
    await state.clear()

@dp.callback_query(F.data == "adm_del_help_media")
async def adm_del_help_media_handler(call: CallbackQuery):
    execute_db('DELETE FROM settings WHERE key="help_media"')
    await call.answer("✅ បានដក វីដេអូ/រូបភាព/អត្ថបទ (/help) រួចរាល់!", show_alert=True)
    await adm_content_setting_handler(call)

@dp.callback_query(F.data == "adm_stock_hub")
async def adm_stock_hub_handler(call: CallbackQuery):
    try: await call.answer()
    except Exception: pass
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="Add Stock / ដោយដៃ", callback_data="adm_manage_stock", style="success", icon_custom_emoji_id="5444908424015934570")],
        [IBtn(text="មើលស្តុក", callback_data="adm_view_stock", style="primary", icon_custom_emoji_id="5447607759421863856")],
        [IBtn(text="Back", callback_data="back_admin", style="danger", icon_custom_emoji_id="6035130900075777681")]
    ])
    await call.message.edit_text(
        "<tg-emoji emoji-id=\"5447479640547428304\">📦</tg-emoji> <b>គ្រុបគ្រង (add stock / views Stock )</b>\nសូមជ្រើសរើសមុខងារខាងក្រោម៖",
        reply_markup=kb
    )

@dp.callback_query(F.data == "adm_view_stock")
async def adm_view_stock_handler(call: CallbackQuery):
    try: await call.answer()
    except Exception: pass
    cats = execute_db('SELECT id, name, icon FROM categories', fetchall=True)
    if not cats: return await call.answer("មិនមានទិន្នន័យទេ!", show_alert=True)
    kb = [[IBtn(text=c[1], callback_data=f"vstk_cat_{c[0]}", style="primary", icon_custom_emoji_id=c[2])] for c in cats]
    kb.append([IBtn(text="Back", callback_data="adm_stock_hub", style="danger", icon_custom_emoji_id="6035130900075777681")])
    text = "<tg-emoji emoji-id=\"6143084439204275121\">📊</tg-emoji>មើលស្តុកផលលិតផល \nជ្រើសរើស tier ដើម្បីមើល Keyលម្អិត៖"
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data.startswith("vstk_cat_"))
async def vstk_cat_handler(call: CallbackQuery):
    cat_id = int(call.data.split("_")[2])
    items = execute_db('SELECT id, name, icon FROM items WHERE cat_id=?', (cat_id,), fetchall=True)
    kb = []
    for i in items:
        stk = execute_db('SELECT COUNT(*) FROM stock WHERE item_id=? AND is_sold=0', (i[0],), fetch=True)[0]
        kb.append([IBtn(text=f"{i[1]} ({stk})", callback_data=f"vstk_itm_{i[0]}", style="primary", icon_custom_emoji_id=i[2])])
    kb.append([IBtn(text="Back", callback_data="adm_view_stock", style="danger", icon_custom_emoji_id="6035130900075777681")])
    await call.message.edit_text("ជ្រើសរើសទំនិញដើម្បីមើល Key លម្អិត៖", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data.startswith("vstk_itm_"))
async def vstk_itm_handler(call: CallbackQuery):
    item_id = int(call.data.split("_")[2])
    item_info = execute_db('SELECT name, post_media FROM items WHERE id=?', (item_id,), fetch=True)
    item_name = item_info[0] if item_info else "ទំនិញ"
    post_media = item_info[1] if item_info else None
    
    keys = execute_db('SELECT key_data, type FROM stock WHERE item_id=? AND is_sold=0', (item_id,), fetchall=True)
    
    if not keys and not post_media:
        await call.answer("អស់ស្តុកហើយ និងមិនទាន់មាន Media ទេ!", show_alert=True)
        return
        
    text = f"📦 <b>ព័ត៌មានស្តុក៖ {item_name}</b>\n\n"
    if keys:
        text += f"🔑 <b>Key ដែលមានក្នុងស្តុក ({len(keys)}):</b>\n"
        for k in keys:
            if k[1] == 'text': text += f"• <code>{k[0]}</code>\n"
            else: text += f"• [File/Media] {k[0].split(':')[0]}\n"
    else:
        text += "⚠️ <i>មិនមាន Key (Text) ក្នុងស្តុកទេ</i>\n"
        
    if post_media:
        text += "\n📂 <b>File/Media ពេលទិញរួច៖</b> មានកំណត់ (កំពុងផ្ញើជូនខាងក្រោម)"
        
    if len(text) > 4000: text = text[:4000] + "\n... (ច្រើនពេក)"
    kb = InlineKeyboardMarkup(inline_keyboard=[[IBtn(text="Back", callback_data="adm_view_stock", style="danger", icon_custom_emoji_id="6035130900075777681")]])
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except: pass
    
    # ផ្ញើ File/Media ពេលទិញរួច (post_media) មកបង្ហាញជូន
    if post_media:
        media_list = []
        try:
            loaded = json.loads(post_media)
            if isinstance(loaded, list): media_list = loaded
            elif isinstance(loaded, dict): media_list = [loaded]
        except:
            if ':' in post_media:
                m_type, content = post_media.split(':', 1)
                media_list = [{'type': m_type, 'content': content, 'caption': None}]
                
        for pm in media_list:
            m_type, content, cap = pm.get('type'), pm.get('content'), pm.get('caption') or None
            pm_cap = f"📁 [File/Media ពេលទិញរួច - {item_name}]\n{cap}" if cap else f"📁 [File/Media ពេលទិញរួច - {item_name}]"
            try:
                if m_type == 'photo': await call.bot.send_photo(call.message.chat.id, content, caption=pm_cap)
                elif m_type == 'video': await call.bot.send_video(call.message.chat.id, content, caption=pm_cap)
                elif m_type == 'document': await call.bot.send_document(call.message.chat.id, content, caption=pm_cap)
                elif m_type == 'audio': await call.bot.send_audio(call.message.chat.id, content, caption=pm_cap)
                elif m_type == 'voice': await call.bot.send_voice(call.message.chat.id, content, caption=pm_cap)
                elif m_type == 'text': await call.bot.send_message(call.message.chat.id, f"📝 [សារ/Link ពេលទិញរួច - {item_name}]\n{content}")
            except Exception as e:
                logger.error(f"Error previewing post_media: {e}")

    # បើមានស្តុកជា File/Media (photo/video/document) ផ្ទាល់ក្នុង stock
    if keys:
        for k in keys:
            if k[1] != 'text' and ':' in k[0]:
                m_type, m_id = k[0].split(':', 1)
                try:
                    if m_type == 'photo': await call.bot.send_photo(call.message.chat.id, m_id, caption=f"📦 [រូបភាពក្នុងស្តុក - {item_name}]")
                    elif m_type == 'video': await call.bot.send_video(call.message.chat.id, m_id, caption=f"📦 [វីដេអូក្នុងស្តុក - {item_name}]")
                    elif m_type == 'document': await call.bot.send_document(call.message.chat.id, m_id, caption=f"📦 [File ក្នុងស្តុក - {item_name}]")
                except Exception as e:
                    logger.error(f"Error previewing file stock: {e}")

    await call.answer()

@dp.callback_query(F.data == "adm_manage_stock")
async def adm_manage_stock(call: CallbackQuery):
    try: await call.answer()
    except Exception: pass
    cats = execute_db('SELECT id, name, icon FROM categories', fetchall=True)
    if not cats: return await call.answer("មិនមានទិន្នន័យទេ!", show_alert=True)
    kb = [[IBtn(text=c[1], callback_data=f"mstk_cat_{c[0]}", style="primary", icon_custom_emoji_id=c[2])] for c in cats]
    kb.append([IBtn(text="Back", callback_data="adm_stock_hub", style="danger", icon_custom_emoji_id="6035130900075777681")])
    text = "<tg-emoji emoji-id=\"6138899547625102613\">📦</tg-emoji>ផ្ទាំងគ្រុបគ្រងស្តុកលឿនរហ័ស \n👉 សូមជ្រើសរើសឈ្មោះ ផលលិតផល ខាងក្រោមដើម្បីគ្រុបស្តុក៖"
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data.startswith("mstk_cat_"))
async def mstk_cat_handler(call: CallbackQuery):
    cat_id = int(call.data.split("_")[2])
    items = execute_db('SELECT id, name, icon FROM items WHERE cat_id=?', (cat_id,), fetchall=True)
    kb = []
    for i in items:
        kb.append([IBtn(text=i[1], callback_data=f"stkopt_{i[0]}", style="primary", icon_custom_emoji_id=i[2])])
    kb.append([IBtn(text="Back", callback_data="adm_manage_stock", style="danger", icon_custom_emoji_id="6035130900075777681")])
    await call.message.edit_text("👉 សូមជ្រើសរើសទំនិញ៖", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data.startswith("stkopt_"))
async def stk_options(call: CallbackQuery):
    item_id = int(call.data.split("_")[1])
    inf_row = execute_db('SELECT is_infinite FROM items WHERE id=?', (item_id,), fetch=True)
    is_inf = inf_row[0] if inf_row and inf_row[0] else 0
    if not is_inf:
        inf_btns = [IBtn(text="អេតស្តុកមិនចេះអស់", callback_data=f"addinf_{item_id}", style="primary", icon_custom_emoji_id="5447387942995655277")]
    else:
        inf_btns = [
            IBtn(text="កែស្តុកមិនចេះអស់", callback_data=f"addinf_{item_id}", style="primary", icon_custom_emoji_id="5447387942995655277"),
            IBtn(text="❌ ដកស្តុកមិនចេះអស់", callback_data=f"delinf_{item_id}", style="danger", icon_custom_emoji_id="5258130763148172425")
        ]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="Add Key", callback_data=f"addstk_{item_id}", style="success", icon_custom_emoji_id="5397916757333654639"),
         IBtn(text="ទាញយក", callback_data=f"dlstk_{item_id}", style="primary", icon_custom_emoji_id="5307746710682869587"),
         IBtn(text="ដក Key", callback_data=f"clrstk_{item_id}", style="danger", icon_custom_emoji_id="5258130763148172425")],
        [IBtn(text="➕ Add Stock Auto", callback_data=f"addstk_auto_{item_id}", style="success")],
        inf_btns,
        [IBtn(text="Back", callback_data="adm_manage_stock", style="danger", icon_custom_emoji_id="6035130900075777681")]
    ])
    text = "<tg-emoji emoji-id=\"6138721800403559725\">👇</tg-emoji>សូមជ្រើសរើសបូតុងខាងក្រោម៖"
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data.startswith("addstk_auto_"))
async def addstk_auto_start(call: CallbackQuery, state: FSMContext):
    try: await call.answer()
    except Exception: pass
    item_id = int(call.data.replace("addstk_auto_", ""))
    row = execute_db(
        "SELECT items.name, categories.name, items.api_package_id FROM items JOIN categories ON items.cat_id = categories.id WHERE items.id=?",
        (item_id,), fetch=True
    )
    if not row:
        return await call.message.edit_text("❌ រកមិនឃើញទំនិញនេះទេ!", reply_markup=admin_back_inline("adm_manage_stock"))
    item_name, cat_name, api_pkg_id = row

    await call.message.edit_text("⏳ <b>កំពុងទាញព័ត៌មានស្តុកពីវេបសាយ API...</b>")
    try:
        catalog = await ResellerAPIAsync().catalog() or []
    except Exception as e:
        return await call.message.edit_text(
            f"❌ <b>មិនអាចភ្ជាប់ API វេបសាយបានទេ!</b>\n<code>{escape_html(str(e)[:200])}</code>",
            reply_markup=admin_back_inline(f"stkopt_{item_id}")
        )

    matched_pkg = None
    matched_prod_name = cat_name
    for prod in catalog:
        for pkg in prod.get("packages", []):
            if api_pkg_id and str(pkg.get("package_id")) == str(api_pkg_id):
                matched_pkg = pkg
                matched_prod_name = prod.get("name", cat_name)
                break
        if matched_pkg:
            break

    if not matched_pkg:
        for prod in catalog:
            if prod.get("name", "").strip().lower() == cat_name.strip().lower():
                for pkg in prod.get("packages", []):
                    if pkg.get("name", "").strip().lower() == item_name.strip().lower():
                        matched_pkg = pkg
                        matched_prod_name = prod.get("name", cat_name)
                        break
            if matched_pkg:
                break

    if not matched_pkg:
        # Let admin pick from API catalog products if not linked yet
        await state.update_data(auto_target_item_id=item_id, auto_api_catalog=catalog)
        kb_rows = []
        for idx, prod in enumerate(catalog[:15]):
            kb_rows.append([IBtn(text=f"{prod.get('name')} ({len(prod.get('packages', []))} កញ្ចប់)", callback_data=f"asaprod_{idx}", style="primary")])
        kb_rows.append([IBtn(text="Back", callback_data=f"stkopt_{item_id}", style="danger", icon_custom_emoji_id="6035130900075777681")])
        return await call.message.edit_text(
            f"📦 <b>ទំនិញ៖ {escape_html(cat_name)} - {escape_html(item_name)}</b>\n"
            f"👉 សូមរើសហ្គេមពី API វេបសាយដើម្បីទាញស្តុកអូតូ៖",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows)
        )

    stk_avail = "∞ (Unlimited)" if matched_pkg.get("stock") is None else str(matched_pkg.get("stock"))
    pkg_id = matched_pkg.get("package_id")
    await state.update_data(auto_target_item_id=item_id, auto_pkg_id=pkg_id, auto_pkg_name=matched_pkg.get("name"))
    await state.set_state(AdminAddStockAuto.qty)
    await call.message.edit_text(
        f"➕ <b>Add Stock Auto</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎮 ផលិតផល៖ <b>{escape_html(matched_prod_name)}</b>\n"
        f"📦 កញ្ចប់៖ <b>{escape_html(matched_pkg.get('name', item_name))}</b>\n"
        f"🌐 ស្តុកក្នុងវេបសាយ API៖ <b>{stk_avail}</b>\n"
        f"💵 តម្លៃដើម API៖ <b>${float(matched_pkg.get('price', 0)):.2f}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📥 <b>តើអ្នកចង់ទាញយកប៉ុន្មានស្តុក? (បញ្ចូលជាលេខ)៖</b>",
        reply_markup=cancel_inline()
    )

@dp.callback_query(F.data.startswith("asaprod_"))
async def addstk_auto_pick_prod(call: CallbackQuery, state: FSMContext):
    try: await call.answer()
    except Exception: pass
    idx = int(call.data.replace("asaprod_", ""))
    data = await state.get_data()
    catalog = data.get("auto_api_catalog", [])
    item_id = data.get("auto_target_item_id")
    if idx < 0 or idx >= len(catalog):
        return await call.message.edit_text("❌ ហ្គេមមិនត្រឹមត្រូវ!", reply_markup=admin_back_inline("adm_manage_stock"))
    prod = catalog[idx]
    pkgs = prod.get("packages", [])
    kb_rows = []
    for p_idx, p in enumerate(pkgs):
        stk = "∞" if p.get("stock") is None else str(p.get("stock"))
        kb_rows.append([IBtn(text=f"{p.get('name')} | ${float(p.get('price', 0)):.2f} (ស្តុក: {stk})", callback_data=f"asapkg_{idx}_{p_idx}", style="primary")])
    kb_rows.append([IBtn(text="Back", callback_data=f"stkopt_{item_id}", style="danger", icon_custom_emoji_id="6035130900075777681")])
    await call.message.edit_text(
        f"🎮 <b>{escape_html(prod.get('name'))}</b>\n👉 សូមរើសកញ្ចប់ដើម្បីទាញស្តុក៖",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows)
    )

@dp.callback_query(F.data.startswith("asapkg_"))
async def addstk_auto_pick_pkg(call: CallbackQuery, state: FSMContext):
    try: await call.answer()
    except Exception: pass
    parts = call.data.split("_")
    p_i, k_i = int(parts[1]), int(parts[2])
    data = await state.get_data()
    catalog = data.get("auto_api_catalog", [])
    item_id = data.get("auto_target_item_id")
    pkg = catalog[p_i]["packages"][k_i]
    pkg_id = pkg.get("package_id")
    execute_db("UPDATE items SET api_package_id=? WHERE id=?", (pkg_id, item_id))
    stk_avail = "∞ (Unlimited)" if pkg.get("stock") is None else str(pkg.get("stock"))
    await state.update_data(auto_pkg_id=pkg_id, auto_pkg_name=pkg.get("name"))
    await state.set_state(AdminAddStockAuto.qty)
    await call.message.edit_text(
        f"📦 <b>កញ្ចប់៖ {escape_html(pkg.get('name'))}</b>\n"
        f"🌐 ស្តុកក្នុងវេបសាយ API៖ <b>{stk_avail}</b>\n"
        f"💵 តម្លៃដើម API៖ <b>${float(pkg.get('price', 0)):.2f}</b>\n\n"
        f"📥 <b>តើអ្នកចង់ទាញយកប៉ុន្មានស្តុក? (បញ្ចូលជាលេខ)៖</b>",
        reply_markup=cancel_inline()
    )

@dp.message(AdminAddStockAuto.qty)
async def addstk_auto_exec(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    if not txt.isdigit() or int(txt) <= 0:
        return await msg.answer("❌ សូមបញ្ចូលចំនួនស្តុកជាលេខត្រឹមត្រូវ (ឧ. 5)៖", reply_markup=cancel_inline())
    qty = int(txt)
    data = await state.get_data()
    item_id = data.get("auto_target_item_id")
    pkg_id = data.get("auto_pkg_id")
    await state.clear()
    wait_m = await msg.answer(f"⏳ កំពុងទាញយក {qty} Key ពីវេបសាយ API...")
    try:
        ref = f"stkauto_{item_id}_{int(time.time())}"
        res = await ResellerAPIAsync().generate(pkg_id, quantity=qty, reference=ref)
        keys = res.get("keys") or []
        added = 0
        for k in keys:
            k_str = str(k).strip()
            if k_str:
                execute_db("INSERT INTO stock (item_id, key_data, type) VALUES (?, ?, ?)", (item_id, k_str, "text"))
                added += 1
        await wait_m.edit_text(
            f"✅ <b>បានទាញយក {added} Key ចូលស្តុកជោគជ័យ!</b>",
            reply_markup=admin_back_inline(f"stkopt_{item_id}")
        )
    except Exception as e:
        await wait_m.edit_text(
            f"❌ <b>ទាញយកស្តុកបរាជ័យ៖</b>\n<code>{escape_html(str(e)[:200])}</code>",
            reply_markup=admin_back_inline(f"stkopt_{item_id}")
        )

@dp.callback_query(F.data.startswith("dlstk_"))
async def dl_stock(call: CallbackQuery, bot: Bot):
    item_id = int(call.data.split("_")[1])
    keys = execute_db('SELECT key_data FROM stock WHERE item_id=? AND is_sold=0 AND type="text"', (item_id,), fetchall=True)
    if not keys: return await call.answer("គ្មាន Key (Text) សម្រាប់ទាញយកទេ!", show_alert=True)
    content = "\n".join([k[0] for k in keys])
    bio = BytesIO(content.encode('utf-8'))
    item_name = execute_db('SELECT name FROM items WHERE id=?', (item_id,), fetch=True)[0]
    await bot.send_document(call.message.chat.id, BufferedInputFile(bio.getvalue(), filename=f"{item_name}_keys.txt"))
    await call.answer("✅ បានទាញយក!", show_alert=True)

@dp.callback_query(F.data == "adm_clone_bot")
async def adm_clone_bot_menu(call: CallbackQuery):
    if is_clone_bot() or call.from_user.id != OWNER_ID: return await call.answer("គ្មានសិទ្ធិទេ!", show_alert=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="Clone Bots", callback_data="cb_add", style="success", icon_custom_emoji_id="5258362837411045098")],
        [IBtn(text="My Bots", callback_data="cb_list", style="primary", icon_custom_emoji_id="5258093637450866522")],
        [IBtn(text="Back", callback_data="back_admin", style="danger", icon_custom_emoji_id="6035130900075777681")]
    ])
    text = "<tg-emoji emoji-id=\"5364125616801073577\">🤖</tg-emoji>Clone Bot សូមបងរើសមីនុយខាងក្រោមដ៏ឆ្លាតវ័យមួយនេះ៖"
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data == "cb_add")
async def cb_add_prompt(call: CallbackQuery, state: FSMContext):
    if is_clone_bot() or call.from_user.id != OWNER_ID: return await call.answer("គ្មានសិទ្ធិទេ!", show_alert=True)
    text = "<tg-emoji emoji-id=\"5258362837411045098\">➕</tg-emoji>សូមបងដាក់ Token ឬ API Bots ដែលបងបានមកពីរ @botfather បងអាចយកមកដាក់ទីនេះបានខ្ញុំនឹងទាញយកហើយដំណើរការដោយស្វ័យប្រវត្តិអោយមង  ( ឧ . 12345678:VBCxz******************** )"
    await call.message.edit_text(text, reply_markup=cancel_inline())
    await state.set_state(AdminClone.token)
    await call.answer()

@dp.message(AdminClone.token)
async def cb_save_token(msg: Message, state: FSMContext):
    token = msg.text.strip()
    test_bot = Bot(token=token)
    try:
        me = await test_bot.get_me()
        await test_bot.session.close()
        await state.update_data(token=token, username=me.username, first_name=me.first_name)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [IBtn(text="ដាក់ ID ខ្ញុំផ្ទាល់", callback_data="cb_owner_me", style="primary")],
            [IBtn(text="❌ បោះបង់", callback_data="cancel_action", style="danger", icon_custom_emoji_id="6102914615107133393")]
        ])
        await msg.answer(f"✅ Token ត្រឹមត្រូវ (@{me.username})!\n\n👑 សូមបញ្ចូល <b>Telegram User ID</b> របស់ម្ចាស់បតនេះ ដើម្បីអោយគេមានសិទ្ធិជា Admin គ្រប់គ្រងបតដោយខ្លួនឯងទាំងអស់៖", reply_markup=kb)
        await state.set_state(AdminClone.owner_id)
    except Exception as e:
        try: await test_bot.session.close()
        except: pass
        await msg.answer("❌ Token មិនត្រឹមត្រូវ! សូមព្យាយាមម្តងទៀត៖", reply_markup=cancel_inline())

@dp.callback_query(AdminClone.owner_id, F.data == "cb_owner_me")
async def cb_save_owner_me(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    token, username, first_name = data['token'], data['username'], data['first_name']
    owner_uid = call.from_user.id
    bot_id = execute_db('INSERT INTO cloned_bots (token, bot_username, bot_name, owner_id) VALUES (?, ?, ?, ?)', (token, username, first_name, owner_uid), db_path='vbenstore.db')
    await start_cloned_bot(token, bot_id)
    await call.message.edit_text(f"✅ បានបន្ថែម Bot: @{username}\n👑 Owner ID: <code>{owner_uid}</code>\nកំពុងដំណើរការពេញលេញហើយឥឡូវនេះ! (ទិន្នន័យ និងមុខងារ Admin ដាច់ដោយឡែក ១០០%)")
    await state.clear()
    await call.answer()

@dp.message(AdminClone.owner_id)
async def cb_save_owner_id(msg: Message, state: FSMContext):
    try: owner_uid = int(msg.text.strip())
    except: return await msg.answer("❌ សូមបញ្ចូល User ID ជាលេខត្រឹមត្រូវ!", reply_markup=cancel_inline())
    data = await state.get_data()
    token, username, first_name = data['token'], data['username'], data['first_name']
    bot_id = execute_db('INSERT INTO cloned_bots (token, bot_username, bot_name, owner_id) VALUES (?, ?, ?, ?)', (token, username, first_name, owner_uid), db_path='vbenstore.db')
    await start_cloned_bot(token, bot_id)
    await msg.answer(f"✅ បានបន្ថែម Bot: @{username}\n👑 Owner ID: <code>{owner_uid}</code>\nកំពុងដំណើរការពេញលេញហើយឥឡូវនេះ! (ទិន្នន័យ និងមុខងារ Admin ដាច់ដោយឡែក ១០០%)")
    await state.clear()

@dp.callback_query(F.data == "cb_list")
async def cb_list(call: CallbackQuery):
    if is_clone_bot() or call.from_user.id != OWNER_ID: return await call.answer("គ្មានសិទ្ធិទេ!", show_alert=True)
    bots = execute_db('SELECT id, bot_username, bot_name FROM cloned_bots', fetchall=True, db_path='vbenstore.db')
    if not bots: return await call.answer("មិនទាន់មាន Bot ទេ!", show_alert=True)
    kb = [[IBtn(text=f"@{b[1]}", callback_data=f"cbmng_{b[0]}", style="primary", icon_custom_emoji_id="5258093637450866522")] for b in bots]
    kb.append([IBtn(text="Back", callback_data="adm_clone_bot", style="danger", icon_custom_emoji_id="6035130900075777681")])
    await call.message.edit_text("ជ្រើសរើស Bot របស់អ្នក៖", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data.startswith("cbmng_"))
async def cb_manage(call: CallbackQuery):
    if is_clone_bot() or call.from_user.id != OWNER_ID: return await call.answer("គ្មានសិទ្ធិទេ!", show_alert=True)
    bot_id = int(call.data.split("_")[1])
    b = execute_db('SELECT token, bot_username, bot_name, owner_id, is_active FROM cloned_bots WHERE id=?', (bot_id,), fetch=True, db_path='vbenstore.db')
    if not b: return await call.answer("រកមិនឃើញទេ!", show_alert=True)
    is_active = b[4]
    status_text = "កំពុងដំណើរការ 🟢" if is_active else "បានបញ្ឈប់ 🔴"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="▶️ចាប់ផ្ដើម Bot", callback_data=f"cbstart_{bot_id}", style="success"), IBtn(text="⏹ បពា្ឈប់ Bot", callback_data=f"cbstop_{bot_id}", style="danger")],
        [IBtn(text="🗑លុប បត", callback_data=f"cbdel_{bot_id}", style="danger", icon_custom_emoji_id="5258130763148172425")],
        [IBtn(text="Back", callback_data="cb_list", style="primary", icon_custom_emoji_id="6035130900075777681")]
    ])
    text = f"""<tg-emoji emoji-id="5258093637450866522">🤖</tg-emoji> <b>Username Bot:</b> @{b[1]}\n<tg-emoji emoji-id="5258328383183396223">🏷</tg-emoji> <b>Name Bot:</b> {b[2]}\n<tg-emoji emoji-id="5258215635996908355">🔑</tg-emoji> <b>Token Bot:</b> <code>{b[0][:15]}...</code>\n<tg-emoji emoji-id="5841276284155467413">👑</tg-emoji> <b>ID Owner Bot:</b> {b[3]}\n📊 <b>Status:</b> {status_text}"""
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data.startswith("cbstart_"))
async def cb_start(call: CallbackQuery):
    bot_id = int(call.data.split("_")[1])
    b = execute_db('SELECT token FROM cloned_bots WHERE id=?', (bot_id,), fetch=True, db_path='vbenstore.db')
    execute_db('UPDATE cloned_bots SET is_active=1 WHERE id=?', (bot_id,), db_path='vbenstore.db')
    if bot_id not in cloned_bot_tasks: await start_cloned_bot(b[0], bot_id)
    await call.answer("✅ បានចាប់ផ្តើម Bot!", show_alert=True)
    await cb_manage(call) 

@dp.callback_query(F.data.startswith("cbstop_"))
async def cb_stop(call: CallbackQuery):
    bot_id = int(call.data.split("_")[1])
    execute_db('UPDATE cloned_bots SET is_active=0 WHERE id=?', (bot_id,), db_path='vbenstore.db')
    if bot_id in cloned_bot_tasks:
        cloned_bot_tasks[bot_id]['task'].cancel()
        del cloned_bot_tasks[bot_id]
    await call.answer("✅ បានបញ្ឈប់ Bot!", show_alert=True)
    await cb_manage(call) 

@dp.callback_query(F.data.startswith("cbdel_"))
async def cb_del(call: CallbackQuery):
    bot_id = int(call.data.split("_")[1])
    execute_db('DELETE FROM cloned_bots WHERE id=?', (bot_id,), db_path='vbenstore.db')
    if bot_id in cloned_bot_tasks:
        cloned_bot_tasks[bot_id]['task'].cancel()
        del cloned_bot_tasks[bot_id]
    await call.answer("✅ បានលុប Bot!", show_alert=True)
    await cb_list(call)

# ====================================================================================================
# [ ផ្នែក USER - មីនុយទូទៅ ]
# ====================================================================================================

def get_start_inline_kb(is_admin=False):
    contact_url = (get_setting("contact_admin_url", "https://t.me/Vbenstore168") or "https://t.me/Vbenstore168").strip()
    start_defs = {
        "buynow": IBtn(text="Buy Now / ទិញឥឡូវនេះ", callback_data="buy_now_inline", style="success", icon_custom_emoji_id="5445146945024720188", btn_key="buynow"),
        "topup": IBtn(text="Top Up / បព្ចូាលទឹកប្រាក់", callback_data="topup_menu", style="primary", icon_custom_emoji_id="5447579253723918909", btn_key="topup"),
        "myorders": IBtn(text="My Orders / ការបព្ជាទិញរបស់ខ្ញុំ", callback_data="my_orders_cb", style="primary", icon_custom_emoji_id="5445023138297447592", btn_key="myorders"),
        "balance": IBtn(text="Balance / តុល្យភាព", callback_data="my_balance", style="primary", icon_custom_emoji_id="5444960062407732826", btn_key="balance"),
        "contact": IBtn(text="Contact Admin / ទាក់ទងអ្នកគ្រប់គ្រង", url=contact_url, style="success", icon_custom_emoji_id="5445046442789999895", btn_key="contact"),
    }
    rows = []
    raw_l = get_setting("org_layout_start_menu")
    raw_s = get_setting("org_styles_start_menu")
    if raw_l:
        try:
            c_layout = json.loads(raw_l)
            c_styles = json.loads(raw_s) if raw_s else {}
            for r in c_layout:
                r_btns = []
                for k in r:
                    if k in start_defs:
                        b = start_defs[k]
                        if k in c_styles:
                            try: object.__setattr__(b, 'style', c_styles[k])
                            except Exception: pass
                        r_btns.append(b)
                if r_btns:
                    rows.append(r_btns)
            placed = {k for r in c_layout for k in r}
            for k, b in start_defs.items():
                if k not in placed:
                    rows.append([b])
        except Exception:
            rows = []
    if not rows:
        rows = [
            [start_defs["buynow"]],
            [start_defs["topup"]],
            [start_defs["myorders"]],
            [start_defs["balance"]],
            [start_defs["contact"]],
        ]
    if is_admin:
        rows.append([IBtn(text="ADMIN PANEL / អ្នកកាន់បត", callback_data="admin_panel", style="danger", icon_custom_emoji_id="5444869180899752137", btn_key="adminpanel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def has_active_pending_qr(uid: int) -> bool:
    now = time.time()
    rows = execute_db(
        "SELECT payment_id, pay_type, created_at FROM pending_payments WHERE user_id=? AND is_done=0",
        (uid,), fetchall=True
    ) or []
    for pid, ptype, created_at in rows:
        age = now - float(created_at or 0)
        ttl = 180 if ptype in ("aba", "topup_aba") else 600
        if age < ttl:
            return True
        else:
            execute_db("UPDATE pending_payments SET is_done=3 WHERE payment_id=?", (pid,))
    return False

async def show_start_screen(event, current_bot: Bot):
    uid = event.from_user.id
    owner_id = get_current_owner()
    u_name = escape_html(event.from_user.first_name or "Friend")
    try:
        me = await current_bot.get_me()
        bot_name = escape_html(me.first_name or "Store Bot")
    except Exception:
        bot_name = "Store Bot"

    res = execute_db('SELECT is_admin FROM users WHERE id=?', (uid,), fetch=True)
    is_admin = res[0] if res else 0

    raw_text = get_setting('start_text', DEFAULT_START_TEXT)
    if not raw_text or "Hellow brother" in raw_text or "Welcome to our store" in raw_text or "ITACHI BOT" in raw_text or "The items are as follows" in raw_text or "Hello {name}" in raw_text or "ប្រព័ន្ធទិញទំនិញស្វ័យប្រវត្តិ" in raw_text or "Wellcome to store" in raw_text or "BUY NOW ខាងក្រោម" in raw_text:
        raw_text = DEFAULT_START_TEXT
        execute_db('UPDATE settings SET value=? WHERE key=?', (DEFAULT_START_TEXT, 'start_text'))

    text = render_clean_text(raw_text.replace("{name}", u_name).replace("{bot_name}", bot_name))
    inline_kb = get_start_inline_kb(is_admin=(bool(is_admin) or uid == owner_id))

    chat_id = event.message.chat.id if isinstance(event, CallbackQuery) else event.chat.id
    dots_msg = None
    if isinstance(event, Message):
        try:
            dots_msg = await current_bot.send_message(chat_id, ". ..")
        except Exception:
            dots_msg = None

    # Delete previous /start menu message if any
    prev_mid = get_setting(f"last_start_msg_{uid}")
    if prev_mid and str(prev_mid).isdigit():
        try:
            await current_bot.delete_message(chat_id, int(prev_mid))
        except Exception:
            pass

    if isinstance(event, CallbackQuery):
        try: await event.message.delete()
        except Exception: pass

    start_media = get_setting('start_media')
    sent_start_msg = None
    media_sent = False
    if start_media and ':' in str(start_media):
        try:
            m_type, m_id = start_media.split(':', 1)
            if m_type == 'photo':
                sent_start_msg = await current_bot.send_photo(chat_id, m_id, caption=text, reply_markup=inline_kb)
                media_sent = True
            elif m_type == 'video':
                sent_start_msg = await current_bot.send_video(chat_id, m_id, caption=text, reply_markup=inline_kb)
                media_sent = True
            elif m_type == 'animation':
                sent_start_msg = await current_bot.send_animation(chat_id, m_id, caption=text, reply_markup=inline_kb)
                media_sent = True
        except Exception as e:
            logger.warning(f"Failed to send start_media photo/video: {e}")
            execute_db("DELETE FROM settings WHERE key='start_media'")
            media_sent = False

    if not media_sent:
        try:
            sent_start_msg = await current_bot.send_message(chat_id, text, reply_markup=inline_kb)
        except Exception as e:
            logger.error(f"Error sending start text message: {e}")

    if dots_msg:
        try: await dots_msg.delete()
        except Exception: pass

    if sent_start_msg:
        execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (f"last_start_msg_{uid}", str(sent_start_msg.message_id)))

@dp.message(CommandStart(), StateFilter("*"))
async def cmd_start(msg: Message, state: FSMContext, bot: Bot):
    await state.clear()
    try: await msg.delete()
    except Exception: pass
    owner_id = get_current_owner()
    user_exists = execute_db('SELECT id FROM users WHERE id=?', (msg.from_user.id,), fetch=True)
    if not user_exists:
        is_adm_init = 1 if msg.from_user.id == owner_id else 0
        execute_db('INSERT INTO users (id, is_admin, first_name, username) VALUES (?, ?, ?, ?)', (msg.from_user.id, is_adm_init, msg.from_user.first_name, msg.from_user.username))
        u_name = msg.from_user.first_name or "Unknown"
        u_user = f"@{msg.from_user.username}" if msg.from_user.username else "គ្មាន"
        kh_now = datetime.utcnow() + timedelta(hours=7)
        now_str = kh_now.strftime("%d-%m-%Y %I:%M:%S %p")
        alert_text = f"""━━━━━━━━━━━━━━━━━━━━ 
🆕 <b>អតថិជនថ្មី</b> 
━━━━━━━━━━━━━━━━━━━━ 
· លេខសម្គាល់ : <code>{msg.from_user.id}</code>
· ឈ្មោះអ្នកប្រើ : <b>{u_name}</b> ({u_user})
· ចូល : <b>{now_str}</b> 
━━━━━━━━━━━━━━━━━━━━ 
❤️ សូមបងបព្ជាទិញសេវាកម្មដែលមានក្នុង bot ចុះបង! 🙏
━━━━━━━━━━━━━━━━━━━━"""
        await alert_to_channel(alert_text, bot)

    await show_start_screen(msg, bot)

# ----------------- SHOP FLOW -----------------

@dp.callback_query(F.data == "buy_now_direct")
@dp.callback_query(F.data == "buy_now_inline")
async def buy_now_inline_handler(call: CallbackQuery, bot: Bot):
    await send_categories(call, bot)
    await call.answer()

@dp.callback_query(F.data == "back_to_start")
async def back_to_start_handler(call: CallbackQuery, bot: Bot):
    await show_start_screen(call, bot)
    await call.answer()

@dp.message(StateFilter("*"), F.text.contains("BUY NOW") | F.text.contains("Buy Now") | F.text.contains("ទិញឥឡូវនេះ"))
@dp.message(Command("shop"))
@dp.message(Command("buy"))
async def shop_categories(msg: Message, state: FSMContext, bot: Bot):
    await state.clear()
    await send_categories(msg, bot)

# (Commands /orders, /contact, /help, /share completely removed as requested)

# ----------------- CHAT ADMIN FLOW -----------------
@dp.message(Command("chat_admin"))
async def cmd_chat_admin(msg: Message):
    text = "<tg-emoji emoji-id=\"5282855515481711638\">ℹ️</tg-emoji> ចង់ដឹងព័ត៍មានសូមបងចុចបូតុងខាងក្រោមដើម្បីនិយាយជាមួយ Admin"
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        IBtn(text="Chat Admin / ឆាត អេតមីន", callback_data="user_chat_admin_click", style="primary", icon_custom_emoji_id="5235570365094188078")
    ]])
    await msg.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "user_chat_admin_click")
async def user_chat_admin_click_handler(call: CallbackQuery, state: FSMContext):
    text = "<tg-emoji emoji-id=\"5235570365094188078\">💬</tg-emoji> សូមបងវាយសារដែលចង់ធ្ញើទៅ Admin វាយធ្ញើមកទីនេះមក"
    await call.message.edit_text(text, reply_markup=cancel_inline())
    await state.set_state(UserChatAdmin.message)
    await call.answer()

@dp.message(UserChatAdmin.message)
async def user_send_chat_admin(msg: Message, state: FSMContext, bot: Bot):
    await state.clear()
    await msg.answer("<tg-emoji emoji-id=\"5472239203590888751\">⏳</tg-emoji> Admin កំពង់មើលសារបឹងឆ្លើយតបវិញឆាប់ៗ.....")
    
    uid = msg.from_user.id
    u_name = escape_html(msg.from_user.first_name or "Unknown")
    u_user = f"@{msg.from_user.username}" if msg.from_user.username else "គ្មាន"
    admin_cap = f"💬 <b>សារថ្មីពីសមាជិក (Chat Admin):</b>\n- ID: <code>{uid}</code>\n- Name: {u_name}\n- Username: {u_user}\n━━━━━━━━━━━━━━━━━━━━\n"
    
    reply_kb = InlineKeyboardMarkup(inline_keyboard=[[
        IBtn(text="Reply Chat / តបឆាត", callback_data=f"adm_reply_chat_{uid}", style="primary", icon_custom_emoji_id="5188481279963715781")
    ]])
    
    owner_id = get_current_owner()
    admins = execute_db('SELECT id FROM users WHERE is_admin=1', fetchall=True) or [(owner_id,)]
    admin_ids = set([a[0] for a in admins] + [owner_id])
    
    for adm_id in admin_ids:
        try:
            if msg.text:
                await bot.send_message(adm_id, admin_cap + f"📝 <b>សារ៖</b>\n{msg.html_text}", reply_markup=reply_kb)
            elif msg.photo:
                await bot.send_photo(adm_id, msg.photo[-1].file_id, caption=admin_cap + f"📝 <b>សារ៖</b>\n{msg.html_text if msg.caption else ''}", reply_markup=reply_kb)
            elif msg.video:
                await bot.send_video(adm_id, msg.video.file_id, caption=admin_cap + f"📝 <b>សារ៖</b>\n{msg.html_text if msg.caption else ''}", reply_markup=reply_kb)
            elif msg.document:
                await bot.send_document(adm_id, msg.document.file_id, caption=admin_cap + f"📝 <b>សារ៖</b>\n{msg.html_text if msg.caption else ''}", reply_markup=reply_kb)
            elif msg.audio:
                await bot.send_audio(adm_id, msg.audio.file_id, caption=admin_cap + f"📝 <b>សារ៖</b>\n{msg.html_text if msg.caption else ''}", reply_markup=reply_kb)
            elif msg.voice:
                await bot.send_voice(adm_id, msg.voice.file_id, caption=admin_cap + f"📝 <b>សារ៖</b>\n{msg.html_text if msg.caption else ''}", reply_markup=reply_kb)
        except Exception as e:
            logger.error(f"Failed to forward user chat to admin {adm_id}: {e}")

@dp.callback_query(F.data.startswith("adm_reply_chat_"))
async def adm_reply_chat_start(call: CallbackQuery, state: FSMContext):
    target_uid = int(call.data.replace("adm_reply_chat_", ""))
    await state.update_data(reply_target_uid=target_uid)
    text = f"✍️ សូមវាយសារ ឬផ្ញើ (Text/រូបភាព/វីដេអូ/សំឡេង) ដើម្បីតបទៅកាន់ User <code>{target_uid}</code> ៖"
    await call.message.answer(text, reply_markup=cancel_inline())
    await state.set_state(AdminReplyChat.reply_msg)
    await call.answer()

@dp.message(AdminReplyChat.reply_msg)
async def adm_reply_chat_send(msg: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    target_uid = data.get('reply_target_uid')
    if not target_uid:
        await state.clear()
        return await msg.answer("❌ មិនមានព័ត៌មាន User ទេ!")
        
    prefix = "<tg-emoji emoji-id=\"5298614648138919107\">👨‍💻</tg-emoji> <b>Admin Support</b>\n\n"
    sent_ok = False
    try:
        if msg.text:
            await bot.send_message(target_uid, prefix + msg.html_text)
            sent_ok = True
        elif msg.photo:
            await bot.send_photo(target_uid, msg.photo[-1].file_id, caption=prefix + (msg.html_text or ""))
            sent_ok = True
        elif msg.video:
            await bot.send_video(target_uid, msg.video.file_id, caption=prefix + (msg.html_text or ""))
            sent_ok = True
        elif msg.document:
            await bot.send_document(target_uid, msg.document.file_id, caption=prefix + (msg.html_text or ""))
            sent_ok = True
        elif msg.audio:
            await bot.send_audio(target_uid, msg.audio.file_id, caption=prefix + (msg.html_text or ""))
            sent_ok = True
        elif msg.voice:
            await bot.send_voice(target_uid, msg.voice.file_id, caption=prefix + (msg.html_text or ""))
            sent_ok = True
    except Exception as e:
        logger.error(f"Failed to send admin reply to user {target_uid}: {e}")
        await msg.answer(f"❌ មិនអាចផ្ញើសារទៅកាន់ User បានទេ ({e})")
        
    if sent_ok:
        await msg.answer(f"✅ បានឆ្លើយតបសារទៅកាន់ User <code>{target_uid}</code> រួចរាល់!")
    await state.clear()

async def send_categories(event, current_bot: Bot):
    cats = execute_db('SELECT id, name, icon, media_data FROM categories', fetchall=True)
    if not cats:
        txt = "<tg-emoji emoji-id='5258514780469075716'>⚠️</tg-emoji> មិនទាន់មានទំនិញ ឬ Category ត្រូវបានបង្កើតនៅឡើយទេ!\n\n👉 សូមចូលទៅកាន់ ADMIN PANEL ➔ គ្រុបគ្រងផលលិតផល & ទំនិញ  ដើម្បីបង្កើត Category ថ្មី។"
        if isinstance(event, CallbackQuery): 
            try: await event.message.edit_text(txt)
            except: pass
            return
        return await event.answer(txt)
    
    raw_l = get_setting("org_layout_cats")
    raw_s = get_setting("org_styles_cats")
    custom_used = False
    if raw_l:
        try:
            c_layout = json.loads(raw_l)
            c_styles = json.loads(raw_s) if raw_s else {}
            cats_map = {str(c[0]): c for c in cats}
            kb = []
            for r in c_layout:
                row_btns = []
                for cid in r:
                    cid_str = str(cid)
                    if cid_str in cats_map:
                        c = cats_map[cid_str]
                        total_stock = execute_db('SELECT COUNT(*) FROM stock s JOIN items i ON s.item_id = i.id WHERE i.cat_id=? AND s.is_sold=0', (c[0],), fetch=True)[0]
                        inf_c = execute_db('SELECT COUNT(*) FROM items WHERE cat_id=? AND is_infinite=1', (c[0],), fetch=True)[0]
                        has_stk = (total_stock > 0 or inf_c > 0)
                        st = "danger" if not has_stk else c_styles.get(cid_str, "primary")
                        row_btns.append(IBtn(text=c[1], callback_data=f"sel_cat_{c[0]}", style=st, icon_custom_emoji_id=c[2]))
                if row_btns: kb.append(row_btns)
            custom_used = len(kb) > 0
        except:
            custom_used = False

    if not custom_used:
        kb = []
        row = []
        for c in cats:
            total_stock = execute_db('SELECT COUNT(*) FROM stock s JOIN items i ON s.item_id = i.id WHERE i.cat_id=? AND s.is_sold=0', (c[0],), fetch=True)[0]
            style = "primary" if total_stock > 0 else "danger"
            btn = IBtn(text=c[1], callback_data=f"sel_cat_{c[0]}", style=style, icon_custom_emoji_id=c[2])
            if len(c[1]) <= 18:
                row.append(btn)
                if len(row) == 2:
                    kb.append(row)
                    row = []
            else:
                if row:
                    kb.append(row)
                    row = []
                kb.append([btn])
        if row:
            kb.append(row)
        
    kb.append([IBtn(text="Back", callback_data="back_to_start", style="danger", icon_custom_emoji_id="5447651546613449378")])
    
    text = render_clean_text("<tg-emoji emoji-id=\"5447319442562251569\">🛒</tg-emoji> <b>Chosse &amp; Category</b> <tg-emoji emoji-id=\"5231102735817918643\">📦</tg-emoji> ៖")
    if isinstance(event, CallbackQuery):
        try: await event.message.delete()
        except: pass
        await current_bot.send_message(event.message.chat.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    else:
        await event.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("sel_cat_"))
async def shop_items(call: CallbackQuery, bot: Bot):
    cat_id = int(call.data.split("_")[2])
    uid = call.from_user.id
    res = execute_db('SELECT is_reseller, is_reseller_vip FROM users WHERE id=?', (uid,), fetch=True)
    is_res = res[0] if (res and res[0]) else 0
    is_vip = res[1] if (res and len(res) > 1 and res[1]) else 0
    cat = execute_db('SELECT name, media_data, icon, description, is_disabled FROM categories WHERE id=?', (cat_id,), fetch=True)
    if cat and len(cat) > 4 and cat[4] == 1:
        return await call.answer("♻️ ម៉ូតក្រុមហ៊ុនគេកំពង់ធ្វើការ Update សូមបងទៅទិញម៉ូតផ្សេងបានណា⏳", show_alert=True)
    items = execute_db('SELECT id, name, icon, price, reseller_price, is_infinite, reseller_vip_price FROM items WHERE cat_id=?', (cat_id,), fetchall=True)
    
    raw_l = get_setting(f"org_layout_items_{cat_id}")
    raw_s = get_setting(f"org_styles_items_{cat_id}")
    custom_used = False
    if raw_l:
        try:
            c_layout = json.loads(raw_l)
            c_styles = json.loads(raw_s) if raw_s else {}
            items_map = {str(i[0]): i for i in items}
            kb = []
            for r in c_layout:
                row_btns = []
                for iid in r:
                    iid_str = str(iid)
                    if iid_str in items_map:
                        i = items_map[iid_str]
                        is_inf = i[5] if len(i) > 5 and i[5] else 0
                        vip_p = i[6] if (len(i) > 6 and i[6] and i[6] > 0) else 0.0
                        if is_vip and vip_p > 0: u_price = vip_p
                        elif is_res: u_price = i[4]
                        else: u_price = i[3]
                        stk = 9999 if is_inf else execute_db('SELECT COUNT(*) FROM stock WHERE item_id=? AND is_sold=0', (i[0],), fetch=True)[0]
                        stk_disp = "∞" if is_inf else str(stk)
                        if stk > 0:
                            if is_vip and vip_p > 0:
                                btn_text = f"{i[1]} • ${u_price:.2f} • Stock: {stk_disp} • Reseller VIP"
                            elif is_res:
                                btn_text = f"{i[1]} • ${u_price:.2f} • Stock: {stk_disp} • Reseller"
                            else:
                                btn_text = f"{i[1]} • ${u_price:.2f} • Stock: {stk_disp}"
                            def_style, cb_data = "primary", f"sel_item_{i[0]}"
                            st = c_styles.get(iid_str, def_style)
                        else:
                            btn_text, def_style, cb_data = f"{i[1]} • ${u_price:.2f} • [Out of Stock]", "danger", "ignore_click"
                            st = "danger"
                        row_btns.append(IBtn(text=btn_text, callback_data=cb_data, style=st, icon_custom_emoji_id=i[2]))
                if row_btns: kb.append(row_btns)
            if kb:
                placed_ids = {str(iid) for r in c_layout for iid in r}
                for i in items:
                    if str(i[0]) not in placed_ids:
                        is_inf = i[5] if len(i) > 5 and i[5] else 0
                        vip_p = i[6] if (len(i) > 6 and i[6] and i[6] > 0) else 0.0
                        if is_vip and vip_p > 0: u_price = vip_p
                        elif is_res: u_price = i[4]
                        else: u_price = i[3]
                        if is_inf:
                            btn_text, def_style, cb_data = f"{i[1]} (${u_price:.2f}) [Stock: ∞]", "primary", f"sel_item_{i[0]}"
                        else:
                            stk = execute_db('SELECT COUNT(*) FROM stock WHERE item_id=? AND is_sold=0', (i[0],), fetch=True)[0]
                            if stk > 0:
                                btn_text, def_style, cb_data = f"{i[1]} (${u_price:.2f}) [Stock: {stk}]", "primary", f"sel_item_{i[0]}"
                            else:
                                btn_text, def_style, cb_data = f"{i[1]} (${u_price:.2f}) [Out of Stock]", "danger", "ignore_click"
                        kb.append([IBtn(text=btn_text, callback_data=cb_data, style=def_style, icon_custom_emoji_id=i[2])])
                kb.append([IBtn(text="Back to Category", callback_data="back_to_cat", style="danger", icon_custom_emoji_id="5352759161945867747")])
                custom_used = True
        except:
            custom_used = False

    if not custom_used:
        kb = []
        row = []
        for i in items:
            is_inf = i[5] if len(i) > 5 and i[5] else 0
            stk = 9999 if is_inf else execute_db('SELECT COUNT(*) FROM stock WHERE item_id=? AND is_sold=0', (i[0],), fetch=True)[0]
            vip_p = i[6] if (len(i) > 6 and i[6] and i[6] > 0) else 0.0
            if is_vip and vip_p > 0: u_price = vip_p
            elif is_res: u_price = i[4]
            else: u_price = i[3]
            if is_inf:
                btn_text, style, cb_data = f"{i[1]} (${u_price:.2f}) [Stock: ∞]", "primary", f"sel_item_{i[0]}"
            elif stk > 0:
                btn_text, style, cb_data = f"{i[1]} (${u_price:.2f}) [Stock: {stk}]", "primary", f"sel_item_{i[0]}"
            else:
                btn_text, style, cb_data = f"{i[1]} (${u_price:.2f}) [Out of Stock]", "danger", "ignore_click"
            
            btn = IBtn(text=btn_text, callback_data=cb_data, style=style, icon_custom_emoji_id=i[2])
            if len(btn_text) <= 22:
                row.append(btn)
                if len(row) == 2:
                    kb.append(row)
                    row = []
            else:
                if row:
                    kb.append(row)
                    row = []
                kb.append([btn])
        if row:
            kb.append(row)
        kb.append([IBtn(text="Back to Category", callback_data="back_to_cat", style="danger", icon_custom_emoji_id="5352759161945867747")])
    
    cat_desc = cat[3] if cat and len(cat) > 3 and cat[3] else None
    desc_str = f"\n\n<blockquote>{cat_desc}</blockquote>" if cat_desc else ""
    text = render_clean_text(f"{get_emoji_str(cat[2])} <b>{cat[0]}</b>{desc_str}")
    
    try: await call.message.delete()
    except: pass
    cat_sent = False
    if cat[1] and ':' in str(cat[1]):
        try:
            m_type, m_id = cat[1].split(':', 1)
            if m_type == 'photo':
                await bot.send_photo(call.message.chat.id, m_id, caption=text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
                cat_sent = True
            elif m_type == 'video':
                await bot.send_video(call.message.chat.id, m_id, caption=text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
                cat_sent = True
        except Exception as e:
            logger.warning(f"Error sending category media: {e}")
            cat_sent = False
            
    if not cat_sent:
        try:
            await bot.send_message(call.message.chat.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        except Exception as e:
            logger.error(f"Error sending category fallback text: {e}")
    await call.answer()

@dp.callback_query(F.data == "ignore_click")
async def ignore_click_handler(call: CallbackQuery):
    await call.answer("❌ ទំនិញនេះអស់ស្តុកហើយ!", show_alert=True)

@dp.callback_query(F.data == "back_to_cat")
async def back_to_cat_handler(call: CallbackQuery, bot: Bot):
    await send_categories(call, bot)
    await call.answer()

@dp.callback_query(F.data.startswith("sel_item_"))
async def pre_checkout_item(call: CallbackQuery, state: FSMContext, bot: Bot):
    try: await call.answer()
    except: pass
    await state.clear()
    parts = call.data.split("_")
    item_id = int(parts[2])
    qty = int(parts[3]) if len(parts) > 3 else 1
    await render_checkout(call, item_id, qty, is_edit=True, current_bot=bot)

async def render_checkout(event, item_id, qty, is_edit=True, old_msg_id=None, current_bot: Bot = bot):
    uid = event.from_user.id
    res = execute_db('SELECT is_reseller, is_reseller_vip FROM users WHERE id=?', (uid,), fetch=True)
    is_res = res[0] if (res and res[0]) else 0
    is_vip = res[1] if (res and len(res) > 1 and res[1]) else 0
    item = execute_db('''SELECT items.name, items.price, items.reseller_price, items.cat_id, categories.name, items.reseller_vip_price FROM items JOIN categories ON items.cat_id = categories.id WHERE items.id=?''', (item_id,), fetch=True)
    if not item:
        if isinstance(event, CallbackQuery):
            return await event.answer("❌ រកមិនឃើញទិន្នន័យទំនិញនេះទេ!", show_alert=True)
        return await event.answer("❌ រកមិនឃើញទិន្នន័យទំនិញនេះទេ!")
        
    item_name = escape_html(str(item[0] or "Unknown Item"))
    cat_name = escape_html(str(item[4] or "Unknown Category"))
    
    item_inf = execute_db('SELECT is_infinite FROM items WHERE id=?', (item_id,), fetch=True)
    is_inf = bool(item_inf[0]) if (item_inf and item_inf[0]) else False
    if is_inf:
        stock_qty = 9999
    else:
        res_stk = execute_db('SELECT COUNT(*) FROM stock WHERE item_id=? AND is_sold=0', (item_id,), fetch=True)
        stock_qty = res_stk[0] if res_stk else 0
    
    vip_p = item[5] if (len(item) > 5 and item[5] and item[5] > 0) else 0.0
    if is_vip and vip_p > 0: u_price = vip_p
    elif is_res: u_price = item[2]
    else: u_price = item[1]
    total = u_price * qty
    
    # 🎯 ទម្រង់អក្សរតូចស្អាតតាមរូបភាពអ្នកប្រើប្រាស់ (A8A654BB-B7E7-490A-97DC-18763714A9C2_3c99e5.jpeg)
    text = f"""<tg-emoji emoji-id="5332455502917949981">🏛️</tg-emoji> <b>ជ្រើសរើសវិធីទូរទាត់ខាងក្រោម</b>\n\n<tg-emoji emoji-id="6285019600664928290">💰</tg-emoji> <b>Quantity: {qty} | Total: ${total:.2f}</b>"""

    aba_status = get_setting('aba_pay_status', 'on')
    mkhqr_status = get_setting('manual_khqr_status', 'off')
    bakong_status = get_setting('bakong_pay_status', 'off')
    
    rows = []
    prev_q = max(1, qty - 1)
    next_q = min(stock_qty, qty + 1)
    
    stk_disp = "∞" if is_inf else str(stock_qty)
    text = f"""<tg-emoji emoji-id="5332455502917949981">🏛️</tg-emoji> <b>កំណត់ចំនួនទំនិញដែលចង់ទិញ</b>
━━━━━━━━━━━━━━━━━━━━━
- <tg-emoji emoji-id="5231102735817918643">📦</tg-emoji> <b>ទំនិញ៖</b> {cat_name}
- <tg-emoji emoji-id="5445023138297447592">🔑</tg-emoji> <b>កញ្ចប់៖</b> {item_name}
- <tg-emoji emoji-id="5444860552310457690">💰</tg-emoji> <b>តម្លៃរាយ៖</b> ${u_price:.2f} / មួយ
- <tg-emoji emoji-id="6138721800403559725">👀</tg-emoji> <b>ស្តុកនៅសល់៖</b> {stk_disp}
━━━━━━━━━━━━━━━━━━━━━
- <tg-emoji emoji-id="5213305971891248967">🔢</tg-emoji> <b>ចំនួនជ្រើសរើស៖</b> {qty}
- <tg-emoji emoji-id="5444860552310457690">💵</tg-emoji> <b>តម្លៃសរុប៖</b> ${total:.2f}

<tg-emoji emoji-id="6071034593287345457">👉</tg-emoji> ចុច 'ចំនួនផ្ទាល់ខ្លួន' ដើម្បីកែប្រែចំនួន ឬជ្រើសរើសវិធីបង់ប្រាក់ខាងក្រោម៖"""

    rows = []
    # 🎯 ប៊ូតុង "ចំនួនផ្ទាល់ខ្លួន"
    rows.append([
        IBtn(text="ចំនួនផ្ទាល់ខ្លួន", callback_data=f"custom_qty_{item_id}_{qty}", style="primary", icon_custom_emoji_id="5213305971891248967")
    ])
    
    # 🎯 វិធីសាស្ត្រទូទាត់ដែលមានបង្ហាញតម្លៃ
    rows.append([IBtn(text=f"Pay Balance (${total:.2f})", callback_data=f"paybal_{item_id}_{qty}", style="success", icon_custom_emoji_id="5444860552310457690", btn_key="paybal")])
    if aba_status == 'on':
        rows.append([IBtn(text=f"Pay with ABA (${total:.2f})", callback_data=f"abapay_{item_id}_{qty}", style="primary", icon_custom_emoji_id="6314519407443845610", btn_key="abapay")])
    if get_setting('khqrpay_pay_status', 'off') == 'on':
        rows.append([IBtn(text=f"Pay With ABA KHQR • ${total:.2f}", callback_data=f"khqrpay_{item_id}_{qty}", style="primary", icon_custom_emoji_id="6314519407443845610", btn_key="khqrpay")])
    if bakong_status == 'on':
        rows.append([IBtn(text=f"Pay with Bakong (${total:.2f})", callback_data=f"bakongpay_{item_id}_{qty}", style="primary", icon_custom_emoji_id="6095690437165586962", btn_key="bakongpay")])
    binance_status = get_setting('binance_pay_status', 'off')
    if binance_status == 'on':
        rows.append([IBtn(text=f"Pay Binance - ${total:.2f}", callback_data=f"binancepay_{item_id}_{qty}", style="primary", icon_custom_emoji_id="5793944030861598035", btn_key="binancepay")])
    if mkhqr_status == 'on':
        rows.append([IBtn(text=f"Pay with KHQR (${total:.2f})", callback_data=f"mkhqr_{item_id}_{qty}", style="primary", icon_custom_emoji_id="5422814644093868925", btn_key="khqr")])
        
    # 🎯 ប៊ូតុង Back to Category
    rows.append([IBtn(text="Back to Category", callback_data=f"sel_cat_{item[3]}", style="danger", icon_custom_emoji_id="5352759161945867747")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    
    rendered = render_clean_text(text)
    if is_edit and isinstance(event, CallbackQuery):
        edited = False
        try:
            await event.message.edit_text(rendered, reply_markup=kb)
            edited = True
        except Exception:
            edited = False
            
        if not edited:
            sent_msg = None
            try:
                sent_msg = await current_bot.send_message(event.message.chat.id, rendered, reply_markup=kb)
            except Exception:
                plain = re.sub(r"<[^>]+>", "", rendered)
                try: sent_msg = await current_bot.send_message(event.message.chat.id, plain, reply_markup=kb, parse_mode=None)
                except Exception: pass
            if sent_msg:
                try: await event.message.delete()
                except Exception: pass
        try: await event.answer()
        except Exception: pass
    else:
        if old_msg_id:
            try: await current_bot.delete_message(event.chat.id, old_msg_id)
            except Exception: pass
        try:
            await event.answer(rendered, reply_markup=kb)
        except Exception:
            plain = re.sub(r"<[^>]+>", "", rendered)
            await event.answer(plain, reply_markup=kb, parse_mode=None)
@dp.callback_query(F.data == "noop_keys")
async def noop_keys_handler(call: CallbackQuery):
    try: await call.answer()
    except: pass

@dp.callback_query(F.data.startswith("adjqty_"))
async def adjust_qty_handler(call: CallbackQuery, bot: Bot):
    parts = call.data.split("_")
    item_id, target_qty = int(parts[1]), int(parts[2])
    stock_qty = get_item_stock(item_id)
    target_qty = max(1, min(stock_qty, target_qty))
    await render_checkout(call, item_id, target_qty, is_edit=True, current_bot=bot)

@dp.callback_query(F.data.startswith("cqty_"))
async def ask_custom_qty(call: CallbackQuery, state: FSMContext):
    item_id = int(call.data.split("_")[1])
    stock_qty = get_item_stock(item_id)
    text = f"""<tg-emoji emoji-id="5890864241388293875">✏️</tg-emoji> <b>បញ្ចូលចំនួនទំនិញផ្ទាល់ខ្លួន</b>\n\n<blockquote>• ស្តុកនៅសល់៖ {stock_qty}\n👉 <b>សូមផ្ញើចំនួនដែលចង់ទិញ (ជាលេខ) មកកាន់ខ្ញុំឥឡូវនេះ៖</b></blockquote>"""
    kb = InlineKeyboardMarkup(inline_keyboard=[[IBtn(text="Back", callback_data=f"sel_item_{item_id}", style="danger", icon_custom_emoji_id="5352759161945867747")]])
    try:
        await call.message.edit_text(text, reply_markup=kb)
        prompt_msg_id = call.message.message_id
    except:
        try: await call.message.delete()
        except: pass
        sent = await call.message.answer(text, reply_markup=kb)
        prompt_msg_id = sent.message_id
        
    await state.update_data(item_id=item_id, prompt_msg_id=prompt_msg_id)
    await state.set_state(OrderFSM.custom_qty)
    await call.answer()

@dp.message(OrderFSM.custom_qty)
async def process_custom_qty(msg: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    item_id = data.get("target_item_id") or data.get("item_id")
    prompt_msg_id = data.get("prompt_msg_id")
    
    val_text = msg.text.strip() if msg.text else ""
    back_kb = InlineKeyboardMarkup(inline_keyboard=[[IBtn(text="Back", callback_data=f"sel_item_{item_id}", style="danger", icon_custom_emoji_id="5352759161945867747")]])
    
    if not val_text.isdigit() or int(val_text) <= 0:
        return await msg.answer("❌ សូមវាយបញ្ចូលចំនួនជាលេខត្រឹមត្រូវ (ឧទាហរណ៍: 2)៖", reply_markup=back_kb)
        
    qty = int(val_text)
    stock_qty = get_item_stock(item_id)
    
    if stock_qty < 9999 and qty > stock_qty:
        return await msg.answer(f"❌ ស្តុកមិនគ្រប់គ្រាន់ទេ! (ស្តុកនៅសល់៖ {stock_qty})", reply_markup=back_kb)
        
    await state.clear()
    try: await msg.delete()
    except: pass
    await render_checkout(msg, item_id, qty, is_edit=False, old_msg_id=prompt_msg_id, current_bot=bot)

# ----------------- BAKONG CHECKOUT FLOW (UPDATED API) -----------------
@dp.callback_query(F.data.startswith("bakongpay_"))
async def handle_bakong_pay(call: CallbackQuery, bot: Bot):
    try:
        await call.answer()
    except:
        pass
    parts = call.data.split("_")
    item_id, qty = int(parts[1]), int(parts[2])
    uid = call.from_user.id
    if has_active_pending_qr(uid):
        try: await call.answer("⏳ QR មានមួយហើយអ្នកបង្កើតនៅខាងលើមិញសូមអ្នកយក QR ខាងលើនឹងទៅផេរទៅ ទាល់តែ QR នឹងផុតកំណត់ ឬ ចុចបោះបង់វាទើបបងអាច បង្កើត QR ម្ដងទៀតបាន"[:195], show_alert=True)
        except Exception: pass
        return await call.message.answer("⏳ QR មានមួយហើយអ្នកបង្កើតនៅខាងលើមិញសូមអ្នកយក QR ខាងលើនឹងទៅផេរទៅ ទាល់តែ QR នឹងផុតកំណត់ ឬ ចុចបោះបង់វាទើបបងអាច បង្កើត QR ម្ដងទៀតបាន")
    
    stock_qty = get_item_stock(item_id)
    if qty > stock_qty:
        return await call.message.answer(f"❌ ស្តុកមិនគ្រប់គ្រាន់ទេ! (មាន {stock_qty})")
        
    res_usr = execute_db('SELECT is_reseller, is_reseller_vip FROM users WHERE id=?', (uid,), fetch=True)
    is_res = res_usr[0] if (res_usr and res_usr[0]) else 0
    is_vip = res_usr[1] if (res_usr and len(res_usr) > 1 and res_usr[1]) else 0
    
    item = execute_db('''SELECT items.name, items.price, items.reseller_price, categories.name, items.reseller_vip_price FROM items JOIN categories ON items.cat_id = categories.id WHERE items.id=?''', (item_id,), fetch=True)
    if not item:
        return await call.message.answer("❌ មិនមានទិន្នន័យទំនិញនេះទេ!")
        
    cat_name, item_name = item[3], item[0]
    vip_p = item[4] if (len(item) > 4 and item[4] and item[4] > 0) else 0.0
    if is_vip and vip_p > 0: u_price = vip_p
    elif is_res: u_price = item[2]
    else: u_price = item[1]
    total = u_price * qty

    try:
        loading_msg = await call.message.edit_text("<tg-emoji emoji-id=\"6316599954026535998\">🏦</tg-emoji> <b>QR បាគង (KHQR) កំពុងទាញចេញពីប្រព័ន្ធ API សូមរង់ចាំ...</b>")
    except:
        loading_msg = await call.message.answer("<tg-emoji emoji-id=\"6316599954026535998\">🏦</tg-emoji> <b>QR បាគង (KHQR) កំពុងទាញចេញពីប្រព័ន្ធ API សូមរង់ចាំ...</b>")
        
    ref_id = f"bkg_{uid}_{int(time.time())}"
    
    # 🚀 ទាញយក QR ពីប្រព័ន្ធ API ពិតៗ (ហាមដាច់ខាតមិនឱ្យ bot បង្កើត QR ដោយខ្លួនឯង)
    res = await bakong_fetch_api_qr(total, ref_id)
    
    if not res:
        err_msg = "<tg-emoji emoji-id=\"6100333528740801952\">⚠️</tg-emoji> <b>មិនអាចទាញយក QR ពីប្រព័ន្ធ API បាគងបានទេ!</b>\nសូមមេត្តាពិនិត្យមើលប្រព័ន្ធ API ឬទាក់ទង Admin។"
        try:
            await loading_msg.edit_text(err_msg)
        except:
            await call.message.answer(err_msg)
        return

    qr_image_url = res.get("qr_image_url")
    qr_string = res.get("qr_string")
    payment_id = res.get("transaction_id") or ref_id

    photo_input = None
    # ១. ប្រសិនបើ API ផ្ដល់ URL រូបភាព ទាញយករូបភាពពិតពី Server ផ្ទាល់
    if qr_image_url and str(qr_image_url).startswith("http"):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(str(qr_image_url).strip(), timeout=12) as img_resp:
                    if img_resp.status == 200:
                        photo_input = BufferedInputFile(await img_resp.read(), filename="bakong_qr.png")
        except Exception as e:
            logger.warning(f"Error downloading qr_image_url from server: {e}")

    # ២. ប្រសិនបើ API ផ្ដល់កូដ QR String បង្កើតរូបភាព QR ស-ខ្មៅសុទ្ធតាមកូដពិតចេញពី API
    if not photo_input and qr_string:
        try:
            photo_input = BufferedInputFile(create_clean_qr_image(qr_string), filename="bakong_qr.png")
        except Exception as e:
            logger.error(f"Error making QR image from API string: {e}")

    safe_cat = escape_html(cat_name)
    safe_item = escape_html(item_name)
    
    cap = f"""<tg-emoji emoji-id="5258049708525380488">🎮</tg-emoji> Game : <b>{safe_cat}</b>
<tg-emoji emoji-id="6242308461598610637">📦</tg-emoji> item : <b>{safe_item}</b>
<tg-emoji emoji-id="6235459831302460476">💰</tg-emoji> តម្លៃ : <b>${total:.2f}</b>
<tg-emoji emoji-id="5445195276291693508">✅</tg-emoji> សូមស្កេន QR បាគង (KHQR) នេះក្នុង App ធនាគារណាក៏បាន (Bakong, ABA, Wing, ACLEDA...)
<tg-emoji emoji-id="6095690437165586962">🏦</tg-emoji> ពេលផ្ទេររួចរាល់ ចុច "Verify Payment" ខាងក្រោមដើម្បីទទួលបានទំនិញភ្លាមៗ!
<tg-emoji emoji-id="5422814644093868925">🔖</tg-emoji> Ref ID : <code>{str(payment_id)[:20]}</code>  
<tg-emoji emoji-id="6253758805755038090">⏳</tg-emoji> QR ផុតសុពលភាព : 10 : 00 នាទី"""

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="Verify Payment", callback_data=f"vfy_bkg_{payment_id}", style="success", icon_custom_emoji_id="5904704361182798355", btn_key="vfy_bkg")],
        [IBtn(text="Cancel QR / បោះបង់ QR", callback_data=f"cancel_qr_{payment_id}", style="danger", icon_custom_emoji_id="6176808917549453468", btn_key="cancel_qr")]
    ])

    if loading_msg:
        try: await loading_msg.delete()
        except: pass
        
    sent_msg = None
    if photo_input:
        try:
            sent_msg = await bot.send_photo(call.message.chat.id, photo=photo_input, caption=cap, reply_markup=kb)
        except Exception as e:
            logger.error(f"Error send_photo bakong: {e}")
            try:
                sent_msg = await bot.send_message(call.message.chat.id, cap, reply_markup=kb)
            except Exception as e2:
                logger.error(f"Error send_message bakong fallback: {e2}")
    else:
        try:
            sent_msg = await bot.send_message(call.message.chat.id, cap, reply_markup=kb)
        except Exception as e:
            logger.error(f"Error send_message bakong: {e}")

    sent_msg_id = sent_msg.message_id if sent_msg else None
    execute_db("""INSERT OR REPLACE INTO pending_payments 
                  (payment_id, pay_type, user_id, chat_id, item_id, qty, msg_id, total, item_name, created_at, is_done) 
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""", 
               (str(payment_id), 'bakong', uid, call.message.chat.id, item_id, qty, sent_msg_id, total, item_name, time.time()))

    db_ctx, owner_ctx, clone_ctx = current_db_var.get(), current_owner_var.get(), is_clone_var.get()
    run_bg_task(poll_bakong_payment(call, uid, call.message.chat.id, payment_id, item_id, qty, sent_msg_id, total, item_name, bot, db_ctx, owner_ctx, clone_ctx))

@dp.callback_query(F.data.startswith("abapay_"))
async def handle_aba_pay(call: CallbackQuery, bot: Bot):
    try:
        await call.answer()
    except Exception:
        pass
    parts = call.data.split("_")
    item_id, qty = int(parts[1]), int(parts[2])
    uid = call.from_user.id
    if has_active_pending_qr(uid):
        try: await call.answer("⏳ QR មានមួយហើយអ្នកបង្កើតនៅខាងលើមិញសូមអ្នកយក QR ខាងលើនឹងទៅផេរទៅ ទាល់តែ QR នឹងផុតកំណត់ ឬ ចុចបោះបង់វាទើបបងអាច បង្កើត QR ម្ដងទៀតបាន"[:195], show_alert=True)
        except Exception: pass
        return await call.message.answer("⏳ QR មានមួយហើយអ្នកបង្កើតនៅខាងលើមិញសូមអ្នកយក QR ខាងលើនឹងទៅផេរទៅ ទាល់តែ QR នឹងផុតកំណត់ ឬ ចុចបោះបង់វាទើបបងអាច បង្កើត QR ម្ដងទៀតបាន")
    
    stock_qty = get_item_stock(item_id)
    if qty > stock_qty:
        return await call.answer(f"❌ ស្តុកមិនគ្រប់គ្រាន់ទេ! (មាន {stock_qty})", show_alert=True)
        
    res_usr = execute_db('SELECT is_reseller, is_reseller_vip FROM users WHERE id=?', (uid,), fetch=True)
    is_res = res_usr[0] if (res_usr and res_usr[0]) else 0
    is_vip = res_usr[1] if (res_usr and len(res_usr) > 1 and res_usr[1]) else 0
    
    item = execute_db('''SELECT items.name, items.price, items.reseller_price, categories.name, items.reseller_vip_price FROM items JOIN categories ON items.cat_id = categories.id WHERE items.id=?''', (item_id,), fetch=True)
    cat_name, item_name = item[3], item[0]
    vip_p = item[4] if (len(item) > 4 and item[4] and item[4] > 0) else 0.0
    if is_vip and vip_p > 0: u_price = vip_p
    elif is_res: u_price = item[2]
    else: u_price = item[1]
    total = u_price * qty
    
    try: loading_msg = await call.message.edit_text("<tg-emoji emoji-id=\"6316599954026535998\">🏦</tg-emoji> <b>QR និងបង្កើតសូមរង់ចាំ…..</b>")
    except: loading_msg = await call.message.answer("<tg-emoji emoji-id=\"6316599954026535998\">🏦</tg-emoji> <b>QR និងបង្កើតសូមរង់ចាំ…..</b>")
    
    ref_id = f"znt_{uid}_{int(time.time())}"
    uname_arg = call.from_user.username or f"user_{uid}"
    try:
        res = await aba_generate_qr_async(total, ref_id, username=uname_arg)
    except Exception as e:
        logger.error(f"Error in aba_generate_qr_async: {e}")
        res = None
    
    if not res or (not res.get("payment_id") and not res.get("qr_string") and not res.get("qr_image")):
        api_key = (os.getenv('ABA_WEBSITE_API_KEY', '') or get_setting('aba_api_key', '') or '').strip()
        merchant_id = (os.getenv('ABA_MERCHANT_ID', '') or get_setting('aba_merchant_id', '') or '').strip()
        if not api_key or not merchant_id:
            err_msg = "<tg-emoji emoji-id=\"6100333528740801952\">⚠️</tg-emoji> សូមមេត្តាកំណត់ ABA API Key និង Merchant ID នៅក្នុង Setting Payment ABA ជាមុនសិន!"
        else:
            err_msg = "<tg-emoji emoji-id=\"6100333528740801952\">⚠️</tg-emoji> ប្រព័ន្ធធនាគារ ABA PAY កំពុងរវល់…សូមរង់ចាំ\n<tg-emoji emoji-id=\"6314519407443845610\">🏦</tg-emoji> ឬបង្កើត QR ម្តងទៀត៖"
        try: await loading_msg.edit_text(err_msg)
        except: pass
        return
        
    payment_id = res.get("payment_id") or res.get("transaction_id") or res.get("id")
    qr_image = res.get("qr_image") or res.get("card_image")
    pay_url = res.get("pay_url")
    qr_string = res.get("qr_string")
    
    cap = f"""Payment Summary 
━━━━━━━━━━━━━━━━━━━━━
Item: {cat_name}
Plan: {item_name}
Quantity: {qty}
Unit Price: ${u_price:.2f}
Total Price: ${total:.2f}
Payment ID: <code>{payment_id}</code>
Method: Instant Delivery (ABA Pay)
━━━━━━━━━━━━━━━━━━━━━
Scan the KHQR to pay. Your order will be fulfilled automatically after confirmation."""

    photo_input = None
    if qr_string:
        try:
            img_bytes = create_clean_qr_image(qr_string)
            photo_input = BufferedInputFile(img_bytes, filename="khqr.png")
        except Exception as e:
            logger.error(f"create_clean_qr_image failed: {e}")

    if not photo_input and qr_image:
        if str(qr_image).startswith("http"):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(str(qr_image).strip(), timeout=15) as qresp:
                        if qresp.status == 200:
                            photo_input = BufferedInputFile(await qresp.read(), filename="aba_qr.png")
            except Exception:
                photo_input = str(qr_image).strip()
        else:
            try:
                b64_str = qr_image.split(",")[1] if "," in qr_image else qr_image
                photo_input = BufferedInputFile(base64.b64decode(b64_str), filename="aba_qr.png")
            except: pass
                
    aba_url = await resolve_aba_app_url(res, payment_id, qr_string)

    kb_rows = [
        [IBtn(text="បើក  App ABA ទូរទាត់", url=aba_url, style="primary", icon_custom_emoji_id="6325675417491481533", btn_key="open_aba")],
        [IBtn(text="Cancel QR", callback_data=f"cancel_qr_{payment_id}", style="danger", icon_custom_emoji_id="6102914615107133393", btn_key="cancel_qr")]
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    sent_msg = None
    if photo_input:
        try:
            sent_msg = await bot.send_photo(call.message.chat.id, photo=photo_input, caption=cap, reply_markup=kb)
        except Exception as e:
            logger.warning(f"Error send_photo aba with direct link: {e}")

    if not sent_msg:
        try:
            sent_msg = await bot.send_message(call.message.chat.id, cap, reply_markup=kb)
        except Exception as e:
            logger.warning(f"Error send_message aba with direct link: {e}")
            
    if not sent_msg:
        fallback_aba = aba_url
        fb_rows = [
            [IBtn(text="បើក  App ABA ទូរទាត់", url=fallback_aba, style="primary", icon_custom_emoji_id="6325675417491481533", btn_key="open_aba")],
            [IBtn(text="Cancel QR", callback_data=f"cancel_qr_{payment_id}", style="danger", icon_custom_emoji_id="6102914615107133393", btn_key="cancel_qr")]
        ]
        kb_fb = InlineKeyboardMarkup(inline_keyboard=fb_rows)
        try:
            if photo_input:
                sent_msg = await bot.send_photo(call.message.chat.id, photo=photo_input, caption=cap, reply_markup=kb_fb)
            else:
                sent_msg = await bot.send_message(call.message.chat.id, cap, reply_markup=kb_fb)
        except Exception as e:
            logger.error(f"Error sending aba fallback: {e}")
            safe_kb = InlineKeyboardMarkup(inline_keyboard=[
                [IBtn(text="Cancel QR", callback_data=f"cancel_qr_{payment_id}", style="danger", icon_custom_emoji_id="6102914615107133393", btn_key="cancel_qr")]
            ])
            if photo_input:
                sent_msg = await bot.send_photo(call.message.chat.id, photo=photo_input, caption=cap, reply_markup=safe_kb)
            else:
                sent_msg = await bot.send_message(call.message.chat.id, cap, reply_markup=safe_kb)

    # លុបសារ loading_msg ក្រោយពេលសារ QR ត្រូវបានផ្ញើជោគជ័យ
    if loading_msg:
        try: await loading_msg.delete()
        except: pass

    execute_db("""INSERT OR REPLACE INTO pending_payments 
                  (payment_id, pay_type, user_id, chat_id, item_id, qty, msg_id, total, item_name, created_at, is_done) 
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""", 
               (str(payment_id), 'aba', uid, call.message.chat.id, item_id, qty, sent_msg.message_id, total, item_name, time.time()))
        
    db_ctx, owner_ctx, clone_ctx = current_db_var.get(), current_owner_var.get(), is_clone_var.get()
    run_bg_task(poll_aba_payment(call, uid, call.message.chat.id, payment_id, item_id, qty, sent_msg.message_id, total, item_name, bot, db_ctx, owner_ctx, clone_ctx))
    await call.answer()

async def poll_aba_payment(call, uid, chat_id, payment_id, item_id, qty, msg_id, total_paid, item_name, current_bot: Bot, db_ctx, owner_ctx, clone_ctx):
    current_db_var.set(db_ctx)
    current_owner_var.set(owner_ctx)
    is_clone_var.set(clone_ctx)
    timeout = time.time() + 180
    while time.time() < timeout:
        # Check if already processed by manual verify or cancelled
        p_row = execute_db('SELECT is_done FROM pending_payments WHERE payment_id=?', (str(payment_id),), fetch=True)
        if p_row and p_row[0] != 0:
            return

        paid = await aba_check_paid_async(payment_id)
        if paid:
            execute_db('UPDATE pending_payments SET is_done=1 WHERE payment_id=?', (str(payment_id),))
            await aba_mark_credited_async(payment_id)
            await deliver_item(call, uid, chat_id, item_id, qty, msg_id, total_paid, item_name, current_bot)
            return
        await asyncio.sleep(5) # ឆែក 5 វិនាទីម្ដង

    p_row = execute_db('SELECT is_done FROM pending_payments WHERE payment_id=?', (str(payment_id),), fetch=True)
    if p_row and p_row[0] == 0:
        execute_db('UPDATE pending_payments SET is_done=3 WHERE payment_id=?', (str(payment_id),))
        try:
            await current_bot.delete_message(chat_id, msg_id)
            await current_bot.send_message(chat_id, "🧭 QR ដែលអ្នកបានបង្កើតមុននឹងផុតកំណត់ហើយ ( 3នាទី ) សូមបងចូលទៅបង្កើតQRម្ដងទៀតដើម្បីផេរ៖")
        except: pass

async def poll_bakong_payment(call, uid, chat_id, payment_id, item_id, qty, msg_id, total_paid, item_name, current_bot: Bot, db_ctx, owner_ctx, clone_ctx):
    current_db_var.set(db_ctx)
    current_owner_var.set(owner_ctx)
    is_clone_var.set(clone_ctx)
    start_time = time.time()
    timeout = start_time + 600
    while time.time() < timeout:
        p_row = execute_db('SELECT is_done FROM pending_payments WHERE payment_id=?', (str(payment_id),), fetch=True)
        if p_row and p_row[0] != 0:
            return

        paid = await bakong_check_paid_async(payment_id)
        if paid:
            execute_db('UPDATE pending_payments SET is_done=1 WHERE payment_id=?', (str(payment_id),))
            await deliver_item(call, uid, chat_id, item_id, qty, msg_id, total_paid, item_name, current_bot)
            return

        await asyncio.sleep(5)

    p_row = execute_db('SELECT is_done FROM pending_payments WHERE payment_id=?', (str(payment_id),), fetch=True)
    if p_row and p_row[0] == 0:
        execute_db('UPDATE pending_payments SET is_done=3 WHERE payment_id=?', (str(payment_id),))
        try:
            if msg_id:
                await current_bot.delete_message(chat_id, msg_id)
            await current_bot.send_message(chat_id, "🧭 QR បាគង ដែលអ្នកបានបង្កើតមុននេះផុតកំណត់ហើយ (10 នាទី) សូមចូលទៅបង្កើត QR ម្តងទៀតដើម្បីទូទាត់៖")
        except: pass

async def deliver_item(call, uid, chat_id, item_id, qty, msg_id, total_paid, item_name, current_bot: Bot):
    inf_chk = execute_db('SELECT is_infinite, infinite_data FROM items WHERE id=?', (item_id,), fetch=True)
    is_inf = inf_chk[0] if inf_chk and inf_chk[0] else 0
    inf_val = inf_chk[1] if inf_chk and len(inf_chk) > 1 else ""
    
    if is_inf and inf_val:
        key_text = ""
        if inf_val.startswith("text:"):
            k_val = inf_val.split("text:", 1)[1]
            key_text = f"- <tg-emoji emoji-id=\"5257969839313526622\">🔑</tg-emoji> <code>{k_val}</code>\n"
            keys_saved = k_val
        else:
            m_type, m_id = inf_val.split(':', 1)
            key_text = f"- <tg-emoji emoji-id=\"5257969839313526622\">🔑</tg-emoji> <code>[ឯកសារស្តុកមិនចេះអស់]</code>\n"
            keys_saved = inf_val
            try:
                if m_type == 'photo': await current_bot.send_photo(chat_id, m_id, caption="នេះគឺជាឯកសាររបស់អ្នក!")
                elif m_type == 'video': await current_bot.send_video(chat_id, m_id, caption="នេះគឺជាឯកសាររបស់អ្នក!")
                elif m_type == 'document': await current_bot.send_document(chat_id, m_id, caption="នេះគឺជាឯកសាររបស់អ្នក!")
            except: pass
        execute_db('INSERT INTO orders (user_id, item_id, qty, total_price, date, key_data) VALUES (?, ?, ?, ?, ?, ?)', (uid, item_id, qty, total_paid, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), keys_saved))
    else:
        stocks = execute_db('SELECT id, key_data, type FROM stock WHERE item_id=? AND is_sold=0 LIMIT ?', (item_id, qty), fetchall=True)
        if len(stocks) < qty:
            return await current_bot.send_message(chat_id, "❌ ស្តុកត្រូវបានទិញអស់លឿនពេក! សូមទាក់ទង Admin។")
            
        keys_bought = [s[1] for s in stocks]
        keys_saved = "\n".join(keys_bought)
        execute_db('INSERT INTO orders (user_id, item_id, qty, total_price, date, key_data) VALUES (?, ?, ?, ?, ?, ?)', (uid, item_id, qty, total_paid, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), keys_saved))
                   
        key_text = ""
        for s in stocks:
            execute_db('UPDATE stock SET is_sold=1 WHERE id=?', (s[0],))
            if s[2] == 'text': key_text += f"- <tg-emoji emoji-id=\"5257969839313526622\">🔑</tg-emoji> <code>{s[1]}</code>\n"
            else:
                m_type, m_id = s[1].split(':', 1)
                try:
                    if m_type == 'photo': await current_bot.send_photo(chat_id, m_id, caption="នេះគឺជាឯកសាររបស់អ្នក!")
                    elif m_type == 'video': await current_bot.send_video(chat_id, m_id, caption="នេះគឺជាឯកសាររបស់អ្នក!")
                    elif m_type == 'document': await current_bot.send_document(chat_id, m_id, caption="នេះគឺជាឯកសាររបស់អ្នក!")
                except: pass
        
    row_cat = execute_db('SELECT c.name FROM items i JOIN categories c ON i.cat_id = c.id WHERE i.id=?', (item_id,), fetch=True)
    cat_name = row_cat[0] if row_cat else "Unknown"
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    u_info = execute_db('SELECT username, first_name, is_admin, is_reseller, is_reseller_vip FROM users WHERE id=?', (uid,), fetch=True)
    uname = f"@{u_info[0]}" if (u_info and u_info[0]) else (u_info[1] if (u_info and u_info[1]) else str(uid))
    is_adm = (u_info and u_info[2] == 1) or (uid == get_current_owner())
    is_res = (u_info and u_info[3] == 1)
    is_vip = (u_info and len(u_info) > 4 and u_info[4] == 1)
    if is_adm:
        role_str = '<tg-emoji emoji-id="6314076231243404806">👑</tg-emoji> admin'
    elif is_vip:
        role_str = '<tg-emoji emoji-id="6314076231243404806">👑</tg-emoji> Reseller VIP'
    elif is_res:
        role_str = '<tg-emoji emoji-id="6314076231243404806">👑</tg-emoji> reseller'
    else:
        role_str = '<tg-emoji emoji-id="6314076231243404806">👤</tg-emoji> Member'

    last_order = execute_db('SELECT id FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 1', (uid,), fetch=True)
    order_id_val = last_order[0] if last_order else int(time.time())

    kh_now = datetime.utcnow() + timedelta(hours=7)
    time_str = kh_now.strftime("%d-%m-%Y %I:%M:%S %p")

    msg = f"""<tg-emoji emoji-id="5445195276291693508">✅</tg-emoji> <b>Payment Verified!</b>
<tg-emoji emoji-id="5197269100878907942">🧾</tg-emoji> <b>Orders ID :</b> <code>{order_id_val}</code>
<tg-emoji emoji-id="5409250385753829649">👤</tg-emoji> <b>User :</b> {uname}
<tg-emoji emoji-id="5287231198098117669">🔰</tg-emoji> <b>Role :</b> {role_str}
<tg-emoji emoji-id="5258049708525380488">🎮</tg-emoji> <b>Game :</b> {cat_name}
<tg-emoji emoji-id="5431897022456145283">⏱</tg-emoji> <b>Duration :</b> {item_name}
<tg-emoji emoji-id="5413395871008058098">🔑</tg-emoji> <b>Key :</b>
{key_text}
<tg-emoji emoji-id="6242308461598610637">⏰</tg-emoji> <b>Time :</b> {time_str}
<tg-emoji emoji-id="5445195276291693508">✅</tg-emoji> <b>Status:</b> Completed (Auto)
<tg-emoji emoji-id="5436040291507247633">🙏</tg-emoji> <b>Thank you for your purchase!</b>"""

    if msg_id:
        try: await current_bot.delete_message(chat_id, msg_id)
        except: pass
    await current_bot.send_message(chat_id, msg)
    
    row_pm = execute_db('SELECT post_media FROM items WHERE id=?', (item_id,), fetch=True)
    post_media = row_pm[0] if row_pm else None
    if post_media:
        media_list = []
        try:
            loaded = json.loads(post_media)
            if isinstance(loaded, list): media_list = loaded
            elif isinstance(loaded, dict): media_list = [loaded]
        except:
            if ':' in post_media:
                m_type, content = post_media.split(':', 1)
                media_list = [{'type': m_type, 'content': content, 'caption': None}]
        
        for pm in media_list:
            m_type, content, cap = pm.get('type'), pm.get('content'), pm.get('caption') or None
            try:
                if m_type == 'photo': await current_bot.send_photo(chat_id, content, caption=cap)
                elif m_type == 'video': await current_bot.send_video(chat_id, content, caption=cap)
                elif m_type == 'document': await current_bot.send_document(chat_id, content, caption=cap)
                elif m_type == 'audio': await current_bot.send_audio(chat_id, content, caption=cap)
                elif m_type == 'voice': await current_bot.send_voice(chat_id, content, caption=cap)
                elif m_type == 'text': await current_bot.send_message(chat_id, content)
            except: pass

    user_row = execute_db('SELECT first_name, username FROM users WHERE id=?', (uid,), fetch=True)
    u_name = user_row[0] if user_row and user_row[0] else "Unknown"
    u_user = f"@{user_row[1]}" if user_row and user_row[1] else "គ្មាន"
    
    row_cat_info = execute_db('SELECT c.name FROM items i JOIN categories c ON i.cat_id = c.id WHERE i.id=?', (item_id,), fetch=True)
    c_name_bought = row_cat_info[0] if row_cat_info else "ផលលិតផល"
    
    kh_now = datetime.utcnow() + timedelta(hours=7)
    order_time_str = kh_now.strftime("%d-%m-%Y %I:%M:%S %p")

    alert_txt = f"""━━━━━━━━━━━━━━━━━━━━
🛒 <b>ការកម្មង់ពីរអតថិជនថ្មី!</b>
━━━━━━━━━━━━━━━━━━━━
· លេខសម្គាល់អតិថិជន : <code>{uid}</code>
· ឈ្មោះអ្នកអតិថិជិត : <b>{u_name}</b> ({u_user})
· ផលលិតផល : <b>{c_name_bought}</b>
· កព្ចាប់ : <b>{item_name}</b>
· តម្លៃ : <b>${total_paid:.2f}</b>
· ចំនួនដែលបានទិញ : <b>{qty}</b>
· បានទិញនៅម៉ោង : <b>{order_time_str}</b>
━━━━━━━━━━━━━━━━━━━━ 
🙏 សូមអរគុណបងដែលបងបានគាំទ្រឆានែលរបស់យើង❤️! 
━━━━━━━━━━━━━━━━━━━━"""
    await alert_to_channel(alert_txt, current_bot)

    rem_stock = execute_db('SELECT COUNT(*) FROM stock WHERE item_id=? AND is_sold=0', (item_id,), fetch=True)[0]
    if rem_stock <= 3:
        item_row = execute_db('SELECT price, cat_id FROM items WHERE id=?', (item_id,), fetch=True)
        i_price = item_row[0] if item_row else 0.0
        c_name = execute_db('SELECT name FROM categories WHERE id=?', (item_row[1],), fetch=True)[0] if item_row else "ទំនិញ"
        alert = f"""<tg-emoji emoji-id=\"6143084439204275121\">🚨</tg-emoji> <b>ទំនិញជិតអស់ស្តុកទៀតហើយ - មានគេទិញច្រើនណាស់ !</b>
━━━━━━━━━━━━━━━━━━━━
· <tg-emoji emoji-id=\"6147552519452107586\">📦</tg-emoji> ផលលិតផល : <b>{c_name}</b>
· <tg-emoji emoji-id=\"6183573607004775460\">⏱</tg-emoji> កញ្ចប់ : <b>{item_name}</b>
· <tg-emoji emoji-id=\"6138932923815960721\">💰</tg-emoji> តម្លៃ : <b>${i_price:.2f}</b>
· <tg-emoji emoji-id=\"6138655185460797793\">⏳</tg-emoji> ស្តុកនៅសល់តែ : <b>{rem_stock}</b>
━━━━━━━━━━━━━━━━━━━━
· <tg-emoji emoji-id=\"6138702889662554181\">🏃</tg-emoji> រួសរាន់ឡើងទាន់ទំនិញនៅមានស្តុកយ័ត្នគេទិញអស់លឿនៗមក!
· <tg-emoji emoji-id=\"6138677811348513089\">✨</tg-emoji> រួចរាល់សម្រាប់ការទិញស្តុកនឹងនៅសូមចុចបូតុង <tg-emoji emoji-id=\"5312361253610475399\">🛒</tg-emoji> <b>BUY NOW</b> ខាងក្រោមដើម្បីទិញ!"""
        if rem_stock == 0: alert = alert.replace("ទំនិញជិតអស់ស្តុកទៀតហើយ", "ទំនិញត្រូវបានលក់អស់ហើយ")
        kb = InlineKeyboardMarkup(inline_keyboard=[[IBtn(text="Buy Now / ទិញឥឡូវនេះ", callback_data="buy_now_direct", style="primary", icon_custom_emoji_id="5445146945024720188")]])
        users = execute_db('SELECT id FROM users', fetchall=True)
        for u in users:
            try: await current_bot.send_message(u[0], alert, reply_markup=kb)
            except: pass

# --- VERIFY PAYMENT & CANCEL QR HANDLERS ---
@dp.callback_query(F.data.startswith("vfy_aba_"))
async def verify_aba_handler(call: CallbackQuery, bot: Bot):
    payment_id = call.data.replace("vfy_aba_", "")
    row = execute_db("SELECT user_id, chat_id, item_id, qty, msg_id, total, item_name, is_done FROM pending_payments WHERE payment_id=?", (payment_id,), fetch=True)
    if not row:
        return await call.answer("❌ មិនមានទិន្នន័យ QR នេះទេ ឬផុតកំណត់ហើយ!", show_alert=True)
    
    uid, chat_id, item_id, qty, msg_id, total, item_name, is_done = row
    if is_done == 1:
        return await call.answer("✅ ការទូទាត់ត្រូវបានផ្ទៀងផ្ទាត់ និងប្រគល់ទំនិញរួចរាល់ហើយ!", show_alert=True)
    if is_done == 2:
        return await call.answer("❌ QR នេះត្រូវបានបោះបង់រួចហើយ!", show_alert=True)

    paid = await aba_check_paid_async(payment_id)
    if paid:
        execute_db("UPDATE pending_payments SET is_done=1 WHERE payment_id=?", (payment_id,))
        await aba_mark_credited_async(payment_id)
        await deliver_item(call, uid, chat_id, item_id, qty, msg_id, total, item_name, bot)
        await call.answer("✅ ការទូទាត់ទទួលបានជោគជ័យ! ទំនិញត្រូវបានទម្លាក់ជូនហើយ។", show_alert=True)
    else:
        await call.answer("❌ មិនទាន់ឃើញការបង់ប្រាក់ទេ! សូមបាញ់ប្រាក់សិន រួចចុច Verify Payment ម្តងទៀត។", show_alert=True)

@dp.callback_query(F.data.startswith("vfy_bkg_"))
async def verify_bakong_handler(call: CallbackQuery, bot: Bot):
    payment_id = call.data.replace("vfy_bkg_", "")
    row = execute_db("SELECT user_id, chat_id, item_id, qty, msg_id, total, item_name, is_done FROM pending_payments WHERE payment_id=?", (payment_id,), fetch=True)
    if not row:
        return await call.answer("❌ មិនមានទិន្នន័យ QR នេះទេ ឬផុតកំណត់ហើយ!", show_alert=True)
    
    uid, chat_id, item_id, qty, msg_id, total, item_name, is_done = row
    if is_done == 1:
        return await call.answer("✅ ការទូទាត់ត្រូវបានផ្ទៀងផ្ទាត់ និងប្រគល់ទំនិញរួចរាល់ហើយ!", show_alert=True)
    if is_done == 2:
        return await call.answer("❌ QR នេះត្រូវបានបោះបង់រួចហើយ!", show_alert=True)

    paid = await bakong_check_paid_async(payment_id)
    if paid:
        execute_db("UPDATE pending_payments SET is_done=1 WHERE payment_id=?", (payment_id,))
        await deliver_item(call, uid, chat_id, item_id, qty, msg_id, total, item_name, bot)
        await call.answer("✅ ការទូទាត់ទទួលបានជោគជ័យ! ទំនិញត្រូវបានទម្លាក់ជូនហើយ។", show_alert=True)
    else:
        await call.answer("❌ មិនទាន់ឃើញការបង់ប្រាក់ទេ! សូមបាញ់ប្រាក់សិន រួចចុច Verify Payment ម្តងទៀត។", show_alert=True)

@dp.callback_query(F.data.startswith("cancel_qr_"))
async def cancel_qr_handler(call: CallbackQuery, bot: Bot):
    payment_id = call.data.replace("cancel_qr_", "")
    execute_db("UPDATE pending_payments SET is_done=2 WHERE payment_id=?", (payment_id,))
    try:
        await call.message.delete()
    except:
        pass
    await call.message.answer("<tg-emoji emoji-id=\"6176808917549453468\">❌</tg-emoji> <b>អ្នកបានបោះបង់ការទូទាត់ QR នេះរួចរាល់ហើយ!</b>")
    await call.answer("❌ បានបោះបង់ QR!", show_alert=True)

@dp.callback_query(F.data == "buy_now_direct")
async def buy_now_direct_btn(call: CallbackQuery, bot: Bot):
    await send_categories(call, bot)
    await call.answer()

# ====================================================================================================
# [ 💰 PAY BALANCE / TOP UP / BALANCE / MY ORDERS ]
# ====================================================================================================

@dp.callback_query(F.data.startswith("paybal_"))
async def handle_pay_balance(call: CallbackQuery, bot: Bot):
    parts = call.data.split("_")
    item_id, qty = int(parts[1]), int(parts[2])
    uid = call.from_user.id

    stock_qty = get_item_stock(item_id)
    if qty > stock_qty:
        return await call.answer(f"❌ ស្តុកមិនគ្រប់គ្រាន់ទេ! (មាន {stock_qty})", show_alert=True)

    res_usr = execute_db('SELECT is_reseller, is_reseller_vip, COALESCE(balance, 0.0) FROM users WHERE id=?', (uid,), fetch=True)
    is_res = res_usr[0] if (res_usr and res_usr[0]) else 0
    is_vip = res_usr[1] if (res_usr and len(res_usr) > 1 and res_usr[1]) else 0
    user_bal = float(res_usr[2] if (res_usr and len(res_usr) > 2 and res_usr[2] is not None) else 0.0)

    item = execute_db('SELECT name, price, reseller_price, reseller_vip_price FROM items WHERE id=?', (item_id,), fetch=True)
    if not item:
        return await call.answer("❌ មិនមានទិន្នន័យទំនិញនេះទេ!", show_alert=True)

    item_name = item[0]
    vip_p = item[3] if (len(item) > 3 and item[3] and item[3] > 0) else 0.0
    if is_vip and vip_p > 0: u_price = vip_p
    elif is_res: u_price = item[2]
    else: u_price = item[1]
    total = round(u_price * qty, 2)

    if user_bal < total:
        err_txt = (
            f"❌ សូមអភ័យទោសបងប្រុសបងមិនទាន់មានសមតុល្យគ្រប់គ្រាន់សម្រាប់ទិញតាម Pay Balance នោះតេ "
            f"បងមាន ${user_bal:.2f} / ${total:.2f} សូមបងចុច វិធីបង់ប្រាក់តាមវិធីផ្សេងទៅណា👃"
        )
        try:
            await call.answer(err_txt[:195], show_alert=True)
        except Exception:
            pass
        return await call.message.answer(err_txt)

    execute_db('UPDATE users SET balance = COALESCE(balance, 0.0) - ? WHERE id=?', (total, uid))
    await call.answer("✅ ទូទាត់តាម Pay Balance ជោគជ័យ!", show_alert=True)
    await deliver_item(call, uid, call.message.chat.id, item_id, qty, call.message.message_id, total, item_name, bot)

@dp.callback_query(F.data == "my_balance")
async def my_balance_handler(call: CallbackQuery):
    try: await call.answer()
    except Exception: pass
    uid = call.from_user.id
    row = execute_db('SELECT is_reseller, is_reseller_vip, COALESCE(balance, 0.0) FROM users WHERE id=?', (uid,), fetch=True)
    is_res = row[0] if (row and row[0]) else 0
    is_vip = row[1] if (row and len(row) > 1 and row[1]) else 0
    bal = float(row[2] if (row and len(row) > 2 and row[2] is not None) else 0.0)

    if is_vip:
        role_txt = "Reseller VIP"
    elif is_res:
        role_txt = "Reseller"
    else:
        role_txt = "Customers"

    text = render_clean_text(
        f'<tg-emoji emoji-id="6235459831302460476">💳</tg-emoji> <b>Balance / តុល្យភាព</b>\n\n'
        f'<tg-emoji emoji-id="5841276284155467413">👤</tg-emoji> <b>User ID:</b> <code>{uid}</code>\n'
        f'<tg-emoji emoji-id="5413395871008058098">🔰</tg-emoji> <b>Role:</b> {role_txt}\n'
        f'<tg-emoji emoji-id="6235459831302460476">💰</tg-emoji> <b>Your balance:</b> <code>${bal:.2f}</code>'
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="Top Up / បព្ចូាលទឹកប្រាក់", callback_data="topup_menu", style="primary", icon_custom_emoji_id="5447579253723918909", btn_key="topup")],
        [IBtn(text="Back", callback_data="back_to_start", style="danger", icon_custom_emoji_id="5447651546613449378")]
    ])
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except Exception:
        try: await call.message.delete()
        except Exception: pass
        await call.message.answer(text, reply_markup=kb)

def _orders_font(size: int, bold: bool = False):
    candidates = (
        ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", "arialbd.ttf"]
        if bold else
        ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "arial.ttf"]
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default(size)

def _wrap_cell_text(draw, text: str, font, max_w: int) -> list[str]:
    if not text:
        return [""]
    lines = []
    for raw_line in str(text).splitlines():
        words = raw_line.split(" ")
        cur = ""
        for w in words:
            test = (cur + " " + w).strip() if cur else w
            if draw.textlength(test, font=font) <= max_w:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                if draw.textlength(w, font=font) <= max_w:
                    cur = w
                else:
                    # Hard-break long key token
                    chunk = ""
                    for ch in w:
                        if draw.textlength(chunk + ch, font=font) <= max_w:
                            chunk += ch
                        else:
                            if chunk:
                                lines.append(chunk)
                            chunk = ch
                    cur = chunk
        if cur:
            lines.append(cur)
    return lines or [""]

def create_my_orders_image(orders: list, display_user: str) -> bytes:
    W = 1400
    margin_x = 45
    top_y = 42
    table_w = W - margin_x * 2

    # 6 columns matching reference table: Order ID | Product | Amount | Status | Key(s) | Date
    col_widths = [210, 210, 175, 195, 370, 200]  # sum = 1360? Adjust to table_w=1310
    col_widths = [205, 195, 165, 190, 360, 195]  # sum = 1310 = 1400 - 90
    headers = ["Order ID", "Product", "Amount", "Status", "Key(s)", "Date"]

    f_title = _orders_font(34, bold=True)
    f_sub = _orders_font(20, bold=False)
    f_hdr = _orders_font(20, bold=True)
    f_cell = _orders_font(19, bold=False)

    tmp_img = Image.new("RGB", (W, 400), (255, 255, 255))
    tmp_draw = ImageDraw.Draw(tmp_img)

    cell_pad_x = 12
    cell_pad_y = 14
    line_h = 26

    prepared_rows = []
    for o in orders:
        ord_id, qty, total_price, order_date, key_data, item_name, cat_name = o
        ord_str = f"ORD-{ord_id} (x{qty})"
        prod_str = f"{cat_name} - {item_name}" if cat_name else (item_name or "Package")
        amt_str = f"${float(total_price or 0):.2f}"
        status_str = "COMPLETED"
        raw_keys = [k.strip() for k in str(key_data or "").splitlines() if k.strip()]
        keys_str = ", ".join(raw_keys) if raw_keys else "-"
        date_str = str(order_date or "")[:16]

        vals = [ord_str, prod_str, amt_str, status_str, keys_str, date_str]
        wrapped_cols = [
            _wrap_cell_text(tmp_draw, vals[idx], f_cell, col_widths[idx] - cell_pad_x * 2)
            for idx in range(6)
        ]
        max_lines = max(len(c) for c in wrapped_cols)
        row_h = max(56, max_lines * line_h + cell_pad_y * 2)
        prepared_rows.append((wrapped_cols, row_h))

    hdr_h = 46
    table_top = 135
    total_rows_h = sum(rh for _, rh in prepared_rows)
    H = max(560, table_top + hdr_h + total_rows_h + 70)

    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)

    # Title & Generated Timestamp (UTC+7 Cambodia real time)
    now_kh = datetime.utcnow() + timedelta(hours=7)
    gen_str = now_kh.strftime("%d-%m-%Y %I:%M %p")
    d.text((margin_x, top_y), f"My Orders — {display_user}", font=f_title, fill=(17, 17, 17))
    d.text((margin_x, top_y + 46), f"Generated: {gen_str} · {len(orders)} order(s)", font=f_sub, fill=(102, 102, 102))

    # Draw Table Header (Dark Green #2E7D32)
    GREEN_HDR = (46, 125, 50)
    BORDER_GRAY = (140, 140, 140)
    d.rectangle([margin_x, table_top, margin_x + table_w, table_top + hdr_h], fill=GREEN_HDR, outline=BORDER_GRAY, width=1)

    cx = margin_x
    for idx, h_txt in enumerate(headers):
        d.text((cx + cell_pad_x, table_top + 11), h_txt, font=f_hdr, fill=(255, 255, 255))
        cx += col_widths[idx]
        if idx < 5:
            d.line([(cx, table_top), (cx, table_top + hdr_h)], fill=BORDER_GRAY, width=1)

    # Draw Data Rows
    cy = table_top + hdr_h
    for r_idx, (wrapped_cols, row_h) in enumerate(prepared_rows):
        row_bg = (255, 255, 255) if r_idx % 2 == 0 else (248, 250, 248)
        d.rectangle([margin_x, cy, margin_x + table_w, cy + row_h], fill=row_bg, outline=BORDER_GRAY, width=1)
        cx = margin_x
        for c_idx, lines_list in enumerate(wrapped_cols):
            ty = cy + cell_pad_y
            for ln in lines_list:
                d.text((cx + cell_pad_x, ty), ln, font=f_cell, fill=(20, 20, 20))
                ty += line_h
            cx += col_widths[c_idx]
            if c_idx < 5:
                d.line([(cx, cy), (cx, cy + row_h)], fill=BORDER_GRAY, width=1)
        cy += row_h

    bio = BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    return bio.getvalue()

@dp.callback_query(F.data == "my_orders_cb")
async def my_orders_cb_handler(call: CallbackQuery, state: FSMContext):
    try: await call.answer()
    except Exception: pass
    uid = call.from_user.id
    orders = execute_db("""
        SELECT o.id, o.qty, o.total_price, o.date, o.key_data, i.name, c.name
        FROM orders o
        LEFT JOIN items i ON o.item_id = i.id
        LEFT JOIN categories c ON i.cat_id = c.id
        WHERE o.user_id=?
        ORDER BY o.id DESC
        LIMIT 5
    """, (uid,), fetchall=True)

    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="Back", callback_data="back_to_start", style="danger", icon_custom_emoji_id="5447651546613449378")]
    ])
    if not orders:
        text = render_clean_text(
            '<tg-emoji emoji-id="5447387942995655277">🔑</tg-emoji> <b>មិនទាន់មានការបព្ជាទិញនៅឡើយតេ!</b>\n'
            '<tg-emoji emoji-id="6071226041454564573">🛒</tg-emoji> សូមចុចមុខងារ Buy Now ដើម្បីកម្មង់ទំនិញ!'
        )
        try: return await call.message.edit_text(text, reply_markup=back_kb)
        except Exception: return await call.message.answer(text, reply_markup=back_kb)

    display_user = f"@{call.from_user.username}" if call.from_user.username else (call.from_user.first_name or f"User_{uid}")
    try:
        img_bytes = create_my_orders_image(orders, display_user)
        try: await call.message.delete()
        except Exception: pass
        return await call.message.answer_photo(
            BufferedInputFile(img_bytes, filename="my_orders.png"),
            caption=f"📄 Your last {len(orders)} orders",
            reply_markup=back_kb
        )
    except Exception as e:
        logger.error(f"Error generating my_orders image: {e}")

    cards = []
    for o in orders:
        ord_id, qty, total_price, order_date, key_data, item_name, cat_name = o
        cat_name = escape_html(cat_name or "ហ្គេម")
        item_name = escape_html(item_name or "កញ្ចប់ទំនិញ")
        key_data = escape_html(key_data or "គ្មានទិន្នន័យ Key")
        order_date = order_date or ""
        cards.append(
            f'<tg-emoji emoji-id="5445023138297447592">📦</tg-emoji> <b>#{ord_id} | {cat_name} - {item_name}</b>\n'
            f'🔑 Key: <code>{key_data}</code>\n'
            f'💰 តម្លៃ: <b>${total_price:.2f}</b> | 📅 {order_date}'
        )
    full_txt = render_clean_text(
        '<tg-emoji emoji-id="5445023138297447592">📋</tg-emoji> <b>ការបព្ជាទិញរបស់ខ្ញុំ (5 ចុងក្រោយ)៖</b>\n━━━━━━━━━━━━━━━━━━━━━\n'
        + "\n━━━━━━━━━━━━━━━━━━━━━\n".join(cards)
    )
    try:
        await call.message.edit_text(full_txt, reply_markup=back_kb)
    except Exception:
        await call.message.answer(full_txt, reply_markup=back_kb)

@dp.callback_query(F.data == "topup_menu")
async def topup_menu_handler(call: CallbackQuery):
    try: await call.answer()
    except Exception: pass
    text = render_clean_text(
        '<tg-emoji emoji-id="5447579253723918909">💵</tg-emoji> <b>Top Up Balance</b>\n\nChoose an amount:'
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            IBtn(text="$10.00", callback_data="topup_amt_10.00", style="primary", icon_custom_emoji_id="5447579253723918909"),
            IBtn(text="$20.00", callback_data="topup_amt_20.00", style="primary", icon_custom_emoji_id="5447579253723918909"),
        ],
        [
            IBtn(text="$30.00", callback_data="topup_amt_30.00", style="primary", icon_custom_emoji_id="5447579253723918909"),
            IBtn(text="$40.00", callback_data="topup_amt_40.00", style="primary", icon_custom_emoji_id="5447579253723918909"),
        ],
        [
            IBtn(text="$50.00", callback_data="topup_amt_50.00", style="primary", icon_custom_emoji_id="5447579253723918909"),
        ],
        [IBtn(text="Back", callback_data="back_to_start", style="danger", icon_custom_emoji_id="5447651546613449378")]
    ])
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except Exception:
        try: await call.message.delete()
        except Exception: pass
        await call.message.answer(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("topup_amt_"))
async def topup_choose_method_handler(call: CallbackQuery):
    try: await call.answer()
    except Exception: pass
    amt = float(call.data.replace("topup_amt_", ""))
    aba_status = get_setting('aba_pay_status', 'on')
    bakong_status = get_setting('bakong_pay_status', 'off')
    mkhqr_status = get_setting('manual_khqr_status', 'off')

    rows = []
    if aba_status == 'on':
        rows.append([IBtn(text=f"Pay with ABA (${amt:.2f})", callback_data=f"topup_aba_{amt:.2f}", style="primary", icon_custom_emoji_id="6314519407443845610", btn_key="abapay")])
    if get_setting('khqrpay_pay_status', 'off') == 'on':
        rows.append([IBtn(text=f"Pay With ABA KHQR • ${amt:.2f}", callback_data=f"topup_khqrpay_{amt:.2f}", style="primary", icon_custom_emoji_id="6314519407443845610", btn_key="khqrpay")])
    if bakong_status == 'on':
        rows.append([IBtn(text=f"Pay with Bakong (${amt:.2f})", callback_data=f"topup_bkg_{amt:.2f}", style="primary", icon_custom_emoji_id="6095690437165586962", btn_key="bakongpay")])
    if mkhqr_status == 'on':
        rows.append([IBtn(text=f"Pay with KHQR (${amt:.2f})", callback_data=f"topup_mkhqr_{amt:.2f}", style="primary", icon_custom_emoji_id="5422814644093868925", btn_key="khqr")])
    if not rows:
        rows.append([IBtn(text=f"Pay with ABA (${amt:.2f})", callback_data=f"topup_aba_{amt:.2f}", style="primary", icon_custom_emoji_id="6314519407443845610", btn_key="abapay")])
    rows.append([IBtn(text="Back", callback_data="topup_menu", style="danger", icon_custom_emoji_id="5447651546613449378")])

    text = render_clean_text(
        f'<tg-emoji emoji-id="5447579253723918909">💵</tg-emoji> <b>Top Up Balance: ${amt:.2f}</b>\n\n'
        f'👉 សូមជ្រើសរើសវិធីសាស្ត្រទូទាត់ខាងក្រោម៖'
    )
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@dp.callback_query(F.data.startswith("topup_aba_"))
async def topup_aba_pay_handler(call: CallbackQuery, bot: Bot):
    try: await call.answer()
    except Exception: pass
    amt = float(call.data.replace("topup_aba_", ""))
    uid = call.from_user.id
    if has_active_pending_qr(uid):
        try: await call.answer("⏳ QR មានមួយហើយអ្នកបង្កើតនៅខាងលើមិញសូមអ្នកយក QR ខាងលើនឹងទៅផេរទៅ ទាល់តែ QR នឹងផុតកំណត់ ឬ ចុចបោះបង់វាទើបបងអាច បង្កើត QR ម្ដងទៀតបាន"[:195], show_alert=True)
        except Exception: pass
        return await call.message.answer("⏳ QR មានមួយហើយអ្នកបង្កើតនៅខាងលើមិញសូមអ្នកយក QR ខាងលើនឹងទៅផេរទៅ ទាល់តែ QR នឹងផុតកំណត់ ឬ ចុចបោះបង់វាទើបបងអាច បង្កើត QR ម្ដងទៀតបាន")

    try: loading_msg = await call.message.edit_text('<tg-emoji emoji-id="6316599954026535998">🏦</tg-emoji> <b>QR កំពុងបង្កើតពី API សូមរង់ចាំ...</b>')
    except Exception: loading_msg = await call.message.answer('<tg-emoji emoji-id="6316599954026535998">🏦</tg-emoji> <b>QR កំពុងបង្កើតពី API សូមរង់ចាំ...</b>')

    ref_id = f"topup_{uid}_{int(time.time())}"
    uname_arg = call.from_user.username or f"user_{uid}"
    res = await aba_generate_qr_async(amt, ref_id, username=uname_arg)
    if not res or (not res.get("payment_id") and not res.get("qr_string") and not res.get("qr_image")):
        try: await loading_msg.edit_text("⚠️ ប្រព័ន្ធ ABA PAY កំពុងរវល់ ឬមិនទាន់កំណត់ API Key & Merchant ID។ សូមព្យាយាមម្តងទៀត!")
        except Exception: pass
        return

    payment_id = res.get("payment_id") or res.get("transaction_id") or res.get("id")
    qr_image = res.get("qr_image") or res.get("card_image")
    pay_url = res.get("pay_url")
    qr_string = res.get("qr_string")

    photo_input = None
    if qr_string:
        try:
            img_bytes = create_clean_qr_image(qr_string)
            photo_input = BufferedInputFile(img_bytes, filename="topup_khqr.png")
        except Exception as e:
            logger.error(f"create_clean_qr_image topup failed: {e}")
    if not photo_input and qr_image:
        if str(qr_image).startswith("http"):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(str(qr_image).strip(), timeout=15) as qresp:
                        if qresp.status == 200:
                            photo_input = BufferedInputFile(await qresp.read(), filename="topup_aba.png")
            except Exception:
                photo_input = str(qr_image).strip()
        else:
            try:
                b64_str = qr_image.split(",")[1] if "," in qr_image else qr_image
                photo_input = BufferedInputFile(base64.b64decode(b64_str), filename="topup_aba.png")
            except Exception: pass

    aba_url = await resolve_aba_app_url(res, payment_id, qr_string)
    cap = (
        f"💵 <b>Top Up Balance (ABA Pay)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Amount: <b>${amt:.2f}</b>\n"
        f"🔖 Payment ID: <code>{payment_id}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"សូមស្កេន QR ដើម្បីបញ្ចូលទឹកប្រាក់ ប្រព័ន្ធនឹងបញ្ចូលជូនស្វ័យប្រវត្តិ!"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="បើក  App ABA ទូរទាត់", url=aba_url, style="primary", icon_custom_emoji_id="6325675417491481533", btn_key="open_aba")],
        [IBtn(text="Cancel QR", callback_data=f"cancel_qr_{payment_id}", style="danger", icon_custom_emoji_id="6102914615107133393", btn_key="cancel_qr")]
    ])
    try: await loading_msg.delete()
    except Exception: pass
    if photo_input:
        sent_msg = await bot.send_photo(call.message.chat.id, photo=photo_input, caption=cap, reply_markup=kb)
    else:
        sent_msg = await bot.send_message(call.message.chat.id, cap, reply_markup=kb)

    execute_db(
        """INSERT OR REPLACE INTO pending_payments
           (payment_id, pay_type, user_id, chat_id, item_id, qty, msg_id, total, item_name, created_at, is_done)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
        (str(payment_id), 'topup_aba', uid, call.message.chat.id, 0, 1, sent_msg.message_id, amt, f"Top Up ${amt:.2f}", time.time())
    )
    db_ctx, owner_ctx, clone_ctx = current_db_var.get(), current_owner_var.get(), is_clone_var.get()
    run_bg_task(poll_topup_aba_payment(uid, call.message.chat.id, payment_id, sent_msg.message_id, amt, bot, db_ctx, owner_ctx, clone_ctx))

async def _credit_topup_success(uid, chat_id, msg_id, amt, current_bot: Bot):
    execute_db('UPDATE users SET balance = COALESCE(balance, 0.0) + ? WHERE id=?', (amt, uid))
    new_bal_row = execute_db('SELECT COALESCE(balance, 0.0) FROM users WHERE id=?', (uid,), fetch=True)
    new_bal = float(new_bal_row[0]) if new_bal_row else amt
    if msg_id:
        try: await current_bot.delete_message(chat_id, msg_id)
        except Exception: pass
    await current_bot.send_message(
        chat_id,
        f"✅ <b>បញ្ចូលទឹកប្រាក់ជោគជ័យ!</b>\n💰 ចំនួនបញ្ចូល: <b>+${amt:.2f}</b>\n💳 សមតុល្យថ្មី: <b>${new_bal:.2f}</b>"
    )

async def poll_topup_aba_payment(uid, chat_id, payment_id, msg_id, amt, current_bot: Bot, db_ctx, owner_ctx, clone_ctx):
    current_db_var.set(db_ctx)
    current_owner_var.set(owner_ctx)
    is_clone_var.set(clone_ctx)
    timeout = time.time() + 180
    while time.time() < timeout:
        p_row = execute_db('SELECT is_done FROM pending_payments WHERE payment_id=?', (str(payment_id),), fetch=True)
        if p_row and p_row[0] != 0:
            return
        if await aba_check_paid_async(payment_id):
            execute_db('UPDATE pending_payments SET is_done=1 WHERE payment_id=?', (str(payment_id),))
            await aba_mark_credited_async(payment_id)
            await _credit_topup_success(uid, chat_id, msg_id, amt, current_bot)
            return
        await asyncio.sleep(5)

@dp.callback_query(F.data.startswith("vfy_topup_aba_"))
async def verify_topup_aba_handler(call: CallbackQuery, bot: Bot):
    payment_id = call.data.replace("vfy_topup_aba_", "")
    row = execute_db("SELECT user_id, chat_id, msg_id, total, is_done FROM pending_payments WHERE payment_id=?", (payment_id,), fetch=True)
    if not row:
        return await call.answer("❌ មិនមានទិន្នន័យ QR នេះទេ!", show_alert=True)
    uid, chat_id, msg_id, amt, is_done = row
    if is_done == 1:
        return await call.answer("✅ ទឹកប្រាក់ត្រូវបានបញ្ចូលរួចរាល់ហើយ!", show_alert=True)
    if await aba_check_paid_async(payment_id):
        execute_db("UPDATE pending_payments SET is_done=1 WHERE payment_id=?", (payment_id,))
        await aba_mark_credited_async(payment_id)
        await _credit_topup_success(uid, chat_id, msg_id, float(amt), bot)
        await call.answer("✅ បញ្ចូលទឹកប្រាក់ជោគជ័យ!", show_alert=True)
    else:
        await call.answer("❌ មិនទាន់ឃើញការបង់ប្រាក់ទេ! សូមស្កេនបង់ប្រាក់សិន។", show_alert=True)

@dp.callback_query(F.data.startswith("topup_bkg_"))
async def topup_bakong_pay_handler(call: CallbackQuery, bot: Bot):
    try: await call.answer()
    except Exception: pass
    amt = float(call.data.replace("topup_bkg_", ""))
    uid = call.from_user.id
    if has_active_pending_qr(uid):
        try: await call.answer("⏳ QR មានមួយហើយអ្នកបង្កើតនៅខាងលើមិញសូមអ្នកយក QR ខាងលើនឹងទៅផេរទៅ ទាល់តែ QR នឹងផុតកំណត់ ឬ ចុចបោះបង់វាទើបបងអាច បង្កើត QR ម្ដងទៀតបាន"[:195], show_alert=True)
        except Exception: pass
        return await call.message.answer("⏳ QR មានមួយហើយអ្នកបង្កើតនៅខាងលើមិញសូមអ្នកយក QR ខាងលើនឹងទៅផេរទៅ ទាល់តែ QR នឹងផុតកំណត់ ឬ ចុចបោះបង់វាទើបបងអាច បង្កើត QR ម្ដងទៀតបាន")
    ref_id = f"topup_bkg_{uid}_{int(time.time())}"
    res = await bakong_fetch_api_qr(amt, ref_id)
    if not res:
        return await call.message.answer("⚠️ មិនអាចទាញយក QR បាគងពី API បានទេ!")
    qr_string = res.get("qr_string")
    payment_id = res.get("transaction_id") or ref_id
    photo_input = None
    if qr_string:
        try:
            photo_input = BufferedInputFile(create_clean_qr_image(qr_string), filename="topup_bakong.png")
        except Exception:
            pass
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="Verify Payment", callback_data=f"vfy_topup_bkg_{payment_id}", style="success", icon_custom_emoji_id="5904704361182798355", btn_key="vfy_bkg")],
        [IBtn(text="Cancel QR / បោះបង់ QR", callback_data=f"cancel_qr_{payment_id}", style="danger", icon_custom_emoji_id="6176808917549453468", btn_key="cancel_qr")]
    ])
    cap = f"💵 <b>Top Up Balance (Bakong KHQR)</b>\n💰 Amount: <b>${amt:.2f}</b>\n🔖 Payment ID: <code>{payment_id}</code>"
    if photo_input:
        sent_msg = await bot.send_photo(call.message.chat.id, photo=photo_input, caption=cap, reply_markup=kb)
    else:
        sent_msg = await bot.send_message(call.message.chat.id, cap, reply_markup=kb)
    execute_db(
        """INSERT OR REPLACE INTO pending_payments
           (payment_id, pay_type, user_id, chat_id, item_id, qty, msg_id, total, item_name, created_at, is_done)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
        (str(payment_id), 'topup_bkg', uid, call.message.chat.id, 0, 1, sent_msg.message_id, amt, f"Top Up ${amt:.2f}", time.time())
    )
    db_ctx, owner_ctx, clone_ctx = current_db_var.get(), current_owner_var.get(), is_clone_var.get()
    run_bg_task(poll_topup_bakong_payment(uid, call.message.chat.id, payment_id, sent_msg.message_id, amt, bot, db_ctx, owner_ctx, clone_ctx))

async def poll_topup_bakong_payment(uid, chat_id, payment_id, msg_id, amt, current_bot: Bot, db_ctx, owner_ctx, clone_ctx):
    current_db_var.set(db_ctx)
    current_owner_var.set(owner_ctx)
    is_clone_var.set(clone_ctx)
    timeout = time.time() + 600
    while time.time() < timeout:
        p_row = execute_db('SELECT is_done FROM pending_payments WHERE payment_id=?', (str(payment_id),), fetch=True)
        if p_row and p_row[0] != 0:
            return
        if await bakong_check_paid_async(payment_id):
            execute_db('UPDATE pending_payments SET is_done=1 WHERE payment_id=?', (str(payment_id),))
            await _credit_topup_success(uid, chat_id, msg_id, amt, current_bot)
            return
        await asyncio.sleep(5)

@dp.callback_query(F.data.startswith("vfy_topup_bkg_"))
async def verify_topup_bkg_handler(call: CallbackQuery, bot: Bot):
    payment_id = call.data.replace("vfy_topup_bkg_", "")
    row = execute_db("SELECT user_id, chat_id, msg_id, total, is_done FROM pending_payments WHERE payment_id=?", (payment_id,), fetch=True)
    if not row:
        return await call.answer("❌ មិនមានទិន្នន័យ QR នេះទេ!", show_alert=True)
    uid, chat_id, msg_id, amt, is_done = row
    if is_done == 1:
        return await call.answer("✅ ទឹកប្រាក់ត្រូវបានបញ្ចូលរួចរាល់ហើយ!", show_alert=True)
    if await bakong_check_paid_async(payment_id):
        execute_db("UPDATE pending_payments SET is_done=1 WHERE payment_id=?", (payment_id,))
        await _credit_topup_success(uid, chat_id, msg_id, float(amt), bot)
        await call.answer("✅ បញ្ចូលទឹកប្រាក់ជោគជ័យ!", show_alert=True)
    else:
        await call.answer("❌ មិនទាន់ឃើញការបង់ប្រាក់ទេ!", show_alert=True)


# ----------------- KHQRPAY.SITE ABA CHECKOUT & TOPUP FLOW -----------------
@dp.callback_query(F.data.startswith("khqrpay_"))
async def handle_khqrpay_aba(call: CallbackQuery, bot: Bot):
    try: await call.answer()
    except Exception: pass
    parts = call.data.split("_")
    item_id, qty = int(parts[1]), int(parts[2])
    uid = call.from_user.id
    if has_active_pending_qr(uid):
        try: await call.answer("⏳ QR មានមួយហើយអ្នកបង្កើតនៅខាងលើមិញសូមអ្នកយក QR ខាងលើនឹងទៅផេរទៅ ទាល់តែ QR នឹងផុតកំណត់ ឬ ចុចបោះបង់វាទើបបងអាច បង្កើត QR ម្ដងទៀតបាន"[:195], show_alert=True)
        except Exception: pass
        return await call.message.answer("⏳ QR មានមួយហើយអ្នកបង្កើតនៅខាងលើមិញសូមអ្នកយក QR ខាងលើនឹងទៅផេរទៅ ទាល់តែ QR នឹងផុតកំណត់ ឬ ចុចបោះបង់វាទើបបងអាច បង្កើត QR ម្ដងទៀតបាន")

    stock_qty = get_item_stock(item_id)
    if qty > stock_qty:
        return await call.message.answer(f"❌ ស្តុកមិនគ្រប់គ្រាន់ទេ! (មាន {stock_qty})")

    res_usr = execute_db('SELECT is_reseller, is_reseller_vip FROM users WHERE id=?', (uid,), fetch=True)
    is_res = res_usr[0] if (res_usr and res_usr[0]) else 0
    is_vip = res_usr[1] if (res_usr and len(res_usr) > 1 and res_usr[1]) else 0

    item = execute_db("SELECT items.name, items.price, items.reseller_price, categories.name, items.reseller_vip_price FROM items JOIN categories ON items.cat_id = categories.id WHERE items.id=?", (item_id,), fetch=True)
    if not item:
        return await call.message.answer("❌ មិនមានទិន្នន័យទំនិញនេះទេ!")

    cat_name, item_name = item[3], item[0]
    vip_p = item[4] if (len(item) > 4 and item[4] and item[4] > 0) else 0.0
    if is_vip and vip_p > 0: u_price = vip_p
    elif is_res: u_price = item[2]
    else: u_price = item[1]
    total = round(u_price * qty, 2)

    try: loading_msg = await call.message.edit_text('<tg-emoji emoji-id="5307905813451397794">⏳</tg-emoji> Creating a QR code, please wait.')
    except Exception: loading_msg = await call.message.answer('<tg-emoji emoji-id="5307905813451397794">⏳</tg-emoji> Creating a QR code, please wait.')

    res = await khqrpay_create_aba_async(total)
    if not res or not res.get("id"):
        api_key = (os.getenv('KHQRPAY_API_KEY', '') or get_setting('khqrpay_api_key', '') or '').strip()
        err_msg = (
            '<tg-emoji emoji-id="6100333528740801952">⚠️</tg-emoji> សូមកំណត់ API Key របស់ khqrpay.site នៅក្នុង Setting ជាមុនសិន!'
            if not api_key else
            '<tg-emoji emoji-id="6100333528740801952">⚠️</tg-emoji> មិនអាចបង្កើត QR ពី khqrpay.site បានទេ! សូមព្យាយាមម្តងទៀត។'
        )
        try: await loading_msg.edit_text(err_msg)
        except Exception: pass
        return

    payment_id = str(res.get("id"))
    qr_str = res.get("qr") or res.get("qr_string")
    aba_url = res.get("aba_deeplink") or res.get("checkout_url") or await resolve_aba_app_url(res, payment_id, qr_str)

    photo_input = None
    if qr_str:
        try:
            photo_input = BufferedInputFile(create_clean_qr_image(qr_str), filename="khqrpay_aba.png")
        except Exception as e:
            logger.error(f"khqrpay QR image error: {e}")

    cap = f"""Payment Summary (khqrpay.site)
━━━━━━━━━━━━━━━━━━━━━
Item: {cat_name}
Plan: {item_name}
Quantity: {qty}
Unit Price: ${u_price:.2f}
Total Price: ${total:.2f}
Payment ID: <code>{payment_id}</code>
Method: Instant Delivery (ABA Pay)
━━━━━━━━━━━━━━━━━━━━━
Scan the KHQR to pay. Your order will be fulfilled automatically after confirmation."""

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="បើក  App ABA ទូរទាត់", url=aba_url, style="primary", icon_custom_emoji_id="6325675417491481533", btn_key="open_aba")],
        [IBtn(text="Cancel QR", callback_data=f"cancel_qr_{payment_id}", style="danger", icon_custom_emoji_id="6102914615107133393", btn_key="cancel_qr")]
    ])

    try: await loading_msg.delete()
    except Exception: pass

    if photo_input:
        sent_msg = await bot.send_photo(call.message.chat.id, photo=photo_input, caption=cap, reply_markup=kb)
    else:
        sent_msg = await bot.send_message(call.message.chat.id, cap, reply_markup=kb)

    execute_db(
        """INSERT OR REPLACE INTO pending_payments
           (payment_id, pay_type, user_id, chat_id, item_id, qty, msg_id, total, item_name, created_at, is_done)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
        (payment_id, 'khqrpay', uid, call.message.chat.id, item_id, qty, sent_msg.message_id, total, item_name, time.time())
    )
    db_ctx, owner_ctx, clone_ctx = current_db_var.get(), current_owner_var.get(), is_clone_var.get()
    run_bg_task(poll_khqrpay_payment(call, uid, call.message.chat.id, payment_id, item_id, qty, sent_msg.message_id, total, item_name, bot, db_ctx, owner_ctx, clone_ctx))

async def poll_khqrpay_payment(call, uid, chat_id, payment_id, item_id, qty, msg_id, total_paid, item_name, current_bot: Bot, db_ctx, owner_ctx, clone_ctx):
    current_db_var.set(db_ctx)
    current_owner_var.set(owner_ctx)
    is_clone_var.set(clone_ctx)
    timeout = time.time() + 600
    while time.time() < timeout:
        p_row = execute_db('SELECT is_done FROM pending_payments WHERE payment_id=?', (str(payment_id),), fetch=True)
        if p_row and p_row[0] != 0:
            return
        if await khqrpay_check_paid_async(payment_id):
            execute_db('UPDATE pending_payments SET is_done=1 WHERE payment_id=?', (str(payment_id),))
            await deliver_item(call, uid, chat_id, item_id, qty, msg_id, total_paid, item_name, current_bot)
            return
        await asyncio.sleep(5)

@dp.callback_query(F.data.startswith("vfy_khqrpay_"))
async def verify_khqrpay_handler(call: CallbackQuery, bot: Bot):
    payment_id = call.data.replace("vfy_khqrpay_", "")
    row = execute_db("SELECT user_id, chat_id, item_id, qty, msg_id, total, item_name, is_done FROM pending_payments WHERE payment_id=?", (payment_id,), fetch=True)
    if not row:
        return await call.answer("❌ មិនមានទិន្នន័យ QR នេះទេ ឬផុតកំណត់ហើយ!", show_alert=True)
    uid, chat_id, item_id, qty, msg_id, total, item_name, is_done = row
    if is_done == 1:
        return await call.answer("✅ ការទូទាត់ត្រូវបានផ្ទៀងផ្ទាត់ និងប្រគល់ទំនិញរួចរាល់ហើយ!", show_alert=True)
    if is_done == 2:
        return await call.answer("❌ QR នេះត្រូវបានបោះបង់រួចហើយ!", show_alert=True)
    if await khqrpay_check_paid_async(payment_id):
        execute_db("UPDATE pending_payments SET is_done=1 WHERE payment_id=?", (payment_id,))
        await deliver_item(call, uid, chat_id, item_id, qty, msg_id, total, item_name, bot)
        await call.answer("✅ ការទូទាត់ទទួលបានជោគជ័យ!", show_alert=True)
    else:
        await call.answer("❌ មិនទាន់ឃើញការបង់ប្រាក់ទេ! សូមស្កេនបង់ប្រាក់សិន។", show_alert=True)

@dp.callback_query(F.data.startswith("topup_khqrpay_"))
async def topup_khqrpay_handler(call: CallbackQuery, bot: Bot):
    try: await call.answer()
    except Exception: pass
    amt = float(call.data.replace("topup_khqrpay_", ""))
    uid = call.from_user.id
    if has_active_pending_qr(uid):
        try: await call.answer("⏳ QR មានមួយហើយអ្នកបង្កើតនៅខាងលើមិញសូមអ្នកយក QR ខាងលើនឹងទៅផេរទៅ ទាល់តែ QR នឹងផុតកំណត់ ឬ ចុចបោះបង់វាទើបបងអាច បង្កើត QR ម្ដងទៀតបាន"[:195], show_alert=True)
        except Exception: pass
        return await call.message.answer("⏳ QR មានមួយហើយអ្នកបង្កើតនៅខាងលើមិញសូមអ្នកយក QR ខាងលើនឹងទៅផេរទៅ ទាល់តែ QR នឹងផុតកំណត់ ឬ ចុចបោះបង់វាទើបបងអាច បង្កើត QR ម្ដងទៀតបាន")
    try: loading_msg = await call.message.edit_text('<tg-emoji emoji-id="5307905813451397794">⏳</tg-emoji> Creating a QR code, please wait.')
    except Exception: loading_msg = await call.message.answer('<tg-emoji emoji-id="5307905813451397794">⏳</tg-emoji> Creating a QR code, please wait.')
    res = await khqrpay_create_aba_async(amt)
    if not res or not res.get("id"):
        try: await loading_msg.edit_text("⚠️ មិនអាចបង្កើត QR ពី khqrpay.site បានទេ! សូមពិនិត្យ API Key។")
        except Exception: pass
        return
    payment_id = str(res.get("id"))
    qr_str = res.get("qr") or res.get("qr_string")
    aba_url = res.get("aba_deeplink") or res.get("checkout_url") or await resolve_aba_app_url(res, payment_id, qr_str)

    photo_input = None
    if qr_str:
        try:
            photo_input = BufferedInputFile(create_clean_qr_image(qr_str), filename="topup_khqrpay.png")
        except Exception as e:
            logger.error(f"khqrpay topup QR error: {e}")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="បើក  App ABA ទូរទាត់", url=aba_url, style="primary", icon_custom_emoji_id="6325675417491481533", btn_key="open_aba")],
        [IBtn(text="Cancel QR", callback_data=f"cancel_qr_{payment_id}", style="danger", icon_custom_emoji_id="6102914615107133393", btn_key="cancel_qr")]
    ])
    try: await loading_msg.delete()
    except Exception: pass
    cap = f"💵 <b>Top Up Balance (ABA - khqrpay.site)</b>\n💰 Amount: <b>${amt:.2f}</b>\n🔖 Payment ID: <code>{payment_id}</code>"
    if photo_input:
        sent_msg = await bot.send_photo(call.message.chat.id, photo=photo_input, caption=cap, reply_markup=kb)
    else:
        sent_msg = await bot.send_message(call.message.chat.id, cap, reply_markup=kb)

    execute_db(
        """INSERT OR REPLACE INTO pending_payments
           (payment_id, pay_type, user_id, chat_id, item_id, qty, msg_id, total, item_name, created_at, is_done)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
        (payment_id, 'topup_khqrpay', uid, call.message.chat.id, 0, 1, sent_msg.message_id, amt, f"Top Up ${amt:.2f}", time.time())
    )
    db_ctx, owner_ctx, clone_ctx = current_db_var.get(), current_owner_var.get(), is_clone_var.get()
    run_bg_task(poll_topup_khqrpay_payment(uid, call.message.chat.id, payment_id, sent_msg.message_id, amt, bot, db_ctx, owner_ctx, clone_ctx))

async def poll_topup_khqrpay_payment(uid, chat_id, payment_id, msg_id, amt, current_bot: Bot, db_ctx, owner_ctx, clone_ctx):
    current_db_var.set(db_ctx)
    current_owner_var.set(owner_ctx)
    is_clone_var.set(clone_ctx)
    timeout = time.time() + 600
    while time.time() < timeout:
        p_row = execute_db('SELECT is_done FROM pending_payments WHERE payment_id=?', (str(payment_id),), fetch=True)
        if p_row and p_row[0] != 0:
            return
        if await khqrpay_check_paid_async(payment_id):
            execute_db('UPDATE pending_payments SET is_done=1 WHERE payment_id=?', (str(payment_id),))
            await _credit_topup_success(uid, chat_id, msg_id, amt, current_bot)
            return
        await asyncio.sleep(5)

@dp.callback_query(F.data.startswith("vfy_topup_khqrpay_"))
async def verify_topup_khqrpay_handler(call: CallbackQuery, bot: Bot):
    payment_id = call.data.replace("vfy_topup_khqrpay_", "")
    row = execute_db("SELECT user_id, chat_id, msg_id, total, is_done FROM pending_payments WHERE payment_id=?", (payment_id,), fetch=True)
    if not row:
        return await call.answer("❌ មិនមានទិន្នន័យ QR នេះទេ!", show_alert=True)
    uid, chat_id, msg_id, amt, is_done = row
    if is_done == 1:
        return await call.answer("✅ ទឹកប្រាក់ត្រូវបានបញ្ចូលរួចរាល់ហើយ!", show_alert=True)
    if await khqrpay_check_paid_async(payment_id):
        execute_db("UPDATE pending_payments SET is_done=1 WHERE payment_id=?", (payment_id,))
        await _credit_topup_success(uid, chat_id, msg_id, float(amt), bot)
        await call.answer("✅ បញ្ចូលទឹកប្រាក់ជោគជ័យ!", show_alert=True)
    else:
        await call.answer("❌ មិនទាន់ឃើញការបង់ប្រាក់ទេ!", show_alert=True)

# ----------------- MANUAL KHQR CHECKOUT FLOW -----------------
@dp.callback_query(F.data.startswith("mkhqr_"))
async def handle_manual_khqr(call: CallbackQuery, state: FSMContext, bot: Bot):
    parts = call.data.split("_")
    item_id, qty = int(parts[1]), int(parts[2])
    uid = call.from_user.id
    
    stock_qty = get_item_stock(item_id)
    if qty > stock_qty:
        return await call.answer(f"❌ ស្តុកមិនគ្រប់គ្រាន់ទេ! (មាន {stock_qty})", show_alert=True)
        
    res_usr = execute_db('SELECT is_reseller, is_reseller_vip FROM users WHERE id=?', (uid,), fetch=True)
    is_res = res_usr[0] if (res_usr and res_usr[0]) else 0
    is_vip = res_usr[1] if (res_usr and len(res_usr) > 1 and res_usr[1]) else 0
    item = execute_db('''SELECT items.name, items.price, items.reseller_price, categories.name, items.reseller_vip_price FROM items JOIN categories ON items.cat_id = categories.id WHERE items.id=?''', (item_id,), fetch=True)
        
    cat_name, item_name = item[3], item[0]
    vip_p = item[4] if (len(item) > 4 and item[4] and item[4] > 0) else 0.0
    if is_vip and vip_p > 0: u_price = vip_p
    elif is_res: u_price = item[2]
    else: u_price = item[1]
    total = u_price * qty
    
    manual_img = get_setting('manual_khqr_image')
    if not manual_img: return await call.answer("❌ Admin មិនទាន់បានកំណត់រូបភាព KHQR ទេ!", show_alert=True)
        
    cap = f"""<tg-emoji emoji-id="6235459831302460476">💰</tg-emoji> Amount Paid: <b>${total:.2f}</b>\n<tg-emoji emoji-id="5258049708525380488">🎮</tg-emoji> Game : <b>{cat_name}</b>\n<tg-emoji emoji-id="5431897022456145283">⏱</tg-emoji> Duration: <b>{item_name}</b>\n\n<tg-emoji emoji-id="5445195276291693508">✅</tg-emoji> សូមបងយក KHQR ផ្ទាល់ខ្លួនរបស់អេតមីនទៅផេរក្នុងធានាគារណាមួយដែលបងប្រើចុះ ។\n<tg-emoji emoji-id="6035162669948867129">📊</tg-emoji> បញ្ជាក់ពេលដែលបងផេររួចសូមថតវិក្កយប័ត្រផ្ញើចូលមកកាន់បតវិញផងដើម្បីអោយអេតមីនពិនិត្យមើលជូន"""
    try: await call.message.delete()
    except: pass
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[IBtn(text="❌ បោះបង់", callback_data="cancel_action", style="danger")]])
    await bot.send_photo(call.message.chat.id, manual_img, caption=cap, reply_markup=kb)
    await state.update_data(item_id=item_id, qty=qty, total=total, item_name=item_name)
    await state.set_state(UserWaitReceipt.receipt)
    await call.answer()

@dp.message(UserWaitReceipt.receipt, F.photo)
async def process_manual_receipt(msg: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    item_id, qty, total, item_name = data['item_id'], data['qty'], data['total'], data['item_name']
    uid = msg.from_user.id
    
    await msg.answer("✅ បានបញ្ជូនវិក្កយប័ត្រទៅកាន់ Admin សូមរង់ចាំបន្តិចដើម្បី Admin ពិនិត្យបញ្ជាក់...")
    await state.clear()
    
    u_name, u_user = msg.from_user.first_name or "Unknown", f"@{msg.from_user.username}" if msg.from_user.username else "គ្មាន"
    cap = f"""🧾 <b>វិក្កយប័ត្រថ្មី (KHQR Manual)</b>\n- ID: <code>{uid}</code>\n- User: {u_name} ({u_user})\n- ទំនិញ: {item_name}\n- ចំនួន: {qty}\n- តម្លៃសរុប: ${total:.2f}"""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="បព្ជាក់សំណើរ", callback_data=f"mqa_{uid}_{item_id}_{qty}_{total}", style="success", icon_custom_emoji_id="6102563003314479651")],
        [IBtn(text="បោះបង់សំណើរ", callback_data=f"mqr_{uid}", style="danger", icon_custom_emoji_id="6253758805755038090")]
    ])
    
    chan_id = get_setting('channel_id') or get_current_owner()
    await bot.send_photo(chan_id, msg.photo[-1].file_id, caption=cap, reply_markup=kb)

@dp.callback_query(F.data.startswith("mqa_"))
async def approve_manual_receipt(call: CallbackQuery, bot: Bot):
    parts = call.data.split("_")
    uid, item_id, qty, total = int(parts[1]), int(parts[2]), int(parts[3]), float(parts[4])
    await deliver_item(None, uid, uid, item_id, qty, None, total, "Manual Payment Item", bot)
    await call.message.edit_caption(caption=call.message.caption + "\n\n✅ <b>អេតមីនបានបញ្ជាក់សំណើរ និងផ្ញើទំនិញរួចរាល់!</b>", reply_markup=None)
    await call.answer("✅ បានបញ្ជាក់សំណើរ!", show_alert=True)

@dp.callback_query(F.data.startswith("mqr_"))
async def reject_manual_receipt(call: CallbackQuery, bot: Bot):
    uid = int(call.data.split("_")[1])
    try: await bot.send_message(uid, "❌ សំណើរបង់ប្រាក់របស់អ្នកត្រូវបានបដិសេធដោយ Admin! សូមទាក់ទង Admin សម្រាប់ព័ត៌មានបន្ថែម។")
    except: pass
    await call.message.edit_caption(caption=call.message.caption + "\n\n❌ <b>សំណើរត្រូវបានបោះបង់!</b>", reply_markup=None)
    await call.answer("❌ បានបោះបង់សំណើរ!", show_alert=True)

# ====================================================================================================
# [ ផ្នែក ADMIN PANEL SETTINGS (NEW SMART FEATURES) ]
# ====================================================================================================

@dp.callback_query(F.data == "adm_settings")
async def adm_settings_handler(call: CallbackQuery):
    try: await call.answer()
    except Exception: pass
    mkhqr_status = get_setting('manual_khqr_status', 'off')
    if mkhqr_status == 'on': btn_khqr_toggle = IBtn(text="🔕បិទKHQR", callback_data="toggle_mkhqr", style="danger")
    else: btn_khqr_toggle = IBtn(text="🔔បើកKHQR", callback_data="toggle_mkhqr", style="success")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="📊Located", callback_data="adm_located", style="primary")],
        [IBtn(text="👥User", callback_data="adm_users_list", style="primary")],
        [IBtn(text="📉របាយការណ៍ការបព្ជាទិញបស់ភ្ញៀវ", callback_data="adm_sales_report", style="primary")],
        [IBtn(text="🚫Ban User", callback_data="adm_ban_list", style="danger"), IBtn(text="🔑Unban User", callback_data="adm_unban_list", style="success")],
        [IBtn(text="🖼កំណត់ KHQR", callback_data="adm_set_mkhqr", style="primary"), btn_khqr_toggle],
        [IBtn(text="Setting Payment ABA", callback_data="adm_aba_settings", style="primary", icon_custom_emoji_id="6316599954026535998")],
        [IBtn(text="Setting ABA (khqrpay.site)", callback_data="adm_khqrpay_settings", style="primary", icon_custom_emoji_id="6316599954026535998")],
        [IBtn(text="Setting Payment Bakong", callback_data="adm_bakong_settings", style="primary", icon_custom_emoji_id="6095690437165586962")],
        [IBtn(text="Setting Binance Pay", callback_data="adm_binance_settings", style="primary", icon_custom_emoji_id="5793944030861598035")],
        [IBtn(text="Edit Contact Admin", callback_data="adm_edit_contact_url", style="primary", icon_custom_emoji_id="6154233835002271015")],
        [IBtn(text="រៀបចំបូតុង", callback_data="adm_btn_organizer", style="primary", icon_custom_emoji_id="5335054400513649848")],
        [IBtn(text="Back", callback_data="back_admin", style="danger", icon_custom_emoji_id="6035130900075777681")]
    ])
    text = "<tg-emoji emoji-id=\"6151986639393531426\">⚙️</tg-emoji> សូមបងប្រើប្រាស់មុខងារក្នុង Setting នេះទៅដែលមានមុខងាឆ្លាតវ័យ\nចុចបូតុងខាងក្រោមដើម្បីប្រើវា៖"
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data == "toggle_mkhqr")
async def toggle_mkhqr_handler(call: CallbackQuery):
    curr = get_setting('manual_khqr_status', 'off')
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('manual_khqr_status', 'off' if curr == 'on' else 'on'))
    await adm_settings_handler(call)

@dp.callback_query(F.data == "adm_set_mkhqr")
async def adm_set_mkhqr_handler(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("🖼 សូមផ្ញើរូបភាព KHQR ផ្ទាល់ខ្លួនរបស់ Admin មកទីនេះ៖", reply_markup=cancel_inline())
    await state.set_state(AdminManualQR.photo)
    await call.answer()

@dp.message(AdminManualQR.photo, F.photo)
async def save_manual_khqr(msg: Message, state: FSMContext):
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('manual_khqr_image', msg.photo[-1].file_id))
    await msg.answer("✅ បានកំណត់រូបភាព KHQR ផ្ទាល់ខ្លួនជោគជ័យ!")
    await state.clear()

@dp.callback_query(F.data == "adm_located")
async def adm_located_handler(call: CallbackQuery):
    total_rev = execute_db('SELECT SUM(total_price) FROM orders', fetch=True)[0] or 0.0
    total_qty = execute_db('SELECT SUM(qty) FROM orders', fetch=True)[0] or 0
    text = f"📊Located\n💸ប្រាក់ចំណូល : <b>${total_rev:.2f}</b>\n📦លក់ទំនិញបាន : <b>{total_qty} ដុំ</b>"
    kb = InlineKeyboardMarkup(inline_keyboard=[[IBtn(text="Back", callback_data="adm_settings", style="danger", icon_custom_emoji_id="6035130900075777681")]])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data == "adm_users_list")
async def adm_users_list_handler(call: CallbackQuery):
    users = execute_db('SELECT id, first_name, username FROM users ORDER BY id DESC LIMIT 50', fetchall=True)
    count = execute_db('SELECT COUNT(*) FROM users', fetch=True)[0]
    text = f"👥អ្នកប្រើប្រាស់ចុងក្រោយ <b>{count} នាក់</b>\n\n"
    for u in users:
        uname = f"@{u[2]}" if u[2] else "គ្មាន"
        fname = u[1] or "Unknown"
        text += f"- <code>{u[0]}</code> | {fname} | {uname}\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[[IBtn(text="Back", callback_data="adm_settings", style="danger", icon_custom_emoji_id="6035130900075777681")]])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data == "adm_sales_report")
async def adm_sales_report_handler(call: CallbackQuery):
    total_rev = execute_db('SELECT SUM(total_price) FROM orders', fetch=True)[0] or 0.0
    total_qty = execute_db('SELECT SUM(qty) FROM orders', fetch=True)[0] or 0
    orders = execute_db('SELECT o.id, o.total_price, o.date, i.name FROM orders o JOIN items i ON o.item_id = i.id ORDER BY o.id DESC LIMIT 10', fetchall=True)
    
    text = f"📉 <b>របាយការណ៍ការបព្ជាទិញបស់ភ្ញៀវ</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n💸 ចំណូលសរុប : <b>${total_rev:.2f}</b>\n📦 លក់បានសរុប : <b>{total_qty} ដុំ</b>\n\n📝 ប្រតិបត្តិការថ្មីៗ:\n"
    for o in orders: text += f"▪️ #<b>{o[0]}</b> | ${o[1]:.2f} | {o[3]} | <code>{o[2]}</code>\n"
        
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="🔄 Refresh", callback_data="adm_sales_report", style="success")],
        [IBtn(text="Back", callback_data="adm_settings", style="danger", icon_custom_emoji_id="6035130900075777681")]
    ])
    try: await call.message.edit_text(text, reply_markup=kb)
    except: pass
    await call.answer()

# --- KHQRPAY.SITE ABA SETTINGS ---
@dp.callback_query(F.data == "adm_khqrpay_settings")
async def adm_khqrpay_settings_handler(call: CallbackQuery):
    raw_key = (get_setting('khqrpay_api_key', '') or '').strip()
    key_disp = f"{raw_key[:6]}••••••••{raw_key[-4:]}" if len(raw_key) > 10 else ("••••••••" if raw_key else "មិនទាន់កំណត់")
    status = get_setting('khqrpay_pay_status', 'off')
    btn_toggle = IBtn(text="🔕បិទ ABA (khqrpay)", callback_data="toggle_khqrpay", style="danger") if status == 'on' else IBtn(text="🔔បើក ABA (khqrpay)", callback_data="toggle_khqrpay", style="success")

    text = f"""<tg-emoji emoji-id="6316599954026535998">🏦</tg-emoji> <b>Setting Payment ABA (khqrpay.site)</b>
━━━━━━━━━━━━━━━━━━━━━
🔑 <b>API Key :</b> <code>{key_disp}</code>
📊 <b>ស្ថានភាព :</b> <b>{"បើកដំណើរការ 🟢" if status == "on" else "បានបិទ 🔴"}</b>
⏱ <b>Check Payment :</b> <code>5 វិនាទី / ម្ដង</code>
━━━━━━━━━━━━━━━━━━━━━
👉 សូមបញ្ចូល API Key (<code>sk_...</code>) ពី khqrpay.site៖"""

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="🔑 ប្ដូរ API Key (khqrpay.site)", callback_data="adm_edit_khqrpay_api", style="primary")],
        [btn_toggle],
        [IBtn(text="Back", callback_data="adm_settings", style="danger", icon_custom_emoji_id="6035130900075777681")]
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data == "toggle_khqrpay")
async def toggle_khqrpay_handler(call: CallbackQuery):
    curr = get_setting('khqrpay_pay_status', 'off')
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('khqrpay_pay_status', 'off' if curr == 'on' else 'on'))
    await adm_khqrpay_settings_handler(call)

@dp.callback_query(F.data == "adm_edit_khqrpay_api")
async def adm_edit_khqrpay_api_prompt(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("🔑 <b>សូមបញ្ចូល API Key (sk_...) របស់ khqrpay.site៖</b>", reply_markup=cancel_inline())
    await state.set_state(AdminKhqrPay.api_key)
    await call.answer()

@dp.message(AdminKhqrPay.api_key)
async def save_khqrpay_api_handler(msg: Message, state: FSMContext):
    key = (msg.text or "").strip()
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('khqrpay_api_key', key))
    await msg.answer("✅ បានកំណត់ API Key (khqrpay.site) ជោគជ័យ!", reply_markup=admin_back_inline("adm_khqrpay_settings"))
    await state.clear()

# --- BINANCE SETTINGS HANDLERS ---
@dp.callback_query(F.data == "adm_binance_settings")
async def adm_binance_settings_handler(call: CallbackQuery):
    try: await call.answer()
    except Exception: pass
    raw_binance_id = get_setting('binance_pay_id', 'មិនទាន់កំណត់') or 'មិនទាន់កំណត់'
    binance_status = get_setting('binance_pay_status', 'off')
    btn_binance_toggle = IBtn(text="🔕បិទ Binance Pay", callback_data="toggle_binancepay", style="danger") if binance_status == 'on' else IBtn(text="🔔បើក Binance Pay", callback_data="toggle_binancepay", style="success")
    
    if raw_binance_id and raw_binance_id != 'មិនទាន់កំណត់':
        binance_disp = f"{raw_binance_id[:3]}••••{raw_binance_id[-2:]}" if len(raw_binance_id) > 5 else raw_binance_id
    else:
        binance_disp = "មិនទាន់កំណត់"

    status_tag = "បើកដំណើរការ 🟢" if binance_status == 'on' else "បានបិទ 🔴"
    text = f"""<tg-emoji emoji-id="5793944030861598035">💳</tg-emoji> <b>Setting Binance Pay</b>
————————————————————-
🏷 <b>Binance Pay ID បច្ចុប្បន្ន៖</b> <code>{binance_disp}</code>
📊 <b>ស្ថានភាព (Status)៖</b> <b>{status_tag}</b>
—————————————————————
👉 សូមចុចបូតុងខាងក្រោមដើម្បីកំណត់ Binance Pay ID ឬ បើក/បិទ ការទូទាត់តាម Binance Pay"""
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="🏷 កំណត់ Binance Pay ID", callback_data="adm_edit_binance_id", style="primary", icon_custom_emoji_id="5793944030861598035")],
        [btn_binance_toggle],
        [IBtn(text="Back", callback_data="adm_settings", style="danger", icon_custom_emoji_id="6035130900075777681")]
    ])
    await call.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data == "toggle_binancepay")
async def toggle_binancepay_handler(call: CallbackQuery):
    curr = get_setting('binance_pay_status', 'off')
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('binance_pay_status', 'off' if curr == 'on' else 'on'))
    await adm_binance_settings_handler(call)

@dp.callback_query(F.data == "adm_edit_binance_id")
async def adm_edit_binance_id_prompt(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("✏️ សូមបញ្ចូល Binance Pay ID (Pay ID / UID) ថ្មីរបស់អ្នក ៖", reply_markup=cancel_inline())
    await state.set_state(AdminBinance.binance_id)
    await call.answer()

@dp.message(AdminBinance.binance_id)
async def save_binance_id_handler(msg: Message, state: FSMContext):
    bid = msg.text.strip()
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('binance_pay_id', bid))
    await msg.answer(f"✅ បានផ្លាស់ប្តូរ Binance Pay ID ទៅជា: <code>{bid}</code> ជោគជ័យ!", reply_markup=admin_back_inline("adm_binance_settings"))
    await state.clear()

# --- ABA SETTINGS SYSTEM ---
@dp.callback_query(F.data == "adm_aba_settings")
async def adm_aba_settings_handler(call: CallbackQuery):
    raw_api_key = get_setting('aba_api_key', 'មិនទាន់កំណត់') or 'មិនទាន់កំណត់'
    qr_name = get_setting('aba_qr_name', 'ITACHI BOT 24 H') or 'ITACHI BOT 24 H'
    
    aba_status = get_setting('aba_pay_status', 'on')
    btn_aba_toggle = IBtn(text="🔕បិទABA PAY", callback_data="toggle_abapay", style="danger") if aba_status == 'on' else IBtn(text="🔔បើកABA PAY", callback_data="toggle_abapay", style="success")
        
    merchant_id = get_setting('aba_merchant_id', 'មិនទាន់កំណត់') or 'មិនទាន់កំណត់'
    
    # Hide/mask sensitive API key and merchant ID
    if raw_api_key and raw_api_key != 'មិនទាន់កំណត់':
        api_key_disp = f"{raw_api_key[:4]}••••••••{raw_api_key[-4:]}" if len(raw_api_key) > 8 else "••••••••"
    else:
        api_key_disp = "មិនទាន់កំណត់"
        
    if merchant_id and merchant_id != 'មិនទាន់កំណត់':
        merchant_disp = f"{merchant_id[:3]}••••{merchant_id[-2:]}" if len(merchant_id) > 5 else merchant_id
    else:
        merchant_disp = "មិនទាន់កំណត់"

    text = f"""<tg-emoji emoji-id="6316599954026535998">🏦</tg-emoji> <b>Setting Payment ABA</b>
————————————————————-
<tg-emoji emoji-id="6230825600244784296">🔑</tg-emoji> <b>API key បច្ចុកប្បន្ន៖</b> <code>{api_key_disp}</code>
<tg-emoji emoji-id="6231134485702779241">🏷</tg-emoji> <b>ID Merchants បច្ចុកប្បន្ន៖</b> <code>{merchant_disp}</code>
—————————————————————
👉 សូមចុចបូតុងខាងក្រោមដើម្បីប្ដូរ API ឬ ប្ដូរ ID Merchans បាន"""
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="🔑 ប្ដូរ API Key", callback_data="adm_edit_aba_api", style="primary")],
        [IBtn(text="🏷 ប្ដូរ ID Merchan", callback_data="adm_edit_aba_merch", style="primary", icon_custom_emoji_id="6231134485702779241")],
        [btn_aba_toggle],
        [IBtn(text="Back", callback_data="adm_settings", style="danger", icon_custom_emoji_id="6035130900075777681")]
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data == "toggle_abapay")
async def toggle_abapay_handler(call: CallbackQuery):
    curr = get_setting('aba_pay_status', 'on')
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('aba_pay_status', 'off' if curr == 'on' else 'on'))
    await adm_aba_settings_handler(call)

@dp.callback_query(F.data == "adm_edit_aba_api")
async def adm_edit_aba_api(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("បញ្ចូល API Key ថ្មីរបស់អ្នក:", reply_markup=cancel_inline())
    await state.set_state(AdminABA.api_key)
    await call.answer()

@dp.message(AdminABA.api_key)
async def save_aba_api(msg: Message, state: FSMContext):
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('aba_api_key', msg.text.strip()))
    await msg.answer("✅ បានផ្លាស់ប្តូរ API Key ជោគជ័យ!")
    await state.clear()

@dp.callback_query(F.data == "adm_edit_aba_merch")
async def adm_edit_aba_merch(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("បញ្ចូល ID Merchants ថ្មីរបស់អ្នក:", reply_markup=cancel_inline())
    await state.set_state(AdminABA.merchant_id)
    await call.answer()

@dp.message(AdminABA.merchant_id)
async def save_aba_merch(msg: Message, state: FSMContext):
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('aba_merchant_id', msg.text.strip()))
    await msg.answer("✅ បានផ្លាស់ប្តូរ ID Merchants ជោគជ័យ!")
    await state.clear()

# --- BAKONG SETTINGS SYSTEM (NEW) ---
@dp.callback_query(F.data == "adm_edit_aba_qr_name")
async def adm_edit_aba_qr_name_handler(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("✏️ សូមបញ្ចូល ឈ្មោះ QR ថ្មីរបស់អ្នក (ឧទាហរណ៍: ITACHI BOT 24 H ឬ ANGKOR SERVICES):", reply_markup=cancel_inline())
    await state.set_state(AdminABA.qr_name)
    await call.answer()

@dp.message(AdminABA.qr_name)
async def save_aba_qr_name_handler(msg: Message, state: FSMContext):
    name = msg.text.strip()
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('aba_qr_name', name))
    await msg.answer(f"✅ បានផ្លាស់ប្តូរឈ្មោះ QR ទៅជា: <b>{name}</b> ជោគជ័យ!")
    await state.clear()

@dp.callback_query(F.data == "adm_bakong_settings")
async def adm_bakong_settings_handler(call: CallbackQuery):
    token = _get_bakong_api_key()
    account = (get_setting('bakong_account', '') or get_setting('bakong_username_id', '') or os.getenv('BAKONG_ACCOUNT', '') or '').strip()

    if token and token != 'មិនទាន់កំណត់':
        token_disp = f"{token[:6]}••••••••{token[-4:]}" if len(token) > 10 else "••••••••"
    else:
        token_disp = "មិនទាន់កំណត់"

    if account and account != 'មិនទាន់កំណត់':
        account_disp = f"{account[:4]}••••{account[-3:]}" if len(account) > 7 else account
    else:
        account_disp = "មិនទាន់កំណត់"

    bakong_status = get_setting('bakong_pay_status', 'off')
    btn_bakong_toggle = IBtn(text="🔕បិទ បាគង", callback_data="toggle_bakongpay", style="danger") if bakong_status == 'on' else IBtn(text="🔔បើក បាគង", callback_data="toggle_bakongpay", style="success")

    text = f"""<tg-emoji emoji-id="6095690437165586962">🏦</tg-emoji> <b>Setting Bakong (khqrpay.site KHQR)</b>
━━━━━━━━━━━━━━━━━━━━━
🏷 <b>ID Bakong :</b> <code>{account_disp}</code>
🔑 <b>API Key :</b> <code>{token_disp}</code>
⏱ <b>Check Payment :</b> <code>5 វិនាទី / ម្ដង</code>
━━━━━━━━━━━━━━━━━━━━━
👉 សូមចុចបូតុងខាងក្រោមដើម្បីប្ដូរ API ឬ ID Bakong៖"""

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="🔑 ប្ដូរ API", callback_data="adm_edit_bakong_token", style="primary")],
        [IBtn(text="🏷 ប្ដូរ ID Bakong", callback_data="adm_edit_bakong_user", style="primary")],
        [btn_bakong_toggle],
        [IBtn(text="Back", callback_data="adm_settings", style="danger", icon_custom_emoji_id="6035130900075777681")]
    ])
    await call.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
    await call.answer()

@dp.callback_query(F.data == "toggle_bakongpay")
async def toggle_bakongpay_handler(call: CallbackQuery):
    curr = get_setting('bakong_pay_status', 'off')
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('bakong_pay_status', 'off' if curr == 'on' else 'on'))
    await adm_bakong_settings_handler(call)

@dp.callback_query(F.data == "adm_edit_bakong_user")
async def adm_edit_bakong_user(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("🏷️ <b>បញ្ចូល Bakong Account ID របស់អ្នក</b> (ឧទាហរណ៍: <code>user@bakong</code> ឬ <code>phone@abaa</code>) ៖", reply_markup=cancel_inline())
    await state.set_state(AdminBakong.username_id)
    await call.answer()

@dp.message(AdminBakong.username_id)
async def save_bakong_user(msg: Message, state: FSMContext):
    acc = msg.text.strip()
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('bakong_account', acc))
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('bakong_username_id', acc))
    await msg.answer(f"✅ បានកំណត់ Bakong Account ID: <b>{acc}</b> ជោគជ័យ!", reply_markup=admin_back_inline("adm_bakong_settings"))
    await state.clear()

@dp.callback_query(F.data.in_(["adm_edit_bakong_token", "adm_edit_bakong_api"]))
async def adm_edit_bakong_token(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("🔑 <b>បញ្ចូល Bakong Developer Token ថ្មីរបស់អ្នក៖</b>", reply_markup=cancel_inline())
    await state.set_state(AdminBakong.api_key)
    await call.answer()

@dp.message(AdminBakong.api_key)
async def save_bakong_token(msg: Message, state: FSMContext):
    token = msg.text.strip()
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('bakong_token', token))
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('bakong_api_key', token))
    await msg.answer("✅ បានផ្លាស់ប្តូរ Bakong Token ជោគជ័យ!", reply_markup=admin_back_inline("adm_bakong_settings"))
    await state.clear()

@dp.callback_query(F.data.in_(["adm_edit_bakong_base", "adm_edit_bakong_url"]))
async def adm_edit_bakong_base(call: CallbackQuery, state: FSMContext):
    curr = get_setting('bakong_api_base', BAKONG_API_BASE_DEFAULT)
    await call.message.edit_text(f"🌐 <b>បញ្ចូល API Base / Proxy របស់បាគង៖</b>\n(បច្ចុប្បន្ន: <code>{curr}</code>)\n\n👉 <i>ឧទាហរណ៍៖\n- <code>https://api-bakong.nbc.gov.kh/v1</code> (Official)\n- <code>http://bakong.apsara.fun/v1</code> (Proxy)\n- <code>https://api.khqr.dev/v1</code></i>", reply_markup=cancel_inline())
    await state.set_state(AdminBakong.api_base)
    await call.answer()

@dp.message(AdminBakong.api_base)
async def save_bakong_base(msg: Message, state: FSMContext):
    base = msg.text.strip().rstrip('/')
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('bakong_api_base', base))
    await msg.answer(f"✅ បានផ្លាស់ប្តូរ API Base: <b>{base}</b> ជោគជ័យ!", reply_markup=admin_back_inline("adm_bakong_settings"))
    await state.clear()


# ====================================================================================================
# [ 📞 EDIT CONTACT ADMIN (ADMIN SETTINGS) ]
# ====================================================================================================

@dp.callback_query(F.data == "adm_edit_contact_url")
async def adm_edit_contact_url_prompt(call: CallbackQuery, state: FSMContext):
    curr = get_setting('contact_admin_url', 'https://t.me/Vbenstore168')
    await call.message.edit_text(f"✏️ <b>សូមវាយបញ្ចូល Link ឬ Username Telegram សម្រាប់ Contact Admin៖</b>\n(បច្ចុប្បន្ន: <code>{curr}</code>)\n\n👉 <i>ឧទាហរណ៍: @Vbenstore168 ឬ https://t.me/Vbenstore168</i>", reply_markup=cancel_inline())
    await state.set_state(AdminContentSetting.contact_url)
    await call.answer()

@dp.message(AdminContentSetting.contact_url)
async def save_contact_url_handler(msg: Message, state: FSMContext):
    raw = msg.text.strip()
    if raw.startswith("@"):
        url = f"https://t.me/{raw[1:]}"
    elif not raw.startswith("http://") and not raw.startswith("https://"):
        url = f"https://t.me/{raw}"
    else:
        url = raw
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('contact_admin_url', url))
    await msg.answer(f"✅ បានកែប្រែ Link Contact Admin ទៅជា: <b>{url}</b> ជោគជ័យ!", reply_markup=admin_back_inline("adm_settings"))
    await state.clear()

# ====================================================================================================
# [ 🔢 CUSTOM QUANTITY FLOW ]
# ====================================================================================================

@dp.callback_query(F.data.startswith("custom_qty_"))
async def custom_qty_prompt_handler(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    item_id = int(parts[2])
    stock_qty = get_item_stock(item_id)
    stk_disp = "∞" if stock_qty >= 9999 else str(stock_qty)
    
    await state.update_data(target_item_id=item_id, item_stock=stock_qty)
    await state.set_state(OrderFSM.custom_qty)
    
    prompt = render_clean_text(f"""<tg-emoji emoji-id="5213305971891248967">🔢</tg-emoji> <b>បញ្ចូលចំនួនទំនិញផ្ទាល់ខ្លួន</b>

- <tg-emoji emoji-id="5447387942995655277">📦</tg-emoji> <b>ស្តុកនៅសល់៖</b> {stk_disp}

<tg-emoji emoji-id="6071034593287345457">👉</tg-emoji> សូមផ្ញើ <b>ចំនួនដែលចង់ទិញ (ជាលេខ)</b> មកកាន់ខ្ញុំឥឡូវនេះ៖""")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="Back", callback_data=f"cancel_custom_qty_{item_id}", style="danger", icon_custom_emoji_id="5352759161945867747")]
    ])
    try:
        await call.message.edit_text(prompt, reply_markup=kb)
    except Exception:
        await call.message.answer(prompt, reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data.startswith("cancel_custom_qty_"))
async def cancel_custom_qty_handler(call: CallbackQuery, state: FSMContext, bot: Bot):
    await state.clear()
    item_id = int(call.data.replace("cancel_custom_qty_", ""))
    await render_checkout(call, item_id, 1, is_edit=True, current_bot=bot)


# ====================================================================================================
# [ 🛍 BOT COMMAND HANDLERS ]
# ====================================================================================================

@dp.message(Command("shop"))
async def cmd_shop_handler(msg: Message, state: FSMContext, bot: Bot):
    await state.clear()
    await send_categories(msg, bot)



# --- BAN / UNBAN SYSTEM ---
@dp.callback_query(F.data == "adm_ban_list")
async def adm_ban_list(call: CallbackQuery):
    owner_id = get_current_owner()
    users = execute_db('SELECT id, first_name FROM users WHERE is_banned=0 AND id != ? LIMIT 40', (owner_id,), fetchall=True)
    kb, row = [], []
    for u in users:
        fname = u[1] or str(u[0])
        row.append(IBtn(text=f"🚫 {fname[:10]}", callback_data=f"ban_{u[0]}", style="danger"))
        if len(row) == 2:
            kb.append(row); row = []
    if row: kb.append(row)
    kb.append([IBtn(text="Back", callback_data="adm_settings", style="primary", icon_custom_emoji_id="6035130900075777681")])
    await call.message.edit_text("ជ្រើសរើស User ដើម្បី Ban:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data.startswith("ban_"))
async def do_ban(call: CallbackQuery):
    uid = int(call.data.split("_")[1])
    execute_db('UPDATE users SET is_banned=1 WHERE id=?', (uid,))
    await call.answer("✅ បាន Ban User រួចរាល់!", show_alert=True)
    await adm_ban_list(call)

@dp.callback_query(F.data == "adm_unban_list")
async def adm_unban_list(call: CallbackQuery):
    users = execute_db('SELECT id, first_name FROM users WHERE is_banned=1 LIMIT 40', fetchall=True)
    kb, row = [], []
    for u in users:
        fname = u[1] or str(u[0])
        row.append(IBtn(text=f"🔑 {fname[:10]}", callback_data=f"unban_{u[0]}", style="success"))
        if len(row) == 2:
            kb.append(row); row = []
    if row: kb.append(row)
    kb.append([IBtn(text="Back", callback_data="adm_settings", style="primary", icon_custom_emoji_id="6035130900075777681")])
    await call.message.edit_text("ជ្រើសរើស User ដើម្បីដោះ Ban (Unban):", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data.startswith("unban_"))
async def do_unban(call: CallbackQuery):
    uid = int(call.data.split("_")[1])
    execute_db('UPDATE users SET is_banned=0 WHERE id=?', (uid,))
    await call.answer("✅ បានដោះ Ban រួចរាល់!", show_alert=True)
    await adm_unban_list(call)

# ====================================================================================================
# [ ផ្នែក ADMIN PANEL DETAILS ]
# ====================================================================================================

@dp.callback_query(F.data == "adm_manage_products")
async def adm_products(call: CallbackQuery):
    try: await call.answer()
    except Exception: pass
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="Manager Add Game / del", callback_data="adm_mgr_api_game", style="success", icon_custom_emoji_id="5445023138297447592")],
        [IBtn(text="💰ដាក់ប្រាក់", callback_data="adm_api_deposit", style="success")],
        [IBtn(text="បង្កើត ផលលិតផល", callback_data="adm_add_cat", style="success", icon_custom_emoji_id="5445146945024720188")],
        [IBtn(text="បង្កើត កព្ចាប់", callback_data="adm_add_item", style="success", icon_custom_emoji_id="5447253390260207116")],
        [IBtn(text="🔕បិទ/បើកមុខងា", callback_data="adm_toggle_cat_status", style="primary")],
        [IBtn(text="កែឈ្មោះផលលិតផល", callback_data="adm_rename_cat", style="primary", icon_custom_emoji_id="5445128296276718145")],
        [IBtn(text="កែឈ្មោះទំនិញ", callback_data="adm_rename_item", style="primary", icon_custom_emoji_id="5445128296276718145")],
        [IBtn(text="ដាក់វីដេអូ ឬ រូបភាព (Category)", callback_data="adm_add_cat_media", style="primary")],
        [IBtn(text="លុបវីដេអូ ឬ រូបភាព", callback_data="adm_del_cat_media", style="danger")],
        [IBtn(text="ដាក់អត្ថបទ ( ផលលិតផល )", callback_data="adm_add_cat_desc", style="primary", icon_custom_emoji_id="5444988177263654261")],
        [IBtn(text="ដកអត្ថបទ ( ផលលិតផល )", callback_data="adm_del_cat_desc", style="danger", icon_custom_emoji_id="5447385112612208213")],
        [IBtn(text="ដាក់ File/Link ពេលទិញរួច", callback_data="adm_add_post_media", style="primary")],
        [IBtn(text="លុប File/Link ពេលទិញរួច", callback_data="adm_del_post_media", style="danger")],
        [IBtn(text="Back", callback_data="back_admin", style="danger", icon_custom_emoji_id="6035130900075777681")]
    ])
    await call.message.edit_text("🛒 <b>គ្រប់គ្រងផលិតផល និងទំនិញ</b>", reply_markup=kb)


@dp.callback_query(F.data == "adm_api_deposit")
async def adm_api_deposit_start(call: CallbackQuery, state: FSMContext):
    try: await call.answer()
    except Exception: pass
    bal_str = "មិនស្គាល់"
    try:
        bal_data = await ResellerAPIAsync().balance()
        if isinstance(bal_data, dict):
            bal_str = f"${bal_data.get('balance', bal_data.get('amount', bal_data))}"
        else:
            bal_str = str(bal_data)
    except Exception:
        pass
    await state.set_state(AdminApiDeposit.amount)
    await call.message.edit_text(
        f"💰 <b>ដាក់ប្រាក់ចូលវេបសាយ API</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💳 សមតុល្យបច្ចុប្បន្នក្នុងវេបសាយ៖ <b>{escape_html(bal_str)}</b>\n\n"
        f"👉 <b>សូមវាយបញ្ចូលចំនួនទឹកប្រាក់ (USD) ដែលចង់ដាក់ចូលវេបសាយ (ឧ. 10 ឬ 50)៖</b>",
        reply_markup=cancel_inline()
    )

@dp.message(AdminApiDeposit.amount)
async def adm_api_deposit_amount(msg: Message, state: FSMContext):
    try:
        amt = float((msg.text or "").strip().replace("$", ""))
        if amt <= 0:
            raise ValueError("neg")
    except Exception:
        return await msg.answer("❌ សូមបញ្ចូលចំនួនទឹកប្រាក់ជាលេខត្រឹមត្រូវ (ឧ. 10)៖", reply_markup=cancel_inline())

    await state.update_data(api_dep_amt=amt)
    wait_m = await msg.answer("⏳ កំពុងពិនិត្យវិធីបង់ប្រាក់របស់វេបសាយ API...")
    api = ResellerAPIAsync()
    methods = []
    for path in ("/payment-methods", "/deposit/methods", "/deposit-methods"):
        try:
            res = await api._call("GET", path)
            if isinstance(res, list) and res:
                methods = res
                break
            elif isinstance(res, dict) and (res.get("methods") or res.get("data")):
                methods = res.get("methods") or res.get("data")
                break
        except Exception:
            continue

    if not methods:
        # Try direct deposit creation to see if /deposit or /topup exists
        for dep_path in ("/deposit", "/topup", "/aba/deposit"):
            try:
                dep_res = await api._call("POST", dep_path, {"amount": round(amt, 2), "method": "aba"})
                if isinstance(dep_res, dict) and (dep_res.get("qr") or dep_res.get("qr_string") or dep_res.get("qr_image") or dep_res.get("pay_url")):
                    await state.clear()
                    qr_s = dep_res.get("qr") or dep_res.get("qr_string")
                    cap = f"💰 <b>ដាក់ប្រាក់ចូលវេបសាយ (${amt:.2f})</b>\nសូមស្កេន QR ខាងក្រោមដើម្បីដាក់ប្រាក់ចូលវេបសាយ!"
                    if qr_s:
                        await wait_m.delete()
                        return await msg.answer_photo(BufferedInputFile(create_clean_qr_image(qr_s), filename="api_dep.png"), caption=cap)
                    elif dep_res.get("pay_url"):
                        return await wait_m.edit_text(cap + f"\n🔗 {dep_res.get('pay_url')}", reply_markup=admin_back_inline("adm_manage_products"))
            except Exception:
                continue

        await state.clear()
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [IBtn(text="🌐 បើកវេបសាយដាក់ប្រាក់", url="https://reseller.panelkey.shop", style="primary")],
            [IBtn(text="Back", callback_data="adm_manage_products", style="danger", icon_custom_emoji_id="6035130900075777681")]
        ])
        return await wait_m.edit_text(
            f"ℹ️ <b>វេបសាយ API មិនទាន់បើក Endpoint ដាក់ប្រាក់ផ្ទាល់តាម API ទេ</b>\n"
            f"💰 ចំនួនដែលចង់ដាក់៖ <b>${amt:.2f}</b>\n\n"
            f"👉 សូមចុចបូតុងខាងក្រោមដើម្បីចូលទៅដាក់ប្រាក់ក្នុងវេបសាយដោយផ្ទាល់៖",
            reply_markup=kb
        )

    kb_rows = []
    for m_item in methods:
        m_id = m_item.get("id") or m_item.get("code") or m_item.get("name", "aba")
        m_name = m_item.get("name") or str(m_id).upper()
        kb_rows.append([IBtn(text=f"🏦 {m_name} (${amt:.2f})", callback_data=f"apidep_pay_{m_id}", style="primary")])
    kb_rows.append([IBtn(text="Back", callback_data="adm_manage_products", style="danger", icon_custom_emoji_id="6035130900075777681")])
    await wait_m.edit_text(
        f"💰 <b>ដាក់ប្រាក់ចូលវេបសាយ: ${amt:.2f}</b>\n👉 សូមជ្រើសរើសធនាគាររបស់វេបសាយខាងក្រោម៖",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows)
    )

@dp.callback_query(F.data.startswith("apidep_pay_"))
async def adm_api_deposit_exec(call: CallbackQuery, state: FSMContext):
    try: await call.answer()
    except Exception: pass
    method = call.data.replace("apidep_pay_", "")
    data = await state.get_data()
    amt = float(data.get("api_dep_amt", 0))
    await state.clear()
    api = ResellerAPIAsync()
    for dep_path in ("/deposit", "/topup"):
        try:
            dep_res = await api._call("POST", dep_path, {"amount": round(amt, 2), "method": method})
            if isinstance(dep_res, dict):
                qr_s = dep_res.get("qr") or dep_res.get("qr_string")
                if qr_s:
                    await call.message.delete()
                    return await call.message.answer_photo(
                        BufferedInputFile(create_clean_qr_image(qr_s), filename="api_dep.png"),
                        caption=f"💰 <b>ដាក់ប្រាក់ចូលវេបសាយ (${amt:.2f}) - {escape_html(method)}</b>"
                    )
                elif dep_res.get("pay_url"):
                    return await call.message.edit_text(
                        f"💰 <b>ដាក់ប្រាក់ (${amt:.2f})</b>\n🔗 {dep_res.get('pay_url')}",
                        reply_markup=admin_back_inline("adm_manage_products")
                    )
        except Exception:
            continue
    await call.message.edit_text("❌ មិនអាចបង្កើត QR ពីវេបសាយបានទេ!", reply_markup=admin_back_inline("adm_manage_products"))

@dp.callback_query(F.data == "adm_toggle_cat_status")
async def adm_toggle_cat_status_menu(call: CallbackQuery):
    try: await call.answer()
    except Exception: pass
    cats = execute_db('SELECT id, name, COALESCE(is_disabled, 0), icon FROM categories', fetchall=True)
    if not cats:
        return await call.answer("❌ មិនទាន់មានផលិតផលទេ!", show_alert=True)
    kb = []
    for c in cats:
        cid, cname, is_dis, cicon = c
        if is_dis == 1:
            btn_txt = f"🔔បើកមុខងា ({cname})"
            st = "danger"
        else:
            btn_txt = f"🔕បិទមុខងា ({cname})"
            st = "success"
        kb.append([IBtn(text=btn_txt, callback_data=f"togcat_{cid}", style=st, icon_custom_emoji_id=cicon)])
    kb.append([IBtn(text="Back", callback_data="adm_manage_products", style="danger", icon_custom_emoji_id="6035130900075777681")])
    await call.message.edit_text(
        "🔕 <b>បិទ/បើកមុខងារ ផលលិតផល</b>\n👉 ចុចលើផលិតផលណាមួយដើម្បី បិទ ឬ បើក ការទិញ៖",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )

@dp.callback_query(F.data.startswith("togcat_"))
async def adm_toggle_cat_exec(call: CallbackQuery):
    cid = int(call.data.split("_")[1])
    row = execute_db('SELECT COALESCE(is_disabled, 0) FROM categories WHERE id=?', (cid,), fetch=True)
    curr = row[0] if row else 0
    new_val = 0 if curr == 1 else 1
    execute_db('UPDATE categories SET is_disabled=? WHERE id=?', (new_val, cid))
    await call.answer("🔔 បានបើកមុខងារវិញ!" if new_val == 0 else "🔕 បានបិទផលិតផលរួចរាល់!", show_alert=True)
    await adm_toggle_cat_status_menu(call)

@dp.callback_query(F.data == "adm_mgr_api_game")
async def adm_mgr_api_game_handler(call: CallbackQuery):
    try: await call.answer()
    except Exception: pass
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="Add Game", callback_data="adm_api_add_game", style="success", icon_custom_emoji_id="5258508428212445001")],
        [IBtn(text="Delete Game", callback_data="adm_del_cat", style="danger", icon_custom_emoji_id="5258130763148172425")],
        [IBtn(text="Delete Package", callback_data="adm_del_item", style="danger", icon_custom_emoji_id="5258215635996908355")],
        [IBtn(text="ដាក់ប្រាក់ចំណេញ", callback_data="adm_set_profit", style="primary", icon_custom_emoji_id="5814557301196984341")],
        [IBtn(text="ដាក់តម្លៃ Reseller VIP នឹង តម្លៃ Reseller", callback_data="adm_set_reseller_prices", style="primary", icon_custom_emoji_id="5447387942995655277")],
        [IBtn(text="ប្ដូរ api", callback_data="adm_change_api", style="primary", icon_custom_emoji_id="5447420365703773550")],
        [IBtn(text="Back", callback_data="adm_manage_products", style="danger", icon_custom_emoji_id="6035130900075777681")]
    ])
    await call.message.edit_text(
        "<tg-emoji emoji-id=\"5445023138297447592\">🔑</tg-emoji> <b>Manager Add Game / del</b>\nសូមជ្រើសរើសមុខងារខាងក្រោម៖",
        reply_markup=kb
    )

# ====================================================================================================
# [ 🎮 API AUTO ADD GAME / DELETE GAME & PACKAGE / PROFIT / RESELLER VIP PRICE / CHANGE API ]
# ====================================================================================================

def _build_api_game_page_kb(catalog, page=1, per_page=5):
    total = len(catalog)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = start + per_page

    kb_rows = []
    for idx in range(start, min(end, total)):
        prod = catalog[idx]
        p_name = prod.get("name", f"Game {idx+1}")
        pkg_cnt = len(prod.get("packages", []))
        kb_rows.append([IBtn(
            text=f"{p_name} ({pkg_cnt} កញ្ចប់)",
            callback_data=f"apigame_pick_{idx}",
            style="primary",
            icon_custom_emoji_id="5258508428212445001"
        )])

    if total > per_page:
        prev_p = page - 1 if page > 1 else total_pages
        next_p = page + 1 if page < total_pages else 1
        kb_rows.append([
            IBtn(text="⬅️", callback_data=f"apigame_page_{prev_p}", style="primary"),
            IBtn(text=f"📋 {page}/{total_pages}", callback_data="apigame_page_noop", style="primary"),
            IBtn(text="➡️", callback_data=f"apigame_page_{next_p}", style="primary"),
        ])

    kb_rows.append([IBtn(text="Back", callback_data="adm_mgr_api_game", style="danger", icon_custom_emoji_id="6035130900075777681")])
    return InlineKeyboardMarkup(inline_keyboard=kb_rows), page, total_pages

@dp.callback_query(F.data == "adm_api_add_game")
async def adm_api_add_game_start(call: CallbackQuery, state: FSMContext):
    try: await call.answer()
    except Exception: pass
    await state.set_state(AdminApiAddGame.game_name)
    catalog = []
    api_err = None
    try:
        catalog = await ResellerAPIAsync().catalog() or []
    except Exception as e:
        api_err = str(e)

    await state.update_data(api_catalog=catalog)
    kb, page, total_pages = _build_api_game_page_kb(catalog, page=1, per_page=5)

    extra = ""
    if api_err:
        extra = f"\n⚠️ <i>(API ភ្ជាប់បណ្ដោះអាសន្នមិនទាន់បាន: {escape_html(api_err[:80])})</i>"
    await call.message.edit_text(
        f"<tg-emoji emoji-id=\"5258508428212445001\">🎮</tg-emoji> <b>Add Game (Auto API Stock)</b>\n"
        f"📋 <b>ហ្គេមក្នុងវេបសាយសរុប៖ {len(catalog)} ហ្គេម</b>\n\n"
        f"👉 <b>សូមវាយបញ្ចូលឈ្មោះហ្គេមដែលចង់ទាញយក (ឬចុចរើសហ្គេមខាងក្រោម)៖</b>" + extra,
        reply_markup=kb
    )

@dp.callback_query(F.data == "apigame_page_noop")
async def apigame_page_noop_handler(call: CallbackQuery):
    await call.answer()

@dp.callback_query(F.data.startswith("apigame_page_"))
async def apigame_page_nav_handler(call: CallbackQuery, state: FSMContext):
    try: await call.answer()
    except Exception: pass
    page = int(call.data.replace("apigame_page_", ""))
    data = await state.get_data()
    catalog = data.get("api_catalog", [])
    if not catalog:
        try:
            catalog = await ResellerAPIAsync().catalog() or []
            await state.update_data(api_catalog=catalog)
        except Exception:
            pass
    kb, page, total_pages = _build_api_game_page_kb(catalog, page=page, per_page=5)
    try:
        await call.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        await call.message.edit_text(
            f"<tg-emoji emoji-id=\"5258508428212445001\">🎮</tg-emoji> <b>Add Game (Auto API Stock)</b>\n"
            f"📋 <b>ហ្គេមក្នុងវេបសាយសរុប៖ {len(catalog)} ហ្គេម</b>\n\n"
            f"👉 <b>សូមវាយបញ្ចូលឈ្មោះហ្គេមដែលចង់ទាញយក (ឬចុចរើសហ្គេមខាងក្រោម)៖</b>",
            reply_markup=kb
        )

async def _process_selected_api_game(target_msg_or_call, state: FSMContext, prod: dict):
    game_name = prod.get("name", "Game")
    packages = prod.get("packages", [])
    if not packages:
        txt = f"❌ ហ្គេម <b>{escape_html(game_name)}</b> មិនមានកញ្ចប់ (Packages) ក្នុង API ទេ!"
        if isinstance(target_msg_or_call, CallbackQuery):
            return await target_msg_or_call.message.edit_text(txt, reply_markup=admin_back_inline("adm_mgr_api_game"))
        return await target_msg_or_call.answer(txt, reply_markup=admin_back_inline("adm_mgr_api_game"))

    await state.update_data(selected_product=prod)
    profit = float(get_setting("profit_margin", "0") or 0.0)
    kb_rows = []
    for p_idx, p in enumerate(packages):
        stk = "∞" if p.get("stock") is None else str(p.get("stock"))
        api_p = float(p.get("price", 0))
        sell_p = api_p + profit
        kb_rows.append([IBtn(
            text=f"{p.get('name')} | ${sell_p:.2f} (ស្តុក API: {stk})",
            callback_data=f"apipkg_pick_{p_idx}",
            style="primary",
            icon_custom_emoji_id="5258508428212445001"
        )])
    kb_rows.append([IBtn(text="✅ ទាញទាំងអស់ (All Packages)", callback_data="apipkg_pick_all", style="success")])
    kb_rows.append([IBtn(text="Back", callback_data="adm_api_add_game", style="danger", icon_custom_emoji_id="6035130900075777681")])

    txt = (
        f"<tg-emoji emoji-id=\"5258508428212445001\">🎮</tg-emoji> <b>ហ្គេម៖ {escape_html(game_name)}</b>\n"
        f"📦 <b>មានកញ្ចប់សរុប {len(packages)} កញ្ចប់</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👉 <b>សូមចុចជ្រើសរើសកញ្ចប់ដែលចង់ទាញយកស្តុកខាងក្រោម៖</b>"
    )
    if isinstance(target_msg_or_call, CallbackQuery):
        await target_msg_or_call.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
    else:
        await target_msg_or_call.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))

@dp.callback_query(F.data.startswith("apipkg_pick_"))
async def adm_api_pick_package_handler(call: CallbackQuery, state: FSMContext):
    try: await call.answer()
    except Exception: pass
    sel = call.data.replace("apipkg_pick_", "")
    data = await state.get_data()
    prod = data.get("selected_product", {})
    packages = prod.get("packages", [])
    if sel == "all":
        selected_pkgs = packages
        pkg_label = f"ទាំងអស់ ({len(packages)} កញ្ចប់)"
    else:
        idx = int(sel)
        if idx < 0 or idx >= len(packages):
            return await call.message.edit_text("❌ កញ្ចប់មិនត្រឹមត្រូវ!", reply_markup=admin_back_inline("adm_mgr_api_game"))
        selected_pkgs = [packages[idx]]
        pkg_label = packages[idx].get("name", "Package")

    await state.update_data(selected_packages=selected_pkgs)
    await state.set_state(AdminApiAddGame.stock_qty)
    await call.message.edit_text(
        f"📦 <b>កញ្ចប់ដែលបានរើស៖ {escape_html(pkg_label)}</b>\n\n"
        f"📥 <b>តើអ្នកចង់ទាញស្តុកនឹងមកប៉ុន្មាន Key?</b>\n"
        f"<i>(បញ្ចូលជាលេខ ឧ. <code>5</code> ឬ <code>0</code> ប្រសិនបើមិនទាន់ទាញ Key ទេ)</i>",
        reply_markup=cancel_inline()
    )

@dp.callback_query(AdminApiAddGame.game_name, F.data.startswith("apigame_pick_"))
async def adm_api_add_game_pick_btn(call: CallbackQuery, state: FSMContext):
    try: await call.answer()
    except Exception: pass
    idx = int(call.data.split("_")[2])
    data = await state.get_data()
    catalog = data.get("api_catalog", [])
    if idx < 0 or idx >= len(catalog):
        return await call.message.edit_text("❌ ហ្គេមមិនត្រឹមត្រូវ!", reply_markup=admin_back_inline("adm_mgr_api_game"))
    await _process_selected_api_game(call, state, catalog[idx])

@dp.message(AdminApiAddGame.game_name)
async def adm_api_add_game_name_text(msg: Message, state: FSMContext):
    query = (msg.text or "").strip().lower()
    if not query:
        return await msg.answer("❌ សូមវាយបញ្ចូលឈ្មោះហ្គេម!", reply_markup=cancel_inline())
    data = await state.get_data()
    catalog = data.get("api_catalog", [])
    if not catalog:
        try:
            catalog = await ResellerAPIAsync().catalog() or []
            await state.update_data(api_catalog=catalog)
        except Exception as e:
            err_s = str(e)
            hint = ""
            if "403" in err_s or "Just a moment" in err_s:
                hint = "\n\n💡 <i>វេបសាយ API កំពុងបិទ Cloudflare (403)។ សូមដំឡើង <code>pip install cloudscraper curl_cffi</code> លើ Server ឬបើក Whitelist IP លើវេបសាយ API។</i>"
            return await msg.answer(
                f"❌ <b>មិនអាចទាញយកទិន្នន័យពី API បានទេ!</b>\n<code>{escape_html(err_s[:220])}</code>{hint}",
                reply_markup=admin_back_inline("adm_mgr_api_game")
            )
    match = None
    for prod in catalog:
        if prod.get("name", "").strip().lower() == query:
            match = prod
            break
    if not match:
        for prod in catalog:
            if query in prod.get("name", "").strip().lower():
                match = prod
                break
    if not match:
        avail = ", ".join([p.get("name", "") for p in catalog[:15]])
        return await msg.answer(
            f"❌ រកមិនឃើញហ្គេមឈ្មោះ <b>{escape_html(msg.text)}</b> ក្នុង API ទេ!\n\n📋 <b>ហ្គេមដែលមានក្នុង API៖</b> {escape_html(avail)}\n👉 សូមវាយឈ្មោះម្តងទៀត៖",
            reply_markup=cancel_inline()
        )
    await _process_selected_api_game(msg, state, match)

@dp.message(AdminApiAddGame.stock_qty)
async def adm_api_add_game_qty(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    if not txt.isdigit() or int(txt) < 0:
        return await msg.answer("❌ សូមបញ្ចូលចំនួនស្តុកជាលេខត្រឹមត្រូវ (ឧ. 5 ឬ 0)៖", reply_markup=cancel_inline())
    await state.update_data(pull_qty=int(txt))
    await state.set_state(AdminApiAddGame.icon)
    await msg.answer(
        "✨ <b>សូមបញ្ចូល Emoji Premium ឬ ID សម្រាប់ហ្គេមនេះ (ឬចុច រំលង)៖</b>",
        reply_markup=skip_emoji_inline("skip_api_game_emoji")
    )

async def _finalize_api_add_game(target, state: FSMContext, icon_id):
    data = await state.get_data()
    prod = data.get("selected_product", {})
    pull_qty = int(data.get("pull_qty", 0))
    game_name = prod.get("name", "Game")
    packages = data.get("selected_packages") or prod.get("packages", [])
    profit = float(get_setting("profit_margin", "0") or 0.0)

    status_msg = None
    if isinstance(target, CallbackQuery):
        status_msg = await target.message.edit_text(f"⏳ <b>កំពុងបង្កើតហ្គេម {escape_html(game_name)} និងទាញយក Key ពី API អូតូ...</b>")
    else:
        status_msg = await target.answer(f"⏳ <b>កំពុងបង្កើតហ្គេម {escape_html(game_name)} និងទាញយក Key ពី API អូតូ...</b>")

    existing_cat = execute_db('SELECT id FROM categories WHERE LOWER(name)=LOWER(?)', (game_name,), fetch=True)
    if existing_cat:
        cat_id = existing_cat[0]
        if icon_id:
            execute_db('UPDATE categories SET icon=? WHERE id=?', (icon_id, cat_id))
    else:
        cat_id = execute_db('INSERT INTO categories (name, icon) VALUES (?, ?)', (game_name, icon_id))
    api = ResellerAPIAsync()
    total_keys_pulled = 0
    pkg_summaries = []

    for p in packages:
        pkg_id = p.get("package_id")
        pkg_name = p.get("name", f"Package {pkg_id}")
        api_price = float(p.get("price", 0))
        sell_price = round(api_price + profit, 2)
        reseller_price = round(api_price + (profit * 0.5), 2) if profit > 0 else round(api_price, 2)
        vip_price = round(api_price, 2)

        item_id = execute_db(
            'INSERT INTO items (cat_id, name, price, reseller_price, reseller_vip_price, icon, api_package_id) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (cat_id, pkg_name, sell_price, reseller_price, vip_price, icon_id, pkg_id)
        )

        pulled_here = 0
        err_note = ""
        if pull_qty > 0 and pkg_id is not None:
            avail_stk = p.get("stock")
            req_qty = pull_qty if avail_stk is None else min(pull_qty, int(avail_stk))
            if req_qty > 0:
                try:
                    ref = f"bot_{cat_id}_{item_id}_{int(time.time())}"
                    order_res = await api.generate(pkg_id, quantity=req_qty, reference=ref)
                    keys_list = order_res.get("keys") or []
                    for k in keys_list:
                        k_str = str(k).strip()
                        if k_str:
                            execute_db('INSERT INTO stock (item_id, key_data, type) VALUES (?, ?, ?)', (item_id, k_str, 'text'))
                            pulled_here += 1
                    total_keys_pulled += pulled_here
                except Exception as e:
                    err_note = f" ⚠️ ({str(e)[:40]})"
            else:
                err_note = " (ស្តុក API អស់)"

        pkg_summaries.append(f"• {escape_html(pkg_name)} — <b>${sell_price:.2f}</b> | ស្តុកទាញបាន: <b>{pulled_here}</b>{err_note}")

    await state.clear()
    summary = (
        f"✅ <b>បានបន្ថែមហ្គេម {escape_html(game_name)} ចូលហាងអូតូជោគជ័យ!</b>\n"
        f"📦 <b>កញ្ចប់សរុប៖</b> {len(packages)} | 🔑 <b>Key ទាញចូលស្តុកសរុប៖</b> {total_keys_pulled}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        + "\n".join(pkg_summaries)
    )
    if len(summary) > 3950:
        summary = summary[:3950] + "\n..."
    await status_msg.edit_text(summary, reply_markup=admin_back_inline("adm_mgr_api_game"))

@dp.callback_query(AdminApiAddGame.icon, F.data == "skip_api_game_emoji")
async def adm_api_add_game_skip_emoji(call: CallbackQuery, state: FSMContext):
    try: await call.answer()
    except Exception: pass
    await _finalize_api_add_game(call, state, None)

@dp.message(AdminApiAddGame.icon)
async def adm_api_add_game_icon(msg: Message, state: FSMContext):
    icon_id = extract_emoji(msg)
    if not icon_id:
        return await msg.answer("❌ ខុសហើយ! សូមផ្ញើជា Premium Emoji ពិតៗ ឬជាលេខ ID របស់វា (ឬចុច រំលង)៖", reply_markup=skip_emoji_inline("skip_api_game_emoji"))
    await _finalize_api_add_game(msg, state, icon_id)

# --- ដាក់ប្រាក់ចំណេញ (PROFIT MARGIN) ---
@dp.callback_query(F.data == "adm_set_profit")
async def adm_set_profit_handler(call: CallbackQuery, state: FSMContext):
    try: await call.answer()
    except Exception: pass
    curr = float(get_setting("profit_margin", "0") or 0.0)
    await state.set_state(AdminSetProfit.amount)
    await call.message.edit_text(
        f"<tg-emoji emoji-id=\"5814557301196984341\">💰</tg-emoji> <b>ដាក់ប្រាក់ចំណេញ (Profit Margin)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 <b>ប្រាក់ចំណេញបច្ចុប្បន្ន៖</b> <code>+${curr:.2f}</code>\n\n"
        f"👉 សូមវាយបញ្ចូលចំនួនប្រាក់ចំណេញជាដុល្លារ (ឧ. <code>0.5</code> ឬ <code>1.0</code>) ដែលចង់បូកបន្ថែមលើតម្លៃដើមពី API៖",
        reply_markup=cancel_inline()
    )

@dp.message(AdminSetProfit.amount)
async def adm_save_profit_handler(msg: Message, state: FSMContext):
    try:
        amt = float((msg.text or "").strip())
        if amt < 0:
            raise ValueError("negative")
    except Exception:
        return await msg.answer("❌ សូមបញ្ចូលជាលេខត្រឹមត្រូវ (ឧ. 0.5 ឬ 1.0)៖", reply_markup=cancel_inline())
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('profit_margin', str(amt)))
    await state.clear()
    await msg.answer(
        f"✅ <b>បានកំណត់ប្រាក់ចំណេញ +${amt:.2f} ជោគជ័យ!</b>\n"
        f"រាល់ការទាញយកហ្គេមថ្មីពី API នឹងបូកប្រាក់ចំណេញនេះដោយស្វ័យប្រវត្តិ។",
        reply_markup=admin_back_inline("adm_mgr_api_game")
    )

# --- ដាក់តម្លៃ RESELLER VIP នឹង តម្លៃ RESELLER (PICK PACKAGE DIRECTLY) ---
@dp.callback_query(F.data == "adm_set_reseller_prices")
async def adm_set_reseller_prices_menu(call: CallbackQuery):
    try: await call.answer()
    except Exception: pass
    items = execute_db("""
        SELECT items.id, items.name, categories.name, items.reseller_price, items.reseller_vip_price, items.icon
        FROM items
        JOIN categories ON items.cat_id = categories.id
        ORDER BY categories.id, items.id
    """, fetchall=True)
    if not items:
        return await call.answer("❌ មិនទាន់មានកញ្ចប់ទំនិញនៅឡើយទេ!", show_alert=True)
    kb = []
    for i in items:
        r_p = float(i[3] or 0)
        v_p = float(i[4] or 0)
        kb.append([IBtn(
            text=f"{i[2]} - {i[1]} (Res:${r_p:.2f} | VIP:${v_p:.2f})",
            callback_data=f"pkgres_{i[0]}",
            style="primary",
            icon_custom_emoji_id=i[5]
        )])
    kb.append([IBtn(text="Back", callback_data="adm_mgr_api_game", style="danger", icon_custom_emoji_id="6035130900075777681")])
    await call.message.edit_text(
        "<tg-emoji emoji-id=\"5447387942995655277\">💎</tg-emoji> <b>សូមជ្រើសរើសកញ្ចប់ដើម្បីដាក់តម្លៃ Reseller &amp; Reseller VIP៖</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )

@dp.callback_query(F.data.startswith("pkgres_"))
async def adm_pkgres_options(call: CallbackQuery):
    try: await call.answer()
    except Exception: pass
    item_id = int(call.data.split("_")[1])
    row = execute_db("""
        SELECT items.name, categories.name, items.price, items.reseller_price, items.reseller_vip_price
        FROM items JOIN categories ON items.cat_id = categories.id WHERE items.id=?
    """, (item_id,), fetch=True)
    if not row:
        return await call.answer("❌ រកមិនឃើញកញ្ចប់នេះទេ!", show_alert=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text=f"✏️ កែតម្លៃ Reseller (${float(row[3] or 0):.2f})", callback_data=f"edit_pkg_res_{item_id}", style="primary", icon_custom_emoji_id="5447387942995655277")],
        [IBtn(text=f"👑 កែតម្លៃ Reseller VIP (${float(row[4] or 0):.2f})", callback_data=f"edit_pkg_vip_{item_id}", style="success", icon_custom_emoji_id="5447387942995655277")],
        [IBtn(text="Back", callback_data="adm_set_reseller_prices", style="danger", icon_custom_emoji_id="6035130900075777681")]
    ])
    await call.message.edit_text(
        f"📦 <b>កញ្ចប់៖ {escape_html(row[1])} - {escape_html(row[0])}</b>\n"
        f"💵 តម្លៃទូទៅ: <b>${float(row[2] or 0):.2f}</b>\n"
        f"🏷 តម្លៃ Reseller: <b>${float(row[3] or 0):.2f}</b>\n"
        f"👑 តម្លៃ Reseller VIP: <b>${float(row[4] or 0):.2f}</b>",
        reply_markup=kb
    )

@dp.callback_query(F.data.startswith("edit_pkg_res_"))
async def adm_edit_pkg_res_prompt(call: CallbackQuery, state: FSMContext):
    try: await call.answer()
    except Exception: pass
    item_id = int(call.data.replace("edit_pkg_res_", ""))
    await state.update_data(target_pkg_id=item_id)
    await state.set_state(AdminResellerPkgPrice.reseller_price)
    await call.message.edit_text("🏷 <b>សូមបញ្ចូលតម្លៃ Reseller ថ្មី (USD)៖</b>", reply_markup=cancel_inline())

@dp.message(AdminResellerPkgPrice.reseller_price)
async def adm_edit_pkg_res_save(msg: Message, state: FSMContext):
    try:
        val = float((msg.text or "").strip())
    except Exception:
        return await msg.answer("❌ សូមវាយបញ្ចូលជាលេខត្រឹមត្រូវ (ឧ. 3.5)៖", reply_markup=cancel_inline())
    data = await state.get_data()
    item_id = data["target_pkg_id"]
    execute_db('UPDATE items SET reseller_price=? WHERE id=?', (val, item_id))
    await state.clear()
    await msg.answer(f"✅ បានដាក់តម្លៃ Reseller: <b>${val:.2f}</b> ជោគជ័យ!", reply_markup=admin_back_inline("adm_set_reseller_prices"))

@dp.callback_query(F.data.startswith("edit_pkg_vip_"))
async def adm_edit_pkg_vip_prompt(call: CallbackQuery, state: FSMContext):
    try: await call.answer()
    except Exception: pass
    item_id = int(call.data.replace("edit_pkg_vip_", ""))
    await state.update_data(target_pkg_id=item_id)
    await state.set_state(AdminResellerPkgPrice.vip_price)
    await call.message.edit_text("👑 <b>សូមបញ្ចូលតម្លៃ Reseller VIP ថ្មី (USD)៖</b>", reply_markup=cancel_inline())

@dp.message(AdminResellerPkgPrice.vip_price)
async def adm_edit_pkg_vip_save(msg: Message, state: FSMContext):
    try:
        val = float((msg.text or "").strip())
    except Exception:
        return await msg.answer("❌ សូមវាយបញ្ចូលជាលេខត្រឹមត្រូវ (ឧ. 2.5)៖", reply_markup=cancel_inline())
    data = await state.get_data()
    item_id = data["target_pkg_id"]
    execute_db('UPDATE items SET reseller_vip_price=? WHERE id=?', (val, item_id))
    await state.clear()
    await msg.answer(f"✅ បានដាក់តម្លៃ Reseller VIP: <b>${val:.2f}</b> ជោគជ័យ!", reply_markup=admin_back_inline("adm_set_reseller_prices"))

# --- ប្ដូរ API (CHANGE RESELLER WEBSITE API) ---
@dp.callback_query(F.data == "adm_change_api")
async def adm_change_api_menu(call: CallbackQuery):
    try: await call.answer()
    except Exception: pass
    api_url = get_setting('reseller_api_url', 'https://reseller.panelkey.shop/api/v1/reseller') or ''
    api_tok = get_setting('reseller_api_token', '') or ''
    tok_disp = f"{api_tok[:6]}••••••••{api_tok[-4:]}" if len(api_tok) > 10 else (api_tok or "មិនទាន់កំណត់")
    bal_str = "កំពុងពិនិត្យ..."
    try:
        bal_data = await ResellerAPIAsync().balance()
        if isinstance(bal_data, dict):
            bal_val = bal_data.get("balance", bal_data.get("amount", bal_data))
            bal_str = f"${bal_val}"
        else:
            bal_str = str(bal_data)
    except Exception as e:
        bal_str = f"⚠️ Error ({str(e)[:35]})"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="🔑 ប្ដូរ API Token", callback_data="adm_edit_res_api_token", style="primary", icon_custom_emoji_id="5447420365703773550")],
        [IBtn(text="🌐 ប្ដូរ API Base URL", callback_data="adm_edit_res_api_url", style="primary", icon_custom_emoji_id="5447420365703773550")],
        [IBtn(text="🔄 តេស្តការភ្ជាប់ API", callback_data="adm_change_api", style="success")],
        [IBtn(text="Back", callback_data="adm_manage_products", style="danger", icon_custom_emoji_id="6035130900075777681")]
    ])
    await call.message.edit_text(
        f"<tg-emoji emoji-id=\"5447420365703773550\">🔌</tg-emoji> <b>កំណត់ និងប្ដូរ API វេបសាយ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🌐 <b>Base URL:</b> <code>{escape_html(api_url)}</code>\n"
        f"🔑 <b>API Token:</b> <code>{tok_disp}</code>\n"
        f"💰 <b>Balance API:</b> <b>{escape_html(bal_str)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👉 សូមជ្រើសរើសបូតុងខាងក្រោមដើម្បីប្ដូរ API វេបសាយ៖",
        reply_markup=kb
    )

@dp.callback_query(F.data == "adm_edit_res_api_token")
async def adm_edit_res_api_token_prompt(call: CallbackQuery, state: FSMContext):
    try: await call.answer()
    except Exception: pass
    await state.set_state(AdminChangeApi.api_token)
    await call.message.edit_text("🔑 <b>សូមបញ្ចូល API Token ថ្មីរបស់វេបសាយ៖</b>", reply_markup=cancel_inline())

@dp.message(AdminChangeApi.api_token)
async def adm_edit_res_api_token_save(msg: Message, state: FSMContext):
    tok = (msg.text or "").strip()
    if not tok:
        return await msg.answer("❌ សូមបញ្ចូល Token ត្រឹមត្រូវ!", reply_markup=cancel_inline())
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('reseller_api_token', tok))
    await state.clear()
    await msg.answer("✅ <b>បានប្ដូរ API Token ជោគជ័យ!</b>", reply_markup=admin_back_inline("adm_change_api"))

@dp.callback_query(F.data == "adm_edit_res_api_url")
async def adm_edit_res_api_url_prompt(call: CallbackQuery, state: FSMContext):
    try: await call.answer()
    except Exception: pass
    await state.set_state(AdminChangeApi.api_url)
    await call.message.edit_text("🌐 <b>សូមបញ្ចូល API Base URL ថ្មី (ឧ. https://reseller.panelkey.shop/api/v1/reseller)៖</b>", reply_markup=cancel_inline())

@dp.message(AdminChangeApi.api_url)
async def adm_edit_res_api_url_save(msg: Message, state: FSMContext):
    url = (msg.text or "").strip().rstrip('/')
    if not url.startswith("http"):
        return await msg.answer("❌ URL ត្រូវចាប់ផ្ដើមដោយ http:// ឬ https://", reply_markup=cancel_inline())
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('reseller_api_url', url))
    await state.clear()
    await msg.answer(f"✅ <b>បានប្ដូរ API Base URL ទៅជា:</b> <code>{escape_html(url)}</code>", reply_markup=admin_back_inline("adm_change_api"))

# --- RENAME CATEGORY HANDLERS ---
@dp.callback_query(F.data == "adm_rename_cat")
async def adm_rename_cat_menu(call: CallbackQuery):
    cats = execute_db('SELECT id, name FROM categories', fetchall=True)
    if not cats: return await call.answer("❌ មិនទាន់មាន Category ទេ!", show_alert=True)
    kb = [[IBtn(text=f"✏️ {c[1]}", callback_data=f"rencat_{c[0]}", style="primary")] for c in cats]
    kb.append([IBtn(text="Back", callback_data="adm_manage_products", style="danger", icon_custom_emoji_id="6035130900075777681")])
    await call.message.edit_text("📂 <b>ជ្រើសរើស ផលលិតផល ដែលចង់កែឈ្មោះ៖</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data.startswith("rencat_"))
async def adm_rename_cat_prompt(call: CallbackQuery, state: FSMContext):
    cat_id = int(call.data.split("_")[1])
    cat = execute_db('SELECT name FROM categories WHERE id=?', (cat_id,), fetch=True)
    cat_name = cat[0] if cat else ""
    await state.update_data(cat_id=cat_id, old_name=cat_name)
    await call.message.edit_text(f"✏️ <b>សូមបញ្ចូលឈ្មោះថ្មីសម្រាប់ផលលិតផល: {cat_name}</b> ៖", reply_markup=cancel_inline())
    await state.set_state(AdminRenameCat.name)
    await call.answer()

@dp.message(AdminRenameCat.name)
async def adm_save_rename_cat(msg: Message, state: FSMContext):
    new_name = (msg.text or "").strip()
    if not new_name:
        return await msg.answer("❌ សូមបញ្ចូលឈ្មោះត្រឹមត្រូវ!", reply_markup=cancel_inline())
    await state.update_data(new_name=new_name)
    await msg.answer("✨ សូមបញ្ចូល Emoji Premium ឬ ID ថ្មីសម្រាប់ផលលិតផលនេះ (ឬចុច រំលង ប្រសិនបើចង់រក្សាទុក Emoji ចាស់) ៖", reply_markup=skip_emoji_inline("skip_ren_cat_emoji"))
    await state.set_state(AdminRenameCat.icon)

@dp.callback_query(AdminRenameCat.icon, F.data == "skip_ren_cat_emoji")
async def adm_save_rename_cat_skip(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cat_id = data['cat_id']
    new_name = data['new_name']
    execute_db('UPDATE categories SET name=? WHERE id=?', (new_name, cat_id))
    await call.message.edit_text(f"✅ បានកែឈ្មោះផលលិតផលជា៖ <b>{new_name}</b> ជោគជ័យ!", reply_markup=admin_back_inline("adm_mgr_api_game"))
    await state.clear()
    await call.answer()

@dp.message(AdminRenameCat.icon)
async def adm_save_rename_cat_icon(msg: Message, state: FSMContext):
    icon_id = extract_emoji(msg)
    if not icon_id:
        return await msg.answer("❌ ខុសហើយ! សូមផ្ញើជា Premium Emoji ពិតៗ ឬជាលេខ ID របស់វា (ឬចុច រំលង) ៖", reply_markup=skip_emoji_inline("skip_ren_cat_emoji"))
    data = await state.get_data()
    cat_id = data['cat_id']
    new_name = data['new_name']
    execute_db('UPDATE categories SET name=?, icon=? WHERE id=?', (new_name, icon_id, cat_id))
    await msg.answer(f"✅ បានកែឈ្មោះផលលិតផលជា៖ <b>{new_name}</b> និងកំណត់ Emoji ជោគជ័យ!", reply_markup=admin_back_inline("adm_mgr_api_game"))
    await state.clear()

# --- RENAME ITEM HANDLERS ---
@dp.callback_query(F.data == "adm_rename_item")
async def adm_rename_item_pick_cat(call: CallbackQuery):
    cats = execute_db('SELECT id, name FROM categories', fetchall=True)
    if not cats: return await call.answer("❌ មិនទាន់មាន Category ទេ!", show_alert=True)
    kb = [[IBtn(text=c[1], callback_data=f"renitemcat_{c[0]}", style="primary")] for c in cats]
    kb.append([IBtn(text="Back", callback_data="adm_manage_products", style="danger", icon_custom_emoji_id="6035130900075777681")])
    await call.message.edit_text("📂 <b>ជ្រើសរើស ផលលិតផល ដើម្បីកែឈ្មោះទំនិញខាងក្នុង៖</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data.startswith("renitemcat_"))
async def adm_rename_item_list(call: CallbackQuery):
    cat_id = int(call.data.split("_")[1])
    items = execute_db('SELECT id, name FROM items WHERE cat_id=?', (cat_id,), fetchall=True)
    if not items: return await call.answer("❌ មិនមានទំនិញក្នុងផលលិតផលនេះទេ!", show_alert=True)
    kb = [[IBtn(text=f"✏️ {i[1]}", callback_data=f"renitempick_{i[0]}", style="primary")] for i in items]
    kb.append([IBtn(text="Back", callback_data="adm_rename_item", style="danger", icon_custom_emoji_id="6035130900075777681")])
    await call.message.edit_text("📦 <b>ជ្រើសរើស ទំនិញ ដែលចង់កែឈ្មោះ៖</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data.startswith("renitempick_"))
async def adm_rename_item_prompt(call: CallbackQuery, state: FSMContext):
    item_id = int(call.data.split("_")[1])
    item = execute_db('SELECT name FROM items WHERE id=?', (item_id,), fetch=True)
    item_name = item[0] if item else ""
    await state.update_data(item_id=item_id, old_name=item_name)
    await call.message.edit_text(f"✏️ <b>សូមបញ្ចូលឈ្មោះថ្មីសម្រាប់ទំនិញ: {item_name}</b> ៖", reply_markup=cancel_inline())
    await state.set_state(AdminRenameItem.name)
    await call.answer()

@dp.message(AdminRenameItem.name)
async def adm_save_rename_item(msg: Message, state: FSMContext):
    new_name = (msg.text or "").strip()
    if not new_name:
        return await msg.answer("❌ សូមបញ្ចូលឈ្មោះត្រឹមត្រូវ!", reply_markup=cancel_inline())
    await state.update_data(new_name=new_name)
    await msg.answer("✨ សូមបញ្ចូល Emoji Premium ឬ ID ថ្មីសម្រាប់ទំនិញនេះ (ឬចុច រំលង ប្រសិនបើចង់រក្សាទុក Emoji ចាស់) ៖", reply_markup=skip_emoji_inline("skip_ren_item_emoji"))
    await state.set_state(AdminRenameItem.icon)

@dp.callback_query(AdminRenameItem.icon, F.data == "skip_ren_item_emoji")
async def adm_save_rename_item_skip(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    item_id = data['item_id']
    new_name = data['new_name']
    execute_db('UPDATE items SET name=? WHERE id=?', (new_name, item_id))
    await call.message.edit_text(f"✅ បានកែឈ្មោះទំនិញជា៖ <b>{new_name}</b> ជោគជ័យ!", reply_markup=admin_back_inline("adm_mgr_api_game"))
    await state.clear()
    await call.answer()

@dp.message(AdminRenameItem.icon)
async def adm_save_rename_item_icon(msg: Message, state: FSMContext):
    icon_id = extract_emoji(msg)
    if not icon_id:
        return await msg.answer("❌ ខុសហើយ! សូមផ្ញើជា Premium Emoji ពិតៗ ឬជាលេខ ID របស់វា (ឬចុច រំលង) ៖", reply_markup=skip_emoji_inline("skip_ren_item_emoji"))
    data = await state.get_data()
    item_id = data['item_id']
    new_name = data['new_name']
    execute_db('UPDATE items SET name=?, icon=? WHERE id=?', (new_name, icon_id, item_id))
    await msg.answer(f"✅ បានកែឈ្មោះទំនិញជា៖ <b>{new_name}</b> និងកំណត់ Emoji ជោគជ័យ!", reply_markup=admin_back_inline("adm_mgr_api_game"))
    await state.clear()

# --- INFINITE STOCK HANDLERS ---
@dp.callback_query(F.data.startswith("addinf_"))
async def add_inf_prompt(call: CallbackQuery, state: FSMContext):
    item_id = int(call.data.split("_")[1])
    item = execute_db('SELECT name FROM items WHERE id=?', (item_id,), fetch=True)
    item_name = item[0] if item else ""
    await state.update_data(item_id=item_id)
    await call.message.edit_text(f"♾ <b>សូមផ្ញើទិន្នន័យ (Key / File / Link / រូបភាព / វីដេអូ ឬអត្ថបទ) សម្រាប់ស្តុកមិនចេះអស់ [{item_name}]៖</b>\n\n(ពេលភ្ញៀវទិញ ប្រព័ន្ធនឹងទម្លាក់ទិន្នន័យនេះជានិច្ច គ្មានថ្ងៃអស់ស្តុកឡើយ)៖", reply_markup=cancel_inline())
    await state.set_state(AdminAddInfinite.data)
    await call.answer()

@dp.message(AdminAddInfinite.data)
async def save_inf_data(msg: Message, state: FSMContext):
    data = await state.get_data()
    item_id = data['item_id']
    if msg.photo: val = f"photo:{msg.photo[-1].file_id}"
    elif msg.video: val = f"video:{msg.video.file_id}"
    elif msg.document: val = f"document:{msg.document.file_id}"
    elif msg.text: val = f"text:{msg.text.strip()}"
    else: return await msg.answer("❌ មិនគាំទ្រទម្រង់នេះទេ!", reply_markup=cancel_inline())
    execute_db('UPDATE items SET is_infinite=1, infinite_data=? WHERE id=?', (val, item_id))
    await msg.answer("✅ <b>បានកំណត់ស្តុកមិនចេះអស់ (Infinite Stock) ជោគជ័យ!</b>\nឥឡូវនេះភ្ញៀវទិញទំនិញនេះយ៉ាងណាក៏មិនអស់ស្តុកដែរ។", reply_markup=admin_back_inline("adm_manage_stock"))
    await state.clear()
    
    # Broadcast new stock alert to users
    item_info = execute_db('SELECT items.name, categories.name FROM items JOIN categories ON items.cat_id = categories.id WHERE items.id=?', (item_id,), fetch=True)
    item_name = item_info[0] if item_info else "ទំនិញ"
    cat_name = item_info[1] if item_info else "ផលិតផល"
    alert = f"""<tg-emoji emoji-id="6269366244462301331">📦</tg-emoji> <b>ស្តុកថ្មីបានមកដល់ហើយ!</b>
━━━━━━━━━━━━━━━━━━━━━
- ទំនិញ៖ <b>{cat_name}</b>
- កញ្ចប់៖ <b>{item_name}</b>
- ចំនួនបន្ថែមថ្មី៖ <b>∞ មិនចេះអស់</b>
━━━━━━━━━━━━━━━━━━━━━
<tg-emoji emoji-id="5904704361182798355">⚡</tg-emoji> <b>រួចរាល់សម្រាប់ទិញឥឡូវនេះ!</b>
👉 ចុចប៊ូតុង <tg-emoji emoji-id="5445146945024720188">🛒</tg-emoji> ខាងក្រោមដើម្បីទិញ ៖"""
    kb = InlineKeyboardMarkup(inline_keyboard=[[IBtn(text="Buy Now / ទិញឥឡូវនេះ", callback_data="buy_now_direct", style="primary", icon_custom_emoji_id="5445146945024720188")]])
    users = execute_db('SELECT id FROM users', fetchall=True)
    for u in users:
        try: await bot.send_message(u[0], alert, reply_markup=kb)
        except: pass

@dp.callback_query(F.data.startswith("delinf_"))
async def del_inf_data(call: CallbackQuery):
    item_id = int(call.data.split("_")[1])
    execute_db('UPDATE items SET is_infinite=0, infinite_data=NULL WHERE id=?', (item_id,))
    await call.answer("✅ បានដកស្តុកមិនចេះអស់រួចរាល់!", show_alert=True)
    await stk_options(call)


def extract_emoji(msg: Message):
    if msg.entities:
        for ent in msg.entities:
            if ent.type == "custom_emoji": return ent.custom_emoji_id
    if msg.text:
        txt = msg.text.strip()
        return txt
    return None

@dp.callback_query(F.data == "adm_add_cat")
async def adm_add_cat_1(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("📝 សូមបញ្ចូល ឈ្មោះផលិតផល (Category):", reply_markup=cancel_inline())
    await state.set_state(AdminAddCat.name)
    await call.answer()

@dp.message(AdminAddCat.name)
async def adm_add_cat_2(msg: Message, state: FSMContext):
    await state.update_data(name=msg.text)
    await msg.answer("✨ សូមបញ្ចូល Emoji Premium ឬ ID Premium សម្រាប់ផលិតផលនេះ:", reply_markup=skip_emoji_inline("skip_cat_emoji"))
    await state.set_state(AdminAddCat.icon)

@dp.callback_query(AdminAddCat.icon, F.data == "skip_cat_emoji")
async def adm_add_cat_skip_emoji(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    execute_db('INSERT INTO categories (name, icon) VALUES (?, ?)', (data['name'], None))
    await call.message.edit_text("✅ បង្កើតផលិតផលជោគជ័យ!", reply_markup=admin_back_inline("adm_manage_products"))
    await state.clear()
    await call.answer()

@dp.message(AdminAddCat.icon)
async def adm_add_cat_3(msg: Message, state: FSMContext):
    icon_id = extract_emoji(msg)
    if not icon_id: return await msg.answer("❌ ខុសហើយ! សូមផ្ញើជា Premium Emoji ពិតៗ ឬជាលេខ ID Premium របស់វា (ឬចុច រំលង):", reply_markup=skip_emoji_inline("skip_cat_emoji"))
    data = await state.get_data()
    execute_db('INSERT INTO categories (name, icon) VALUES (?, ?)', (data['name'], icon_id))
    await msg.answer(render_clean_text(f"✅ បង្កើតផលិតផល {get_emoji_str(icon_id)} <b>{escape_html(data['name'])}</b> ជោគជ័យ!"), reply_markup=admin_back_inline("adm_manage_products"))
    await state.clear()

@dp.callback_query(F.data == "adm_del_cat")
async def adm_del_cat(call: CallbackQuery):
    cats = execute_db('SELECT id, name FROM categories', fetchall=True)
    kb = [[IBtn(text=f"🗑 {c[1]}", callback_data=f"docdelcat_{c[0]}", style="danger")] for c in cats]
    kb.append([IBtn(text="Back", callback_data="adm_manage_products", style="danger", icon_custom_emoji_id="6035130900075777681")])
    await call.message.edit_text("ជ្រើសរើសផលិតផលដើម្បីលុប:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data.startswith("docdelcat_"))
async def doc_del_cat(call: CallbackQuery):
    cid = int(call.data.split("_")[1])
    cat_items = execute_db('SELECT id FROM items WHERE cat_id=?', (cid,), fetchall=True) or []
    for it in cat_items:
        execute_db('DELETE FROM stock WHERE item_id=?', (it[0],))
    execute_db('DELETE FROM items WHERE cat_id=?', (cid,))
    execute_db('DELETE FROM categories WHERE id=?', (cid,))
    await call.answer("✅ លុបហ្គេម និងកញ្ចប់ទាំងអស់រួចរាល់!", show_alert=True)
    await adm_del_cat(call)

@dp.callback_query(F.data == "adm_add_item")
async def adm_add_item_1(call: CallbackQuery, state: FSMContext):
    cats = execute_db('SELECT id, name, icon FROM categories', fetchall=True)
    if not cats: return await call.answer("ត្រូវបង្កើតផលិតផល (Category) ជាមុនសិន!", show_alert=True)
    kb = [[IBtn(text=c[1], callback_data=f"setcat_{c[0]}", style="primary", icon_custom_emoji_id=c[2])] for c in cats]
    kb.append([IBtn(text="Back", callback_data="adm_manage_products", style="danger", icon_custom_emoji_id="6035130900075777681")])
    await call.message.edit_text("📂 ជ្រើសរើស ផលិតផល ដែលចង់បង្កើតកញ្ចប់ចូល:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data.startswith("setcat_"))
async def adm_add_item_2(call: CallbackQuery, state: FSMContext):
    await state.update_data(cat_id=int(call.data.split("_")[1]))
    await call.message.edit_text("📝 សូមបញ្ចូល ឈ្មោះកញ្ចប់:", reply_markup=cancel_inline())
    await state.set_state(AdminAddItem.name)
    await call.answer()

@dp.message(AdminAddItem.name)
async def adm_add_item_3(msg: Message, state: FSMContext):
    await state.update_data(name=msg.text)
    await msg.answer("💰 សូមបងដាក់ តម្លៃទូរទៅ មក ឧ. 0.34", reply_markup=cancel_inline())
    await state.set_state(AdminAddItem.price)

@dp.message(AdminAddItem.price)
async def adm_add_item_4(msg: Message, state: FSMContext):
    try:
        await state.update_data(price=float(msg.text))
        await msg.answer("💸 សូមបងដាក់តម្លៃ Resellers ធម្មតាមក ឧ . 0.10", reply_markup=cancel_inline())
        await state.set_state(AdminAddItem.reseller_price)
    except: await msg.answer("❌ លេខមិនត្រឹមត្រូវ!")

@dp.message(AdminAddItem.reseller_price)
async def adm_add_item_5(msg: Message, state: FSMContext):
    try:
        await state.update_data(reseller_price=float(msg.text))
        await msg.answer("💎 សូមបងដាកតម្លៃ Resellers VIP មក ឧ . 0.08", reply_markup=cancel_inline())
        await state.set_state(AdminAddItem.reseller_vip_price)
    except: await msg.answer("❌ លេខមិនត្រឹមត្រូវ!")

@dp.message(AdminAddItem.reseller_vip_price)
async def adm_add_item_vip_price(msg: Message, state: FSMContext):
    try:
        await state.update_data(reseller_vip_price=float(msg.text))
        await msg.answer("✨ សូមបញ្ចូល Emoji Premium ឬ ID Premium សម្រាប់កញ្ចប់នេះ:", reply_markup=skip_emoji_inline("skip_item_emoji"))
        await state.set_state(AdminAddItem.icon)
    except: await msg.answer("❌ លេខមិនត្រឹមត្រូវ!")

@dp.callback_query(AdminAddItem.icon, F.data == "skip_item_emoji")
async def adm_add_item_skip_emoji(call: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    execute_db('INSERT INTO items (cat_id, name, price, reseller_price, reseller_vip_price, icon) VALUES (?,?,?,?,?,?)', (d['cat_id'], d['name'], d['price'], d['reseller_price'], d.get('reseller_vip_price', 0.0), None))
    await call.message.edit_text("✅ បង្កើតកញ្ចប់ជោគជ័យ!", reply_markup=admin_back_inline("adm_manage_products"))
    await state.clear()
    await call.answer()

@dp.message(AdminAddItem.icon)
async def adm_add_item_6(msg: Message, state: FSMContext):
    icon_id = extract_emoji(msg)
    if not icon_id: return await msg.answer("❌ ខុសហើយ! សូមផ្ញើជា Premium Emoji ពិតៗ ឬជាលេខ ID Premium របស់វា (ឬចុច រំលង):", reply_markup=skip_emoji_inline("skip_item_emoji"))
    d = await state.get_data()
    execute_db('INSERT INTO items (cat_id, name, price, reseller_price, reseller_vip_price, icon) VALUES (?,?,?,?,?,?)', (d['cat_id'], d['name'], d['price'], d['reseller_price'], d.get('reseller_vip_price', 0.0), icon_id))
    await msg.answer(render_clean_text(f"✅ បង្កើតកញ្ចប់ {get_emoji_str(icon_id)} <b>{escape_html(d['name'])}</b> ជោគជ័យ!"), reply_markup=admin_back_inline("adm_manage_products"))
    await state.clear()

@dp.callback_query(F.data == "adm_del_item")
async def adm_del_item(call: CallbackQuery):
    items = execute_db('SELECT items.id, items.name, categories.name FROM items JOIN categories ON items.cat_id = categories.id ORDER BY categories.id, items.id', fetchall=True)
    if not items:
        return await call.answer("❌ មិនមានកញ្ចប់ទំនិញសម្រាប់លុបទេ!", show_alert=True)
    kb = [[IBtn(text=f"🗑 {i[2]} - {i[1]}", callback_data=f"docdelitem_{i[0]}", style="danger", icon_custom_emoji_id="5258215635996908355")] for i in items]
    kb.append([IBtn(text="Back", callback_data="adm_manage_products", style="danger", icon_custom_emoji_id="6035130900075777681")])
    await call.message.edit_text("🗑 <b>ជ្រើសរើសកញ្ចប់ (Package) ដើម្បីលុប៖</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data.startswith("docdelitem_"))
async def doc_del_item(call: CallbackQuery):
    iid = int(call.data.split("_")[1])
    execute_db('DELETE FROM stock WHERE item_id=?', (iid,))
    execute_db('DELETE FROM items WHERE id=?', (iid,))
    await call.answer("✅ លុបកញ្ចប់រួចរាល់!", show_alert=True)
    await adm_del_item(call)

@dp.callback_query(F.data == "adm_add_cat_media")
async def set_cat_media(call: CallbackQuery):
    cats = execute_db('SELECT id, name FROM categories', fetchall=True)
    kb = [[IBtn(text=c[1], callback_data=f"setcatmd_{c[0]}", style="primary")] for c in cats]
    kb.append([IBtn(text="Back", callback_data="adm_manage_products", style="danger", icon_custom_emoji_id="6035130900075777681")])
    await call.message.edit_text("ជ្រើសរើស Category ដើម្បីដាក់វីដេអូ/រូបភាព:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data.startswith("setcatmd_"))
async def set_cat_media2(call: CallbackQuery, state: FSMContext):
    await state.update_data(cat_id=int(call.data.split("_")[1]))
    await call.message.edit_text("ផ្ញើ វីដេអូ ឬ រូបភាពមកទីនេះ:", reply_markup=cancel_inline())
    await state.set_state(AdminCatMedia.media)
    await call.answer()

@dp.message(AdminCatMedia.media)
async def set_cat_media3(msg: Message, state: FSMContext):
    cat_id = (await state.get_data())['cat_id']
    if msg.photo: val = f"photo:{msg.photo[-1].file_id}"
    elif msg.video: val = f"video:{msg.video.file_id}"
    else: return await msg.answer("❌ សូមផ្ញើតែរូបភាព ឬ វីដេអូប៉ុណ្ណោះ!", reply_markup=cancel_inline())
    execute_db('UPDATE categories SET media_data=? WHERE id=?', (val, cat_id))
    await msg.answer("✅ ដាក់ជោគជ័យ!", reply_markup=admin_back_inline("adm_mgr_api_game"))
    await state.clear()

@dp.callback_query(F.data == "adm_del_cat_media")
async def del_cat_media(call: CallbackQuery):
    cats = execute_db('SELECT id, name FROM categories', fetchall=True)
    kb = [[IBtn(text=c[1], callback_data=f"delcatmd_{c[0]}", style="danger")] for c in cats]
    kb.append([IBtn(text="Back", callback_data="adm_manage_products", style="danger", icon_custom_emoji_id="6035130900075777681")])
    await call.message.edit_text("ជ្រើសរើស Category ដើម្បីលុបវីដេអូ/រូបភាព:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data.startswith("delcatmd_"))
async def del_cat_media2(call: CallbackQuery):
    execute_db('UPDATE categories SET media_data=NULL WHERE id=?', (int(call.data.split("_")[1]),))
    await call.answer("✅ លុបរួចរាល់!", show_alert=True)
    await del_cat_media(call)

# --- MANAGE CATEGORY / PRODUCT DESCRIPTION ---
@dp.callback_query(F.data == "adm_add_cat_desc")
async def adm_add_cat_desc_start(call: CallbackQuery):
    cats = execute_db('SELECT id, name FROM categories', fetchall=True)
    if not cats:
        return await call.answer("❌ ត្រូវបង្កើតផលិតផល (Category) ជាមុនសិន!", show_alert=True)
    kb = [[IBtn(text=c[1], callback_data=f"setcatdesc_{c[0]}", style="primary")] for c in cats]
    kb.append([IBtn(text="Back", callback_data="adm_manage_products", style="danger", icon_custom_emoji_id="6035130900075777681")])
    await call.message.edit_text("📂 <b>ជ្រើសរើស ផលិតផល ដែលចង់ដាក់អត្ថបទ៖</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data.startswith("setcatdesc_"))
async def adm_add_cat_desc_prompt(call: CallbackQuery, state: FSMContext):
    cat_id = int(call.data.split("_")[1])
    cat = execute_db('SELECT name FROM categories WHERE id=?', (cat_id,), fetch=True)
    cat_name = cat[0] if cat else ""
    await state.update_data(cat_id=cat_id)
    await call.message.edit_text(f"📝 <b>សូមផ្ញើអត្ថបទសម្រាប់ផលិតផល: {cat_name}</b>\n\n(អាចប្រើ Emoji Premium, ពណ៌, បន្ទាត់ និងការតុបតែងអក្សរបានគ្រប់បែបយ៉ាង)៖", reply_markup=cancel_inline())
    await state.set_state(AdminCatDesc.text)
    await call.answer()

@dp.message(AdminCatDesc.text)
async def adm_save_cat_desc(msg: Message, state: FSMContext):
    data = await state.get_data()
    cat_id = data.get("cat_id")
    desc_html = msg.html_text if (msg.text or msg.caption) else None
    if not desc_html:
        return await msg.answer("❌ សូមផ្ញើជាអត្ថបទ!", reply_markup=cancel_inline())
    execute_db('UPDATE categories SET description=? WHERE id=?', (desc_html, cat_id))
    await msg.answer("✅ <b>បានដាក់អត្ថបទលើផលិតផលជោគជ័យ!</b>\nអត្ថបទនឹងបង្ហាញលើផលិតផលភ្លាមៗដូចក្នុងគំរូ។", reply_markup=admin_back_inline("adm_mgr_api_game"))
    await state.clear()

@dp.callback_query(F.data == "adm_del_cat_desc")
async def adm_del_cat_desc_start(call: CallbackQuery):
    cats = execute_db('SELECT id, name FROM categories WHERE description IS NOT NULL AND description != ""', fetchall=True)
    if not cats:
        return await call.answer("ℹ️ មិនទាន់មានផលិតផលណាមានអត្ថបទនៅឡើយទេ!", show_alert=True)
    kb = [[IBtn(text=f"🗑 {c[1]}", callback_data=f"deldoccatdesc_{c[0]}", style="danger")] for c in cats]
    kb.append([IBtn(text="Back", callback_data="adm_manage_products", style="danger", icon_custom_emoji_id="6035130900075777681")])
    await call.message.edit_text("🗑 <b>ជ្រើសរើស ផលិតផល ដែលចង់ដកអត្ថបទចេញ៖</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data.startswith("deldoccatdesc_"))
async def adm_del_cat_desc_exec(call: CallbackQuery):
    cat_id = int(call.data.split("_")[1])
    execute_db('UPDATE categories SET description=NULL WHERE id=?', (cat_id,))
    await call.answer("✅ បានដកអត្ថបទចេញជោគជ័យ!", show_alert=True)
    await adm_del_cat_desc_start(call)

@dp.callback_query(F.data == "adm_add_post_media")
async def set_post_media(call: CallbackQuery):
    items = execute_db('SELECT items.id, items.name, categories.name, items.icon FROM items JOIN categories ON items.cat_id = categories.id ORDER BY categories.id, items.id', fetchall=True)
    kb = [[IBtn(text=f"{i[2]} - {i[1]}", callback_data=f"setpostmd_{i[0]}", style="primary", icon_custom_emoji_id=i[3])] for i in items]
    kb.append([IBtn(text="Back", callback_data="adm_manage_products", style="danger", icon_custom_emoji_id="6035130900075777681")])
    await call.message.edit_text("ជ្រើសរើសទំនិញ ដើម្បីដាក់ Media ក្រោយពេលទិញរួច:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data.startswith("setpostmd_"))
async def set_post_media2(call: CallbackQuery, state: FSMContext):
    await state.update_data(item_id=int(call.data.split("_")[1]))
    await call.message.edit_text("ផ្ញើ វីដេអូ/រូបភាព/File/Text/សំឡេង មកទីនេះ (អាចដាក់វីដេអូ/រូបភាព/File ភ្ជាប់ជាមួយអត្ថបទ ឬ លីង ក្នុងសារតែមួយក៏បាន ឬបន្ថែមច្រើនដងក៏បាន):", reply_markup=cancel_inline())
    await state.set_state(AdminPostMedia.media)
    await call.answer()

@dp.message(AdminPostMedia.media)
async def set_post_media3(msg: Message, state: FSMContext):
    item_id = (await state.get_data())['item_id']
    caption_html = msg.html_text if (msg.caption or msg.text) else None
    
    if msg.photo: new_entry = {'type': 'photo', 'content': msg.photo[-1].file_id, 'caption': caption_html}
    elif msg.video: new_entry = {'type': 'video', 'content': msg.video.file_id, 'caption': caption_html}
    elif msg.document: new_entry = {'type': 'document', 'content': msg.document.file_id, 'caption': caption_html}
    elif msg.audio: new_entry = {'type': 'audio', 'content': msg.audio.file_id, 'caption': caption_html}
    elif msg.voice: new_entry = {'type': 'voice', 'content': msg.voice.file_id, 'caption': caption_html}
    elif msg.text: new_entry = {'type': 'text', 'content': msg.html_text, 'caption': None}
    else: return await msg.answer("❌ មិនគាំទ្រទម្រង់នេះទេ!", reply_markup=cancel_inline())

    row = execute_db('SELECT post_media FROM items WHERE id=?', (item_id,), fetch=True)
    existing_raw = row[0] if row else None
    media_list = []
    if existing_raw:
        try:
            loaded = json.loads(existing_raw)
            if isinstance(loaded, list): media_list = loaded
            elif isinstance(loaded, dict): media_list = [loaded]
        except:
            if ':' in existing_raw:
                m_type, content = existing_raw.split(':', 1)
                media_list = [{'type': m_type, 'content': content, 'caption': None}]
                
    media_list.append(new_entry)
    execute_db('UPDATE items SET post_media=? WHERE id=?', (json.dumps(media_list, ensure_ascii=False), item_id))
    await msg.answer("✅ ដាក់ជោគជ័យ! (រក្សាទុកទាំង Media និង អត្ថបទ/Link រួចរាល់)", reply_markup=admin_back_inline("adm_mgr_api_game"))
    await state.clear()

@dp.callback_query(F.data == "adm_del_post_media")
async def del_post_media(call: CallbackQuery):
    items = execute_db('SELECT items.id, items.name, categories.name, items.icon FROM items JOIN categories ON items.cat_id = categories.id ORDER BY categories.id, items.id', fetchall=True)
    kb = [[IBtn(text=f"{i[2]} - {i[1]}", callback_data=f"delpostmd_{i[0]}", style="danger", icon_custom_emoji_id=i[3])] for i in items]
    kb.append([IBtn(text="Back", callback_data="adm_manage_products", style="danger", icon_custom_emoji_id="6035130900075777681")])
    await call.message.edit_text("ជ្រើសរើសទំនិញ ដើម្បីលុប Media:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data.startswith("delpostmd_"))
async def del_post_media2(call: CallbackQuery):
    execute_db('UPDATE items SET post_media=NULL WHERE id=?', (int(call.data.split("_")[1]),))
    await call.answer("✅ លុបរួចរាល់!", show_alert=True)
    await del_post_media(call)

# --- MANAGE STOCK ---
@dp.callback_query(F.data.startswith("clrstk_"))
async def clear_stock(call: CallbackQuery):
    item_id = int(call.data.split("_")[1])
    execute_db('DELETE FROM stock WHERE item_id=? AND is_sold=0', (item_id,))
    await call.answer("✅ បានលុបស្តុកចោលទាំងអស់ជោគជ័យ!", show_alert=True)
    try: await call.message.delete()
    except: pass

@dp.callback_query(F.data.startswith("addstk_"))
async def add_stock_start(call: CallbackQuery, state: FSMContext):
    await state.update_data(item_id=int(call.data.split("_")[1]))
    await call.message.edit_text("📥 សូមផ្ញើ ស្តុកមកទីនេះ (ជា files / វីដេអូ / រូបភាព / លីង / អត្ថបទ):\n*បើអត្ថបទ វាយមួយជួរចុះបន្ទាត់មួយ វាចូល ២ keys*", reply_markup=cancel_inline())
    await state.set_state(AdminAddStock.keys)
    await call.answer()

@dp.message(AdminAddStock.keys)
async def add_stock_save(msg: Message, state: FSMContext, bot: Bot):
    item_id = (await state.get_data())['item_id']
    added = 0
    if msg.photo: 
        execute_db('INSERT INTO stock (item_id, key_data, type) VALUES (?, ?, ?)', (item_id, f"photo:{msg.photo[-1].file_id}", 'file')); added = 1
    elif msg.video: 
        execute_db('INSERT INTO stock (item_id, key_data, type) VALUES (?, ?, ?)', (item_id, f"video:{msg.video.file_id}", 'file')); added = 1
    elif msg.document:
        execute_db('INSERT INTO stock (item_id, key_data, type) VALUES (?, ?, ?)', (item_id, f"document:{msg.document.file_id}", 'file')); added = 1
    elif msg.text:
        lines = [L.strip() for L in msg.text.split('\n') if L.strip()]
        for k in lines: execute_db('INSERT INTO stock (item_id, key_data, type) VALUES (?, ?, ?)', (item_id, k, 'text'))
        added = len(lines)
    else: return await msg.answer("❌ មិនគាំទ្រទម្រង់នេះទេ!", reply_markup=cancel_inline())
    
    await msg.answer(f"✅ បានបញ្ចូលចំនួន {added} ចូលស្តុកជោគជ័យ!")
    await state.clear()
    
    item_info = execute_db('SELECT items.name, categories.name FROM items JOIN categories ON items.cat_id = categories.id WHERE items.id=?', (item_id,), fetch=True)
    item_name = item_info[0] if item_info else "ទំនិញ"
    cat_name = item_info[1] if item_info else "ផលិតផល"
    
    alert = f"""<tg-emoji emoji-id="6269366244462301331">📦</tg-emoji> <b>ស្តុកថ្មីបានមកដល់ហើយ!</b>
━━━━━━━━━━━━━━━━━━━━━
- ទំនិញ៖ <b>{cat_name}</b>
- កញ្ចប់៖ <b>{item_name}</b>
- ចំនួនបន្ថែមថ្មី៖ <b>{added}</b>
━━━━━━━━━━━━━━━━━━━━━
<tg-emoji emoji-id="5904704361182798355">⚡</tg-emoji> <b>រួចរាល់សម្រាប់ទិញឥឡូវនេះ!</b>
👉 ចុចប៊ូតុង <tg-emoji emoji-id="5445146945024720188">🛒</tg-emoji> ខាងក្រោមដើម្បីទិញ ៖"""
    kb = InlineKeyboardMarkup(inline_keyboard=[[IBtn(text="Buy Now / ទិញឥឡូវនេះ", callback_data="buy_now_direct", style="primary", icon_custom_emoji_id="5445146945024720188")]])
    users = execute_db('SELECT id FROM users', fetchall=True)
    for u in users:
        try: await bot.send_message(u[0], alert, reply_markup=kb)
        except: pass

# --- BROADCAST ---
@dp.callback_query(F.data == "adm_broadcast")
async def adm_broadcast(call: CallbackQuery, state: FSMContext):
    try: await call.answer()
    except Exception: pass
    await state.update_data(broadcast_queue=[])
    await state.set_state(AdminBroadcast.msg)
    txt = (
        "📢 <b>Broadcast</b>\n\n"
        "សូមអ្នកវាយសារដែលចង់ធ្ញើទៅ Customer បស់អ្នកមក៖ video / photo / voice / gif / file \n"
        "អតិបរមា 20 \n\n"
        "❌ចុច /cancel ដើម្បីបោះបង់\n"
        "✅ ចុច /done ដើម្បីធ្ញើសារទៅយកមង"
    )
    await call.message.edit_text(txt, reply_markup=cancel_inline())

@dp.message(AdminBroadcast.msg, Command("cancel"))
async def broadcast_cancel_cmd(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("❌ បានបោះបង់ការ Broadcast រួចរាល់!", reply_markup=admin_back_inline("back_admin"))

@dp.message(AdminBroadcast.msg, Command("done"))
async def broadcast_done_cmd(msg: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    queue = data.get("broadcast_queue", [])
    if not queue:
        return await msg.answer("⚠️ មិនទាន់មានសារសម្រាប់ផ្ញើទេ! សូមផ្ញើសារសិន ឬចុច /cancel ដើម្បីបោះបង់។")
    users = execute_db('SELECT id FROM users', fetchall=True) or []
    success, fail = 0, 0
    await msg.answer(f"⏳ កំពុងផ្ញើសារចំនួន {len(queue)} ទៅកាន់ {len(users)} នាក់...")
    for u in users:
        u_ok = False
        for item in queue:
            try:
                t = item["type"]
                if t == "text": await bot.send_message(u[0], item["content"])
                elif t == "photo": await bot.send_photo(u[0], item["file_id"], caption=item.get("caption"))
                elif t == "video": await bot.send_video(u[0], item["file_id"], caption=item.get("caption"))
                elif t == "animation": await bot.send_animation(u[0], item["file_id"], caption=item.get("caption"))
                elif t == "document": await bot.send_document(u[0], item["file_id"], caption=item.get("caption"))
                elif t == "audio": await bot.send_audio(u[0], item["file_id"], caption=item.get("caption"))
                elif t == "voice": await bot.send_voice(u[0], item["file_id"], caption=item.get("caption"))
                u_ok = True
            except Exception:
                pass
        if u_ok: success += 1
        else: fail += 1
        await asyncio.sleep(0.05)

    res_text = f"""<tg-emoji emoji-id="6100288912620528566">📊</tg-emoji> បានធ្ញើចំនួន <b>{success+fail}</b> នាក់ \n- <tg-emoji emoji-id="6102563003314479651">✅</tg-emoji> ជោគជ័យចំនួន <b>{success}</b> នាក់ \n- <tg-emoji emoji-id="6102914615107133393">❌</tg-emoji> បរាជ័យ <b>{fail}</b> នាក់"""
    await msg.answer(res_text, reply_markup=admin_back_inline("back_admin"))
    await state.clear()

@dp.message(AdminBroadcast.msg)
async def queue_broadcast_item(msg: Message, state: FSMContext):
    data = await state.get_data()
    queue = data.get("broadcast_queue", [])
    if len(queue) >= 20:
        return await msg.answer("⚠️ អតិបរមា 20 សារហើយ! សូមចុច /done ដើម្បីផ្ញើចេញ ឬ /cancel ដើម្បីបោះបង់។")
    cap = msg.html_text if (msg.caption or msg.text) else None
    if msg.photo: entry = {"type": "photo", "file_id": msg.photo[-1].file_id, "caption": cap}
    elif msg.video: entry = {"type": "video", "file_id": msg.video.file_id, "caption": cap}
    elif msg.animation: entry = {"type": "animation", "file_id": msg.animation.file_id, "caption": cap}
    elif msg.document: entry = {"type": "document", "file_id": msg.document.file_id, "caption": cap}
    elif msg.audio: entry = {"type": "audio", "file_id": msg.audio.file_id, "caption": cap}
    elif msg.voice: entry = {"type": "voice", "file_id": msg.voice.file_id, "caption": cap}
    elif msg.text: entry = {"type": "text", "content": msg.html_text}
    else: return await msg.answer("❌ មិនគាំទ្រទម្រង់នេះទេ!")
    queue.append(entry)
    await state.update_data(broadcast_queue=queue)
    await msg.answer(f"✅ បានបន្ថែម ({len(queue)}/20)។ ផ្ញើបន្ថែមទៀត ឬចុច /done ដើម្បីផ្ញើ ឬ /cancel ដើម្បីបោះបង់។")

# --- RESELLER & PRICE SETTINGS ---
@dp.callback_query(F.data == "adm_reseller")
async def adm_reseller(call: CallbackQuery):
    try: await call.answer()
    except Exception: pass
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="Abb Reseller", callback_data="add_reseller", style="success"), IBtn(text="Del Reseller", callback_data="del_reseller", style="danger")],
        [IBtn(text="Add Reseller VIP", callback_data="add_reseller_vip", style="success", icon_custom_emoji_id="6314076231243404806"),
         IBtn(text="Del Reseller VIP", callback_data="del_reseller_vip", style="danger", icon_custom_emoji_id="5301240299085906131")],
        [IBtn(text="តម្លៃ ទូទៅ", callback_data="adm_set_price_normal", style="primary"), IBtn(text="តម្លៃ Reseller", callback_data="adm_set_price_reseller", style="primary")],
        [IBtn(text="តម្លៃ Reseller VIP", callback_data="adm_set_price_vip", style="primary", icon_custom_emoji_id="6154233835002271015")],
        [IBtn(text="📋 បញ្ជី Reseller + VIP", callback_data="adm_list_resellers", style="primary", icon_custom_emoji_id="6154222749691679144")],
        [IBtn(text="Abmin ID", callback_data="adm_manage_perms", style="primary")],
        [IBtn(text="Back", callback_data="back_admin", style="danger", icon_custom_emoji_id="6035130900075777681")]
    ])
    await call.message.edit_text("👥 <b>គ្រប់គ្រង Reseller & VIP</b>", reply_markup=kb)
    await call.answer()


# ====================================================================================================
# [ 📋 បញ្ជី RESELLER + VIP ទាំងអស់ & CLEAR DATA ]
# ====================================================================================================

@dp.callback_query(F.data == "adm_list_resellers")
async def adm_list_resellers_handler(call: CallbackQuery):
    try: await call.answer()
    except Exception: pass
    
    vip_users = execute_db("SELECT id, username, first_name FROM users WHERE is_reseller_vip = 1", fetchall=True) or []
    normal_users = execute_db("SELECT id, username, first_name FROM users WHERE is_reseller = 1 AND (is_reseller_vip = 0 OR is_reseller_vip IS NULL)", fetchall=True) or []
    
    vip_lines = []
    if vip_users:
        for u in vip_users:
            uid = u[0]
            uname = f"@{u[1]}" if u[1] else (u[2] or f"User_{uid}")
            res = execute_db("SELECT COUNT(id), COALESCE(SUM(qty), 0), COALESCE(SUM(total_price), 0) FROM orders WHERE user_id=?", (uid,), fetch=True)
            t_orders = res[0] if res else 0
            t_qty = res[1] if res else 0
            t_price = res[2] if res else 0.0
            vip_lines.append(f"• {uname} (ID: <code>{uid}</code>) ➔ យកទំនិញទៅលក់សរុប: {t_qty} ({t_orders} ដង | ${t_price:.2f})")
    else:
        vip_lines.append("• (មិនទាន់មានទិន្នន័យ Reseller VIP ទេ)")
        
    norm_lines = []
    if normal_users:
        for u in normal_users:
            uid = u[0]
            uname = f"@{u[1]}" if u[1] else (u[2] or f"User_{uid}")
            res = execute_db("SELECT COUNT(id), COALESCE(SUM(qty), 0), COALESCE(SUM(total_price), 0) FROM orders WHERE user_id=?", (uid,), fetch=True)
            t_orders = res[0] if res else 0
            t_qty = res[1] if res else 0
            t_price = res[2] if res else 0.0
            norm_lines.append(f"• {uname} (ID: <code>{uid}</code>) ➔ យកទំនិញទៅលក់សរុប: {t_qty} ({t_orders} ដង | ${t_price:.2f})")
    else:
        norm_lines.append("• (មិនទាន់មានទិន្នន័យ Reseller ធម្មតាទេ)")
        
    text = f"""<tg-emoji emoji-id="6154222749691679144">📋</tg-emoji> <b>បញ្ជី Reseller + VIP ទាំងអស់ !</b>
———————————————————————
👱‍♂️ <b>Reseller អ្នកលក់បន្ត VIP៖</b>
{chr(10).join(vip_lines)}
———————————————————————
👤 <b>Reseller ធម្មតាអ្នកលក់បន្ត៖</b>
{chr(10).join(norm_lines)}
———————————————————————
👉 <i>សូមចុចប៊ូតុងខាងក្រោមដើម្បីឃ្លាសារចាស់ៗ!</i>"""

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="🗑 Clear ទិន្នន័យ Reseller VIP", callback_data="clear_reseller_vip", style="danger", icon_custom_emoji_id="6176808917549453468")],
        [IBtn(text="🗑 Clear ទិន្នន័យ Reseller ធម្មតា", callback_data="clear_reseller_normal", style="danger", icon_custom_emoji_id="6176808917549453468")],
        [IBtn(text="ត្រលប់", callback_data="adm_reseller", style="danger", icon_custom_emoji_id="5253997076169115797")]
    ])
    rendered = render_clean_text(text)
    try:
        await call.message.edit_text(rendered, reply_markup=kb)
    except Exception:
        try:
            await call.message.answer(rendered, reply_markup=kb)
        except Exception:
            plain = re.sub(r'<[^>]+>', '', rendered)
            await call.message.answer(plain, reply_markup=kb, parse_mode=None)

@dp.callback_query(F.data == "clear_reseller_vip")
async def clear_reseller_vip_handler(call: CallbackQuery):
    execute_db("UPDATE users SET is_reseller_vip = 0 WHERE is_reseller_vip = 1")
    await call.answer("✅ បាន Clear ទិន្នន័យ Reseller VIP រួចរាល់!", show_alert=True)
    await adm_list_resellers_handler(call)

@dp.callback_query(F.data == "clear_reseller_normal")
async def clear_reseller_normal_handler(call: CallbackQuery):
    execute_db("UPDATE users SET is_reseller = 0 WHERE is_reseller = 1 AND (is_reseller_vip = 0 OR is_reseller_vip IS NULL)")
    await call.answer("✅ បាន Clear ទិន្នន័យ Reseller ធម្មតា រួចរាល់!", show_alert=True)
    await adm_list_resellers_handler(call)

@dp.callback_query(F.data == "add_reseller_vip")
async def add_reseller_vip_st(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("👑 <b>បញ្ចូល ID របស់ User ដែលចង់ដាក់ជា Reseller VIP៖</b>", reply_markup=cancel_inline())
    await state.set_state(AdminReseller.add_vip_id)
    await call.answer()

@dp.message(AdminReseller.add_vip_id)
async def add_reseller_vip_save(msg: Message, state: FSMContext):
    try:
        uid = int(msg.text.strip())
        execute_db('INSERT OR IGNORE INTO users (id, is_reseller, is_reseller_vip) VALUES (?, 1, 1)', (uid,))
        execute_db('UPDATE users SET is_reseller=1, is_reseller_vip=1 WHERE id=?', (uid,))
        await msg.answer("✅ <b>បានបន្ថែម Reseller VIP ជោគជ័យ!</b>\nឥឡូវនេះ User នេះនឹងមើលឃើញ និងទិញក្នុងតម្លៃ Reseller VIP។", reply_markup=admin_back_inline("adm_reseller"))
    except:
        await msg.answer("❌ ID មិនត្រឹមត្រូវ! សូមផ្ញើជាលេខ Telegram ID។", reply_markup=cancel_inline())
        return
    await state.clear()

@dp.callback_query(F.data == "del_reseller_vip")
async def del_reseller_vip_st(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("❌ <b>បញ្ចូល ID របស់ User ដែលចង់ដកពី Reseller VIP៖</b>", reply_markup=cancel_inline())
    await state.set_state(AdminReseller.del_vip_id)
    await call.answer()

@dp.message(AdminReseller.del_vip_id)
async def del_reseller_vip_save(msg: Message, state: FSMContext):
    try:
        uid = int(msg.text.strip())
        execute_db('UPDATE users SET is_reseller=0, is_reseller_vip=0 WHERE id=?', (uid,))
        await msg.answer("✅ <b>បានដកពី Reseller VIP ជោគជ័យ!</b>\nUser នេះនឹងត្រឡប់ទៅមើលឃើញតម្លៃទូទៅធម្មតាវិញ។", reply_markup=admin_back_inline("adm_reseller"))
    except:
        await msg.answer("❌ ID មិនត្រឹមត្រូវ! សូមផ្ញើជាលេខ Telegram ID។", reply_markup=cancel_inline())
        return
    await state.clear()

@dp.callback_query(F.data == "adm_set_price_normal")
async def set_price_normal(call: CallbackQuery):
    items = execute_db('SELECT items.id, items.name, items.price, categories.name, items.icon FROM items JOIN categories ON items.cat_id = categories.id ORDER BY categories.id, items.id', fetchall=True)
    kb = [[IBtn(text=f"{i[3]} - {i[1]} (${float(i[2] or 0):.2f})", callback_data=f"setpn_{i[0]}", style="primary", icon_custom_emoji_id=i[4])] for i in items]
    kb.append([IBtn(text="Back", callback_data="adm_reseller", style="danger", icon_custom_emoji_id="6035130900075777681")])
    await call.message.edit_text("ជ្រើសរើសទំនិញដើម្បីកែប្រែ តម្លៃទូទៅ:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data == "adm_set_price_reseller")
async def set_price_reseller(call: CallbackQuery):
    items = execute_db('SELECT items.id, items.name, items.reseller_price, categories.name, items.icon FROM items JOIN categories ON items.cat_id = categories.id ORDER BY categories.id, items.id', fetchall=True)
    kb = [[IBtn(text=f"{i[3]} - {i[1]} (${float(i[2] or 0):.2f})", callback_data=f"setpr_{i[0]}", style="primary", icon_custom_emoji_id=i[4])] for i in items]
    kb.append([IBtn(text="Back", callback_data="adm_reseller", style="danger", icon_custom_emoji_id="6035130900075777681")])
    await call.message.edit_text("ជ្រើសរើសទំនិញដើម្បីកែប្រែ តម្លៃ Reseller:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data == "adm_set_price_vip")
async def set_price_vip(call: CallbackQuery):
    items = execute_db('SELECT items.id, items.name, items.reseller_vip_price, categories.name, items.icon FROM items JOIN categories ON items.cat_id = categories.id ORDER BY categories.id, items.id', fetchall=True)
    kb = [[IBtn(text=f"{i[3]} - {i[1]} (${float(i[2] or 0):.2f})", callback_data=f"setpv_{i[0]}", style="primary", icon_custom_emoji_id=i[4])] for i in items]
    kb.append([IBtn(text="Back", callback_data="adm_reseller", style="danger", icon_custom_emoji_id="6035130900075777681")])
    await call.message.edit_text("👑 <b>ជ្រើសរើសទំនិញដើម្បីកែប្រែ តម្លៃ Reseller VIP:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data.startswith("setpn_") | F.data.startswith("setpr_") | F.data.startswith("setpv_"))
async def ask_new_price(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    item_id = int(parts[1])
    if parts[0] == "setpn": p_type = "normal"
    elif parts[0] == "setpr": p_type = "reseller"
    else: p_type = "vip"
    await state.update_data(edit_item_id=item_id, edit_price_type=p_type)
    await call.message.edit_text(f"វាយបញ្ចូលតម្លៃថ្មី (ជាលេខ USD):", reply_markup=cancel_inline())
    await state.set_state(AdminEditPrice.new_price)
    await call.answer()

@dp.message(AdminEditPrice.new_price)
async def save_new_price(msg: Message, state: FSMContext, bot: Bot):
    try:
        price = float(msg.text)
        data = await state.get_data()
        item_id, p_type = data['edit_item_id'], data['edit_price_type']
        
        old_item = execute_db('SELECT name, price, reseller_price, cat_id, reseller_vip_price FROM items WHERE id=?', (item_id,), fetch=True)
        if p_type == "normal":
            old_price = old_item[1]
            execute_db('UPDATE items SET price=? WHERE id=?', (price, item_id))
        elif p_type == "reseller":
            old_price = old_item[2]
            execute_db('UPDATE items SET reseller_price=? WHERE id=?', (price, item_id))
        else: # vip
            old_price = old_item[4] if (len(old_item) > 4 and old_item[4]) else 0.0
            execute_db('UPDATE items SET reseller_vip_price=? WHERE id=?', (price, item_id))
            
        cat_name = execute_db('SELECT name FROM categories WHERE id=?', (old_item[3],), fetch=True)[0]
        stock_count = execute_db('SELECT COUNT(*) FROM stock WHERE item_id=? AND is_sold=0', (item_id,), fetch=True)[0]

        await msg.answer("✅ កែប្រែតម្លៃជោគជ័យ និងបានជូនដំណឹងដល់ User រួចរាល់!", reply_markup=admin_back_inline("adm_reseller"))
        await state.clear()
        
        tag_str = " (VIP)" if p_type == "vip" else (" (Reseller)" if p_type == "reseller" else "")
        alert = f"""<tg-emoji emoji-id=\"6269366244462301331\">📦</tg-emoji> <b>ទំនិញបានបញ្ចុះតម្លៃហើយ{tag_str} !</b>
━━━━━━━━━━━━━━━━━━━━
- ផលលិតផល : <b>{cat_name}</b>
- កញ្ចប់ : <b>{old_item[0]}</b>
- តម្លៃចាស់ : <b>${old_price:.2f}</b>
- តម្លៃថ្មី : <b>${price:.2f}</b>
- ស្តុកនៅសល់ : <b>{stock_count}</b>
━━━━━━━━━━━━━━━━━━━━
<tg-emoji emoji-id=\"5832229652805985405\">🔥</tg-emoji> រួសរាន់ឡើងទាន់តម្លៃនៅធូថ្លៃ
<tg-emoji emoji-id=\"6071226041454564573\">👉</tg-emoji>សូមបងចុចបូតុង <tg-emoji emoji-id=\"5312361253610475399\">🛒</tg-emoji> <b>BUY NOW</b> ដើម្បីទិញ <tg-emoji emoji-id=\"5231102735817918643\">✨</tg-emoji>"""

        kb = InlineKeyboardMarkup(inline_keyboard=[[IBtn(text="Buy Now / ទិញឥឡូវនេះ", callback_data="buy_now_direct", style="primary", icon_custom_emoji_id="5445146945024720188")]])
        users = execute_db('SELECT id, is_reseller, is_reseller_vip FROM users', fetchall=True)
        for u in users:
            if p_type == "vip" and (len(u) < 3 or u[2] != 1): continue
            elif p_type == "reseller" and u[1] == 0: continue 
            try: await bot.send_message(u[0], alert, reply_markup=kb)
            except: pass
            await asyncio.sleep(0.05)
    except: await msg.answer("❌ សូមវាយជាលេខត្រឹមត្រូវ!", reply_markup=cancel_inline())

@dp.callback_query(F.data == "add_reseller")
async def add_reseller_st(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("បញ្ចូល ID របស់ User ដែលចង់ដាក់ជា Reseller:", reply_markup=cancel_inline())
    await state.set_state(AdminReseller.add_id)
    await call.answer()

@dp.message(AdminReseller.add_id)
async def add_reseller_save(msg: Message, state: FSMContext):
    try:
        uid = int(msg.text)
        execute_db('INSERT OR IGNORE INTO users (id, is_reseller) VALUES (?, 1)', (uid,))
        execute_db('UPDATE users SET is_reseller=1 WHERE id=?', (uid,))
        await msg.answer("✅ ជោគជ័យ!")
    except: pass
    await state.clear()

@dp.callback_query(F.data == "del_reseller")
async def del_reseller_st(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("បញ្ចូល ID របស់ User ដែលចង់ដកពី Reseller:", reply_markup=cancel_inline())
    await state.set_state(AdminReseller.del_id)
    await call.answer()

@dp.message(AdminReseller.del_id)
async def del_reseller_save(msg: Message, state: FSMContext):
    try:
        execute_db('UPDATE users SET is_reseller=0 WHERE id=?', (int(msg.text),))
        await msg.answer("✅ ជោគជ័យ!")
    except: pass
    await state.clear()

# --- ADMIN PERMISSIONS ---
@dp.callback_query(F.data == "adm_manage_perms")
async def adm_manage_perms_handler(call: CallbackQuery):
    owner_id = get_current_owner()
    admins = execute_db('SELECT id, first_name FROM users WHERE is_admin=1 AND (id == ? OR is_admin=1)', (owner_id,), fetchall=True)
    text = "👑 <b>បញ្ជី ADMIN IDs បច្ចុប្បន្ន ៖</b>\n"
    for i, a in enumerate(admins, 1): text += f"{i}. <code>{a[0]}</code> | {a[1] or 'Unknown'}\n"
    text += "\n👉 <i>លោកអ្នកអាចបន្ថែម ID ថ្មី ឬលុប ID ចាស់បាន៖</i>"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn("បន្ថែម Admin ថ្មី", "add_admin_perm", style="success", icon_custom_emoji_id="6033108709213736873")],
        [IBtn("លុប Admin ID", "del_admin_perm", style="danger", icon_custom_emoji_id="5891207662678317861")],
        [IBtn("Back", "adm_reseller", style="danger", icon_custom_emoji_id="6035130900075777681")]
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data == "add_admin_perm")
async def add_admin_perm_handler(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("➕ សូមផ្ញើ Telegram User ID របស់ Admin ថ្មី៖", reply_markup=cancel_inline())
    await state.set_state(AdminReseller.add_admin)
    await call.answer()

@dp.message(AdminReseller.add_admin)
async def process_add_admin(msg: Message, state: FSMContext):
    try:
        uid = int(msg.text)
        execute_db('INSERT OR IGNORE INTO users (id, is_admin) VALUES (?, 1)', (uid,))
        execute_db('UPDATE users SET is_admin=1 WHERE id=?', (uid,))
        await msg.answer("✅ បានបន្ថែម Admin ជោគជ័យ!")
    except: pass
    await state.clear()

@dp.callback_query(F.data == "del_admin_perm")
async def del_admin_perm_handler(call: CallbackQuery):
    owner_id = get_current_owner()
    admins = execute_db('SELECT id, first_name FROM users WHERE is_admin=1 AND id != ?', (owner_id,), fetchall=True)
    kb = [[IBtn(text=f"ដក {a[1] or str(a[0])} ({a[0]})", callback_data=f"deladm_{a[0]}", style="danger")] for a in admins]
    kb.append([IBtn(text="Back", callback_data="adm_manage_perms", style="primary", icon_custom_emoji_id="6035130900075777681")])
    await call.message.edit_text("ជ្រើសរើស Admin ដើម្បីដកសិទ្ធិ:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data.startswith("deladm_"))
async def process_del_admin(call: CallbackQuery):
    uid = int(call.data.split("_")[1])
    execute_db('UPDATE users SET is_admin=0 WHERE id=?', (uid,))
    await call.answer("✅ បានលុបសិទ្ធិ Admin ជោគជ័យ!", show_alert=True)
    await del_admin_perm_handler(call)

# --- SET CHANNEL ---
@dp.callback_query(F.data == "adm_channel")
async def adm_channel(call: CallbackQuery, state: FSMContext):
    try: await call.answer()
    except Exception: pass
    await call.message.edit_text("🔔 សូមវាយបញ្ចូល Channel/Group ID របស់អ្នក:", reply_markup=cancel_inline())
    await state.set_state(AdminChannel.channel_id)
    await call.answer()

@dp.message(AdminChannel.channel_id)
async def save_channel(msg: Message, state: FSMContext):
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('channel_id', msg.text))
    await msg.answer("✅ កំណត់ជោគជ័យ!")
    await state.clear()

# --- START MEDIA ---
@dp.callback_query(F.data == "adm_start_media")
async def adm_start_media(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("ផ្ញើ វីដេអូ ឬ រូបភាព សម្រាប់ /start (ឬវាយពាក្យ 'del' ដើម្បីលុប):", reply_markup=cancel_inline())
    await state.set_state(AdminStartMedia.media)
    await call.answer()

@dp.message(AdminStartMedia.media)
async def save_start_media(msg: Message, state: FSMContext):
    if msg.text and msg.text.lower() == 'del': execute_db('DELETE FROM settings WHERE key=?', ('start_media',))
    elif msg.photo: execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('start_media', f"photo:{msg.photo[-1].file_id}"))
    elif msg.video: execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('start_media', f"video:{msg.video.file_id}"))
    await msg.answer("✅ កំណត់ជោគជ័យ!")
    await state.clear()

@dp.callback_query(F.data == "cancel_action")
async def cancel_action_handler(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try: await call.message.edit_text("❌ បានបោះបង់ការប្រតិបត្តិការរូចរាល់!")
    except:
        try: await call.message.delete()
        except: pass
    await call.answer("❌ បានបោះបង់", show_alert=True)

# ====================================================================================================
# [ MAIN LOOP ]
# ====================================================================================================



# ====================================================================================================
# [ 🎛 ប៊ូតុង ORGANIZER & CUSTOMIZER ENGINE ]
# ====================================================================================================

def move_org_btn(rows, key, action):
    r_idx, c_idx = -1, -1
    for r, row in enumerate(rows):
        if key in row:
            r_idx, c_idx = r, row.index(key)
            break
    if r_idx == -1: return rows

    if action == 'up':
        if r_idx > 0:
            if len(rows[r_idx]) == 1 and len(rows[r_idx - 1]) == 1:
                rows[r_idx], rows[r_idx - 1] = rows[r_idx - 1], rows[r_idx]
            else:
                rows[r_idx].pop(c_idx)
                rows[r_idx - 1].append(key)
                if not rows[r_idx]: rows.pop(r_idx)
    elif action == 'down':
        if r_idx < len(rows) - 1:
            if len(rows[r_idx]) == 1 and len(rows[r_idx + 1]) == 1:
                rows[r_idx], rows[r_idx + 1] = rows[r_idx + 1], rows[r_idx]
            else:
                rows[r_idx].pop(c_idx)
                rows[r_idx + 1].insert(0, key)
                if not rows[r_idx]: rows.pop(r_idx)
    elif action == 'left':
        if c_idx > 0:
            rows[r_idx][c_idx], rows[r_idx][c_idx - 1] = rows[r_idx][c_idx - 1], rows[r_idx][c_idx]
        elif r_idx > 0:
            rows[r_idx].pop(c_idx)
            rows[r_idx - 1].append(key)
            if not rows[r_idx]: rows.pop(r_idx)
    elif action == 'right':
        if c_idx < len(rows[r_idx]) - 1:
            rows[r_idx][c_idx], rows[r_idx][c_idx + 1] = rows[r_idx][c_idx + 1], rows[r_idx][c_idx]
        elif len(rows[r_idx]) > 1:
            rows[r_idx].pop(c_idx)
            rows.insert(r_idx + 1, [key])
    return rows

def get_org_group_info(group_key):
    if group_key == "admin":
        items_dict = {
            "manage_products": {"name": "គ្រុបគ្រងផលលិតផល", "default_style": "primary"},
            "stock_hub": {"name": "គ្រុបគ្រង (add stock / views Stock )", "default_style": "success"},
            "broadcast": {"name": "Broadcast", "default_style": "primary"},
            "reseller": {"name": "គ្រប់គ្រង់ Reseller", "default_style": "primary"},
            "settings": {"name": "Setting", "default_style": "primary"},
            "content_setting": {"name": "Bot Content", "default_style": "primary"},
            "channel": {"name": "កំណត់ Channel", "default_style": "primary"},
            "start_media": {"name": "ដាក់មេឌៀ /start", "default_style": "primary"},
            "del_start_media": {"name": "ដកមេឌៀ /start", "default_style": "danger"},
            "setup_emoji": {"name": "Setup Emoji", "default_style": "primary"}
        }
        title = "រៀបបូតុង Admin ទាំងអស់"
        back_cb = "adm_btn_organizer"
    elif group_key == "cats":
        cats = execute_db('SELECT id, name FROM categories', fetchall=True)
        items_dict = {str(c[0]): {"name": c[1], "default_style": "primary"} for c in cats}
        title = "រៀបបូតុង ផលលិតផល"
        back_cb = "adm_btn_organizer"
    elif group_key.startswith("items_"):
        cat_id = int(group_key.split("_")[1])
        cat = execute_db('SELECT name FROM categories WHERE id=?', (cat_id,), fetch=True)
        c_title = cat[0] if cat else ""
        items = execute_db('SELECT id, name FROM items WHERE cat_id=?', (cat_id,), fetchall=True)
        items_dict = {str(i[0]): {"name": i[1], "default_style": "primary"} for i in items}
        title = f"រៀបបូតុង ទំនិញ ({c_title})"
        back_cb = "org_group_items"
    elif group_key == "start_menu":
        items_dict = {
            "buynow": {"name": "Buy Now / ទិញឥឡូវនេះ", "default_style": "success"},
            "topup": {"name": "Top Up / បព្ចូាលទឹកប្រាក់", "default_style": "primary"},
            "myorders": {"name": "My Orders / ការបព្ជាទិញរបស់ខ្ញុំ", "default_style": "primary"},
            "balance": {"name": "Balance / តុល្យភាព", "default_style": "primary"},
            "contact": {"name": "Contact Admin / ទាក់ទងអ្នកគ្រប់គ្រង", "default_style": "success"},
        }
        title = "រៀបបូតុង ម៉ឺនុយ /start"
        back_cb = "adm_btn_organizer"
    elif group_key == "pay":
        items_dict = {
            "cqty": {"name": "បញ្ចូលចំនួនខ្លួនឯង", "default_style": "primary"},
            "paybal": {"name": "Pay Balance", "default_style": "success"},
            "abapay": {"name": "Pay With ABA", "default_style": "success"},
            "bakongpay": {"name": "Pay With Bakong", "default_style": "success"},
            "khqr": {"name": "KHQR", "default_style": "primary"},
            "back": {"name": "Back", "default_style": "danger"}
        }
        title = "រៀបបូតុង កន្លែងរើសវិធីបង់ប្រាក់"
        back_cb = "adm_btn_organizer"
    else:
        items_dict, title, back_cb = {}, "រៀបចំបូតុង", "adm_btn_organizer"
    return items_dict, title, back_cb

async def render_org_editor(call: CallbackQuery, group_key: str):
    items_dict, title, back_cb = get_org_group_info(group_key)
    if not items_dict:
        await call.answer("❌ មិនមានទិន្នន័យបូតុងនៅក្នុងផ្នែកនេះទេ!", show_alert=True)
        return

    raw_l = get_setting(f"org_layout_{group_key}")
    raw_s = get_setting(f"org_styles_{group_key}")
    
    if raw_l:
        try: layout = json.loads(raw_l)
        except: layout = [[k] for k in items_dict.keys()]
    else:
        layout = [[k] for k in items_dict.keys()]

    if raw_s:
        try: styles = json.loads(raw_s)
        except: styles = {k: items_dict[k]["default_style"] for k in items_dict}
    else:
        styles = {k: items_dict[k]["default_style"] for k in items_dict}

    # Ensure all current keys are included in layout
    existing = set(k for row in layout for k in row)
    for k in items_dict:
        if k not in existing:
            layout.append([k])
        if k not in styles:
            styles[k] = items_dict[k]["default_style"]

    # Build Preview
    preview_rows = []
    for r_idx, row in enumerate(layout):
        row_tags = []
        for k in row:
            if k in items_dict:
                st = styles.get(k, "primary")
                dot = "🔵" if st == "primary" else ("🟢" if st == "success" else "🔴")
                row_tags.append(f"{dot} [{items_dict[k]['name'][:12]}]")
        if row_tags:
            preview_rows.append("  " + " | ".join(row_tags))
    preview_str = "\n".join(preview_rows) if preview_rows else "<i>(គ្មានបូតុង)</i>"

    text = f"""<tg-emoji emoji-id="5335054400513649848">🎛</tg-emoji> <b>ផ្ទាំង{title}</b>
━━━━━━━━━━━━━━━━━━━━━
• <b>ខាងស្តាំ</b> : ចុចលើឈ្មោះបូតុងដើម្បីប្តូរពណ៌ (Primary 🔵 | Success 🟢 | Danger 🔴)
• <b>⬆️ ⬇️</b> : រំកិលបូតុងឡើងលើ / ចុះក្រោម
• <b>⬅️ ➡️</b> : រំកិលបូតុងទៅកៀន / ផ្តេកទទឹង / ចុះជួរ
• <b>រៀបបូតុងបញ្ឈរទាំងអស់</b> : រៀបជាជួរឈរ ១ ជួរ ១ បូតុង
━━━━━━━━━━━━━━━━━━━━━
👀 <b>ទម្រង់បច្ចុប្បន្ន (Layout Preview):</b>
<blockquote>{preview_str}</blockquote>"""

    kb_rows = []
    for row in layout:
        for k in row:
            if k not in items_dict: continue
            st = styles.get(k, "primary")
            b_label = items_dict[k]["name"][:10]
            kb_rows.append([
                IBtn(text="⬆️", callback_data=f"ob_mv_{group_key}_{k}_up", style="primary"),
                IBtn(text="⬇️", callback_data=f"ob_mv_{group_key}_{k}_down", style="primary"),
                IBtn(text="⬅️", callback_data=f"ob_mv_{group_key}_{k}_left", style="primary"),
                IBtn(text="➡️", callback_data=f"ob_mv_{group_key}_{k}_right", style="primary"),
                IBtn(text=b_label, callback_data=f"ob_st_{group_key}_{k}", style=st)
            ])

    kb_rows.append([IBtn(text="រៀបបូតុងបព្ឈទាំងអស់", callback_data=f"ob_vert_{group_key}", style="primary", icon_custom_emoji_id="5307739641166700726")])
    kb_rows.append([IBtn(text="Back", callback_data=back_cb, style="danger", icon_custom_emoji_id="6035130900075777681")])

    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
    await call.answer()

@dp.callback_query(F.data == "adm_btn_organizer")
async def adm_btn_organizer_menu(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [IBtn(text="រៀបបូតុង Admin ទាំងអស់", callback_data="org_group_admin", style="primary", icon_custom_emoji_id="5895592588064328942")],
        [IBtn(text="រៀបបូតុង ម៉ឺនុយ /start", callback_data="org_group_start_menu", style="primary", icon_custom_emoji_id="5335054400513649848")],
        [IBtn(text="រៀបបូតុង ផលលិតផល", callback_data="org_group_cats", style="primary", icon_custom_emoji_id="5352896944496728039")],
        [IBtn(text="រៀបបូតុង ទំនិញ", callback_data="org_group_items", style="primary", icon_custom_emoji_id="5884479287171485878")],
        [IBtn(text="រៀបបូតុង កន្លែងរើសវិធីបង់ប្រាក់", callback_data="org_group_pay", style="primary", icon_custom_emoji_id="5472238215748397135")],
        [IBtn(text="Back", callback_data="adm_settings", style="danger", icon_custom_emoji_id="6035130900075777681")]
    ])
    text = """<tg-emoji emoji-id="5335054400513649848">🎛</tg-emoji> <b>ផ្ទាំងរៀបចំបូតុង និងពណ៌ (Button Organizer)</b>
━━━━━━━━━━━━━━━━━━━━━
សូមជ្រើសរើសផ្នែកដែលអ្នកចង់រៀបចំបូតុង៖"""
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data == "org_group_admin")
async def org_group_admin_handler(call: CallbackQuery):
    await render_org_editor(call, "admin")

@dp.callback_query(F.data == "org_group_start_menu")
async def org_group_start_menu_handler(call: CallbackQuery):
    await render_org_editor(call, "start_menu")

@dp.callback_query(F.data == "org_group_cats")
async def org_group_cats_handler(call: CallbackQuery):
    await render_org_editor(call, "cats")

@dp.callback_query(F.data == "org_group_items")
async def org_group_items_pick_cat(call: CallbackQuery):
    cats = execute_db('SELECT id, name FROM categories', fetchall=True)
    if not cats:
        return await call.answer("❌ មិនទាន់មានផលិតផល (Category) នៅឡើយទេ!", show_alert=True)
    kb = [[IBtn(text=c[1], callback_data=f"org_pickcat_items_{c[0]}", style="primary")] for c in cats]
    kb.append([IBtn(text="Back", callback_data="adm_btn_organizer", style="danger", icon_custom_emoji_id="6035130900075777681")])
    await call.message.edit_text("📂 <b>ជ្រើសរើស ផលិតផល ដើម្បីរៀបចំបូតុងទំនិញខាងក្នុង៖</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data.startswith("org_pickcat_items_"))
async def org_pickcat_items_handler(call: CallbackQuery):
    cat_id = call.data.split("_")[3]
    await render_org_editor(call, f"items_{cat_id}")

@dp.callback_query(F.data == "org_group_pay")
async def org_group_pay_handler(call: CallbackQuery):
    await render_org_editor(call, "pay")

@dp.callback_query(F.data.startswith("ob_mv_"))
async def org_move_btn_handler(call: CallbackQuery):
    parts = call.data.split("_")
    # format: ob_mv_{group_key}_{k}_{action}
    # group_key can be admin, cats, pay, or items_{cat_id}
    action = parts[-1]
    if parts[2] == "items":
        group_key = f"items_{parts[3]}"
        key = parts[4]
    elif parts[2] == "start" and parts[3] == "menu":
        group_key = "start_menu"
        key = parts[4]
    else:
        group_key = parts[2]
        key = parts[3]

    items_dict, _, _ = get_org_group_info(group_key)
    raw_l = get_setting(f"org_layout_{group_key}")
    if raw_l:
        try: layout = json.loads(raw_l)
        except: layout = [[k] for k in items_dict.keys()]
    else:
        layout = [[k] for k in items_dict.keys()]

    layout = move_org_btn(layout, key, action)
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (f"org_layout_{group_key}", json.dumps(layout, ensure_ascii=False)))
    await render_org_editor(call, group_key)

@dp.callback_query(F.data.startswith("ob_st_"))
async def org_style_btn_handler(call: CallbackQuery):
    parts = call.data.split("_")
    if parts[2] == "items":
        group_key = f"items_{parts[3]}"
        key = parts[4]
    elif parts[2] == "start" and parts[3] == "menu":
        group_key = "start_menu"
        key = parts[4]
    else:
        group_key = parts[2]
        key = parts[3]

    items_dict, _, _ = get_org_group_info(group_key)
    raw_s = get_setting(f"org_styles_{group_key}")
    if raw_s:
        try: styles = json.loads(raw_s)
        except: styles = {k: items_dict[k]["default_style"] for k in items_dict}
    else:
        styles = {k: items_dict[k]["default_style"] for k in items_dict}

    curr = styles.get(key, "primary")
    next_st = "success" if curr == "primary" else ("danger" if curr == "success" else "primary")
    styles[key] = next_st
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (f"org_styles_{group_key}", json.dumps(styles, ensure_ascii=False)))
    await render_org_editor(call, group_key)

@dp.callback_query(F.data.startswith("ob_vert_"))
async def org_vert_btn_handler(call: CallbackQuery):
    group_key = call.data.replace("ob_vert_", "")
    items_dict, _, _ = get_org_group_info(group_key)
    raw_l = get_setting(f"org_layout_{group_key}")
    if raw_l:
        try: old_layout = json.loads(raw_l)
        except: old_layout = [[k] for k in items_dict.keys()]
    else:
        old_layout = [[k] for k in items_dict.keys()]

    # Make every button vertical (1 button per row)
    flat = [k for row in old_layout for k in row if k in items_dict]
    for k in items_dict:
        if k not in flat: flat.append(k)
    new_layout = [[k] for k in flat]
    execute_db('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (f"org_layout_{group_key}", json.dumps(new_layout, ensure_ascii=False)))
    await call.answer("✅ បានរៀបបូតុងជាជួរឈរ (Vertical) ទាំងអស់!", show_alert=True)
    await render_org_editor(call, group_key)

async def main():
    logger.info("🚀 VBENSTORE BOT IS RUNNING...")
    await bot.set_my_commands([
        BotCommand(command="start", description="ចាប់ផ្ដើមបត"),
        BotCommand(command="shop", description="🛍 ទិញទំនិញ / Buy Store"),
    ])
    active_bots = execute_db('SELECT id, token FROM cloned_bots WHERE is_active=1', fetchall=True, db_path='vbenstore.db')
    if active_bots:
        for b in active_bots: await start_cloned_bot(b[1], b[0])
    await dp.start_polling(bot)



if __name__ == "__main__":
    asyncio.run(main())
