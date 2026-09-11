#!/usr/bin/env python3
"""
WP / Telegram Number Seller Bot — v9.16 (super instant OTP + SMS link on receipt)
======================================================

WHAT'S NEW IN v9.16
------------------------------------------------------------
1. SUPER INSTANT OTP \u2014 Get OTP now does a LIVE BURST: the
   provider is checked the moment you tap and retried every
   1.5s for ~13s on one shared connection, so the code lands
   the second it's posted (no more one-shot slow checks).
2. FASTER BACKGROUND POLLER \u2014 right after purchase the bot
   checks every 2s for the first 2 minutes (when OTPs almost
   always arrive), then every 5s for the full 10 minutes.
   HTTP timeouts cut to 6s so a slow server never stalls it.
3. OTP LINK WITH THE NUMBER \u2014 the receipt now ships the
   number's SMS-inbox link: an \U0001F517 Open SMS Inbox button
   (tap to see the inbox yourself) AND a clickable link line in
   the receipt text.
4. Search OTP answers twice as fast (6s probe timeout).

WHAT'S NEW IN v9.15
------------------------------------------------------------
1. ADMIN MANAGEMENT \u2014 Admin Panel > Admins:
   add / remove admins by Telegram ID (DB-backed, live reload).
   The super admin can never be removed.
2. NO-OTP NUMBER EXPORTS (admin .txt files):
   - No-OTP Numbers (.txt) \u2014 every sold number in the whole bot
     that never received its OTP (phone | type | user | url).
   - User OTP Report (.txt) \u2014 per-user breakdown: TG username,
     user ID and every number without OTP.
3. INSTANT DEPOSIT FLOW \u2014 Deposit > pick method > payment
   details > user pays > sends ONLY the screenshot (no amount
   picking). Every admin gets the SS with Approve/Reject; on
   approve the admin types the real amount, then the screenshot
   messages are DELETED from the user chat + all admin chats and
   archived to the deposit group.
4. Screenshot storage: deposits.admin_msg_ids tracks every admin
   copy so all of them can be cleaned up.

WHAT'S NEW IN v9.14
------------------------------------------------------------
1. SEARCH OTP — user taps Search OTP, sends his purchased number,
   bot instantly checks: OTP received (shows the code) or not yet.
2. USDT CRYPTO DEPOSITS REMOVED (TXID/on-chain verify deleted).
   Manual payments only: bKash / Nagad / Binance Pay.
   User pays -> sends screenshot -> forwarded to ADMIN with
   Approve/Reject -> admin approves and TYPES the real amount ->
   user wallet credited -> screenshot deleted from the user chat
   and archived to the deposit group.
3. ADMIN OTP STATS — per-user OTP history (received / not received,
   every number listed with its code), searchable by Telegram ID.

WHAT'S NEW IN v9.13 (message redesign: theme + UX)
------------------------------------------------------------
1. NEW DESIGN SYSTEM ON EVERY USER MESSAGE
   - light thin divider, emoji-anchored Title Case titles
   - status emoji glossary: success/failed/pending/locked/replay/
     info/warning always mean the same thing
   - every card ends with a small 'next step' line
   - typos fixed: OTP Received, Your Number
2. ALL USER-SIDE CARDS REDESIGNED (GLB/BUY/OTP/RFD/DEP/PRF + toasts)
   - buttons, callbacks, labels: UNTOUCHED
   - admin screens / group posts: UNTOUCHED

WHAT'S NEW IN v9.12 (wallet rotation + traceability)
------------------------------------------------------------
1. ALL WALLETS ROTATED (old addresses retired everywhere)
   - BEP-20 (BSC)  / Polygon : 0x72b0f558a37ec844b4116574E6ee43B8
   - TRC-20 (Tron)           : TKBP3jP6AFvuumbDEkKKVM4ZFdP1SLN
   - On boot, init_db swaps any leftover OLD wallet still stored
     in a database for the matching NEW wallet automatically -
     a retired address can never stay live.
2. FULL DEPOSIT TRACE (audit trail)
   - New deposit_trace table records EVERY event: order created,
     bad TXID format, declined (pending/failed/wrong token/
     wrong recipient), TXID replay, amount mismatch, credited,
     order locked, wallet changed/rotated - with time, order id,
     user id, network, TXID and reason.
   - Admin command: /trace (last 25) or /trace DEPXXXXXXXX.
   - Every order BINDS the exact wallet it was shown, so a later
     wallet rotation never breaks pending orders; the admin group
     post now shows Order + Wallet + Network + TXID + scan link.
3. Admin SET WALLET screen now lists all three network wallets.

WHAT'S NEW IN v9.11 (clean deposit UI)
------------------------------------------------------------
1. DEAD BUTTONS REMOVED (user report)
   - Custom-amount screen: I PAID removed (the user only types
     the amount there) - it now has just Cancel Deposit.
   - TXID screen: I PAID removed (the TXID itself is the only
     thing needed) - it now has just Cancel Deposit.
   - Redundant "Main Menu" buttons removed from every deposit
     screen - Cancel / Back handle navigation.
2. CANCEL = BACK TO MAIN MENU
   - Cancel Deposit closes the order AND lands the user
     straight on the main menu.
3. CLEANER TEXTS
   - Deposit screens rewritten short and scannable: SEND $X
     card, tap-to-copy address, clearer TXID prompt, plain
     DEPOSIT CONFIRMED receipt (fancy unicode fonts dropped -
     they render as empty boxes on some phones).

WHAT'S NEW IN v9.10.1 (TXID-ONLY verification - no auto-credit)
------------------------------------------------------------
1. POLLER AUTO-CREDIT DELETED
   - The 45s BSC sweep that credited pending deposits by amount
     matching is fully removed. With 200 users paying at once,
     equal amounts ($0.50, $1.00 ...) can be bound safely to
     nobody by an amount alone - so the bot no longer guesses.
2. VERIFICATION = TXID, ALWAYS
   - Money is credited ONLY after the user taps I PAID and sends
     the transaction hash, which is checked on-chain (right
     network, right wallet, USDT contract, success, amount).
   - No TXID -> no verification -> no credit. No exceptions.
3. HIGH-SECURITY HARDENING
   - EVM deposits need >= 3 block confirmations before the TXID
     is accepted (BSC + Polygon).
   - Wrong-TXID attempts per order are capped (lockout) to stop
     brute-force probing.
   - One TXID pays ONE order only (cross-network hash guard),
     double-credit guards and pending-only credit unchanged.

WHAT'S NEW IN v9.9.2 (keyless on-chain verification)
------------------------------------------------------------
1. PUBLIC BSC RPC INSTEAD OF THE EXPLORER API
   - Etherscan deprecated the free V1 endpoint and the free V2
     tier no longer covers BSC. The bot now reads USDT Transfer
     logs DIRECTLY from public BSC nodes (eth_getLogs) and uses
     eth_getTransactionReceipt for TX checks: 100% keyless,
     no rate limits, 5 endpoints rotated automatically.
   - The BscScan key stays configured but is now optional.

WHAT'S NEW IN v9.9.1 (guided auto-deposit + live API key)
------------------------------------------------------------
1. BSCSCAN API KEY ARMED
   - TITU's free BscScan key is now the built-in default
     (bscscan.com, ~100k lookups/day). Existing databases get
     it seeded automatically on first start. .env overrides.

2. USER'S 3-STEP DEPOSIT FLOW (asked order enforced)
   1) Pay the exact unique amount
   2) Paste the TX Hash -> bot verifies it on-chain INSTANTLY
      (recipient + reuse + amount + pending guards)
   3) Bot asks for the payment screenshot -> balance is
      credited AUTOMATICALLY right after it (or tap
      Confirm Now to skip the screenshot - money never waits)
   - While the screenshot is pending the background poller
     still credits within ~45s, so the step can never trap
     money. A stray Cancel can NOT orphan a verified payment.

3. EVERYTHING ELSE UNCHANGED
   - Same unique-amount payment codes, same double-credit
     guards, same admin manual approve fallback, refunds are
     still NEVER instant.

WHAT'S NEW IN v9.9 (USDT BEP20 auto-verify deposits)
------------------------------------------------------------
1. AUTO-VERIFY DEPOSITS (no admin wait)
   - User picks an amount and gets a UNIQUE pay amount
     (base + .01-.99 cent payment code) plus the BEP20 wallet.
   - A background poller sweeps BscScan every 45s; the moment a
     USDT transfer with that exact unique amount lands in the
     wallet, the balance is credited automatically and the user
     + admin group receive the on-chain proof.
   - The user can also paste the TX hash for an instant check
     (same safe credit path).

2. TITU'S WALLET SET
   - BEP20 wallet 0x4f5B...c772 active by default; official
     USDT (BSC) contract pinned; bscscan_api_key setting ready
     (free key from bscscan.com = 100k lookups/day).

3. STILL SAFE
   - One TX hash verifies ONE deposit only (reuse blocked).
   - Pending-only credit guard: double-poll / double-tap can
     never pay twice.
   - Unknown incoming transfers (wrong amount) are reported to
     the admin group once each - money is never silently lost.
   - Admin manual Approve/Reject still works as a fallback.

WHAT'S NEW IN v9.8 (seller-grade refunds + full audit pass)
------------------------------------------------------------
1. LIVE /api/sms/ DOUBLE-CHECK BEFORE ANY REFUND
   - Matched refunds are probed on the provider's clean endpoint
     (URL /sms/ -> /api/sms/) right before approval. A pure-digit
     answer means the OTP exists -> refund BLOCKED automatically
     (no payment). Waiting / text / network error = dead number ->
     refund approved. Only POSITIVE proof ever blocks a payout.

2. SELLER INPUT.TXT EXPORT (supplier claim)
   - Admin Panel -> Manage Refund -> Seller Input.txt sends every
     APPROVED dead number in the supplier's exact format
     username|user_id|phone|url as a file literally named
     input.txt (the seller's checker tool loads it directly;
     claim ~$0.10 per dead number back from the supplier).

3. REFUND IS STILL NEVER INSTANT
   - Money moves ONLY when the admin uploads/pastes the
     failed-urls list, every match passes the live check and the
     batch is approved. Request -> PENDING -> admin -> payout.

4. FULL A-TO-Z AUDIT FIXES
   - .txt uploads were silently DEAD (handler only accepted image
     documents): failed-urls upload AND stock .txt upload now work.
   - Deposit Approve/Reject is double-tap safe (status-guarded;
     approving twice can no longer credit the balance twice).
   - Buy button double-tap lock (cannot charge twice).
   - Admin can no longer ban himself; broadcasts skip banned
     users; pasting the failed-URL list works like uploading the
     .txt; re-adding a previously sold number warns about
     double-sell; deposit-cancel re-attaches the main menu;
     deprecated utcnow()/get_event_loop() removed; profile open
     self-heals; short-id mask fix.

WHAT'S NEW IN v9.7
------------------
1. OTP FIXES
   - Get OTP was showing the FIRST code in the API response (old SMS)
     so two numbers from the same provider session showed the SAME
     code. Baseline is now persisted per number; only NEW codes are
     delivered. No new code -> "OTP NOT RECEIVED YET".
   - Notification format is exactly:
       **\U0001F389 OTP RECEIVED** (bold)
       \U0001F7E2 {number}
       \u2705 {otp}

2. REFUND SYSTEM (strict)
   - Refund button next to Get OTP on the receipt.
   - 5-minute cooldown after purchase; OTP already received -> refund
     permanently refused; refund request blocks OTP for that number
     FOREVER (poller killed instantly).
   - Refund money is never instant: it stays PENDING until the admin
     approves. Admin Panel -> Manage Refund -> download the refund
     list (.txt, "number | url"), check every URL, upload a .txt of
     the FAILED urls -> matched refunds auto-approved and users paid
     automatically; unmatched ones are rejected and returned as .txt.

WHAT'S NEW IN v9.6
------------------
1. USA COUNTRY BUTTON FIXED (buy flow)
   - Tapping a country re-opened the country list instead of the
     confirm screen (callback format mismatch). Confirm is now
     reachable: country tap -> Confirm -> number delivered.

WHAT'S NEW IN v9.5
------------------
1. BUY FIXED (Out-of-Stock bug)
   - Purchases queried stock with the short code ("wa"/"tg") but
     inventory stores full names ("whatsapp"/"telegram"). The query
     never matched -> every buy showed Out of Stock. Type is now
     converted before the query.

WHAT'S NEW IN v9.4
------------------
1. ADD STOCK BUTTON FIXED
   - The Add Stock screen's keyboard function went missing during the
     v9.2 admin-panel compression -> every tap raised NameError and
     NOTHING happened. Function restored; type picker is inline again.

2. REPLY KEYBOARD NOW CLOSES
   - Bottom keyboard is no longer persistent: it closes automatically
     after every button tap (submenus stay clean), and re-opens when a
     top-level screen (main menu / admin panel / input prompt) arrives.

3. ERRORS ARE NEVER SILENT
   - If anything breaks, the user now gets a small warning message
     instead of dead silence.

WHAT'S NEW IN v9.3
------------------
1. BULK STOCK SYSTEM  (+number | otp-api-link)
   - Add stock ONE PER LINE:  +14133525884 | http://169.58.215.134:11111/...
   - Or upload a .txt file with the same format.
   - Auto-fixes small format mistakes (missing +, spaces, commas,
     semicolons, missing http://) and reports every skipped line.

2. INSTANT BACKGROUND OTP (10 minutes)
   - After purchase the bot polls the number's OWN OTP API every 5s
     for 10 minutes in the background.
   - First response = baseline (old SMS ignored); the moment a NEW code
     appears the user gets instantly:
       🎉 OTP received
       🟢 Your Number: +14133525884
       🔥 OTP :- 000000
   - After 10 min: polite timeout notice; the receipt's Get OTP button
     still works forever.

WHAT'S NEW IN v9.2
------------------
1. KEYBOARD NO LONGER COVERS HALF THE SCREEN
   - Identical bottom keyboards are NOT re-attached on every message
     (re-attaching re-opens/expands the keyboard on mobile phones).
   - Admin panel compressed to 3 columns.

2. ADMIN: MODIFY USER
   - Admin Panel -> Modify User -> send chat ID -> full user card
     (balance, deposits, spent, numbers bought, OTPs, orders...).
   - Inline Modify Balance: set exact / +add / -deduct.

3. ONLY USA
   - Country lists reduced to USA everywhere.

v9.1 (user-feedback fixes)
--------------------------
1. NOTHING GETS DELETED ANYMORE
   - Tapping any button NEVER deletes earlier messages. Receipts, OTPs,
     profiles — everything stays in the chat.

2. HYBRID NAVIGATION (back to the classic UX)
   - MAIN MENU stays in the bottom Reply Keyboard (Buy / Deposit /
     Profile / Support / Admin) — always pinned at the bottom.
   - SUB-MENUS (Buy type, Country picker, Confirm, Deposit amount,
     Admin flows...) are INLINE keyboards again, attached to the message,
     and they EDIT IN PLACE like the classic bot.
   - Smart state memory: press the phone's back button, reopen the chat,
     type /start — the SAME screen reappears.

3. STUCK-STATE BUG FIXED (kept from v9)
   - Tapping a menu button while the bot waits for input (e.g. TX Hash)
     no longer saves the button text as data.

4. 2026 PREMIUM LOOK (kept from v9)
   - Divider cards, receipt-style order confirmations, live balance +
     stock on the welcome screen, live rates on the buy screen, quick
     stats on the admin panel.

- python-telegram-bot v22.8
- Reply keyboard: main menu + admin panel + text-input prompts.
- Inline keyboards: every sub-menu + actions (Get OTP, Approve/Reject).
- NO Refer system. OTP delivered inline with purchase.
"""

import os
import random
import re
import json
import time
import asyncio
import uuid
import logging
from datetime import datetime, timedelta, timezone
from html import escape as html_escape

import aiosqlite
import aiohttp
try:
    from dotenv import load_dotenv
except ImportError:      # single-file deploy: .env not required
    def load_dotenv(*a, **k):
        return False

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.constants import ParseMode, ChatAction, KeyboardButtonStyle
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    TypeHandler,
    filters,
)

# --------------------------------------------------------------------------- #
#  LOGGING
# --------------------------------------------------------------------------- #
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("wpbot")
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# --------------------------------------------------------------------------- #
#  CONFIG  (env vars first - Railway/cloud ready; hardcoded fallbacks
#  keep single-file local deploys working exactly as before)
# --------------------------------------------------------------------------- #
def _env(name, default):
    """Read an env var; empty string means 'not set' -> default."""
    v = os.environ.get(name, "").strip()
    return v if v else default

def _env_int(name, default):
    try:
        return int(_env(name, str(default)))
    except (TypeError, ValueError):
        return default

# .env file support for local runs (python-dotenv optional)
try:
    if load_dotenv():  # loads .env from the script directory when present
        logger.info("Loaded .env file")
except Exception:
    pass

BOT_TOKEN = _env("BOT_TOKEN", "8913287576:AAE1R7H4vVglmuULHN6G394wwyRwp3UT-ZQ")
ADMIN_ID = _env_int("ADMIN_ID", 6582969543)
ADMIN_IDS = {ADMIN_ID}

# Group where deposit payment requests (TX hash + screenshot) are forwarded
DEPOSIT_GROUP_ID = _env_int("-1004298523143", -1004499183984)
# Group where every successful purchase is logged (order history)
ORDER_HISTORY_GROUP_ID = _env_int("-1004409338627", -1003942000856)

# --------------------------------------------------------------------------- #
#  v9.14 MANUAL PAYMENT CONFIG (bKash / Nagad / Binance)
# --------------------------------------------------------------------------- #
#  No crypto. User pays to the account below, sends a screenshot,
#  admin approves + enters the real amount -> wallet credited.
PAYMENT_METHODS = {
    "bkash":   {"label": "bKash",       "icon": "\U0001F7E6",
                "key": "bkash_number", "hint": "Send Money (Personal)"},
    "nagad":   {"label": "Nagad",       "icon": "\U0001F7E4",
                "key": "nagad_number", "hint": "Send Money (Personal)"},
    "binance": {"label": "Binance Pay", "icon": "\U0001F7E2",
                "key": "binance_id",   "hint": "Binance Pay ID"},
}
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Railway: attach a Volume at /data -> DB survives restarts & redeploys.
# Locally: /data usually doesn't exist -> falls back to ./data/bot.db.
if os.path.isdir("/data") and os.access("/data", os.W_OK):
    DB_PATH = "/data/bot.db"
else:
    DB_PATH = os.path.join(BASE_DIR, "data", "bot.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# Cloud migration: if /data/bot.db is missing but a bundled copy shipped
# with the repo (data/bot.db), seed the volume from it ONCE (first boot).
if DB_PATH == "/data/bot.db" and not os.path.exists(DB_PATH):
    _seed_db = os.path.join(BASE_DIR, "data", "bot.db")
    if os.path.exists(_seed_db):
        try:
            import shutil as _shutil
            _shutil.copy2(_seed_db, DB_PATH)
            logger.info("Seeded %s from bundled data/bot.db (migration)",
                        DB_PATH)
        except Exception as e:
            logger.warning("DB seed copy failed: %s", e)
DEPOSIT_AMOUNT_PRESETS = [0.30, 0.50, 1.00, 3.00]


DEFAULT_SETTINGS = {
    "whatsapp_rate": "2.50",
    "telegram_rate": "3.00",
    "min_deposit": "0.15",
    "deposit_expiry_minutes": "30",
    "bkash_number": "01XXXXXXXXX",
    "nagad_number": "01XXXXXXXXX",
    "binance_id": "123456789",
    "deposit_group_id": str(DEPOSIT_GROUP_ID),
    "order_history_group_id": str(ORDER_HISTORY_GROUP_ID),
    "bot_name": "VIP Numbers Store",
}


# (name, flag)
COUNTRIES = [
    ("USA", "\U0001F1FA\U0001F1F8"),
]

SUPPORT_USERNAME = "@saif20256"
DIV = "\u2508" * 17  # ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈ light divider (v9.13)

# --------------------------------------------------------------------------- #
#  BUTTON LABELS  (single source of truth for the keyboard + text router)
# --------------------------------------------------------------------------- #
BTN_BUY        = "\U0001F6D2 Buy Number"
BTN_PROFILE    = "\U0001F464 Profile"
BTN_DEPOSIT    = "\U0001F4B3 Deposit"
BTN_SUPPORT    = "\U0001F4AC Support"
BTN_SEARCH_OTP = "\U0001F50D Search OTP"
BTN_ADMIN      = "\U0001F6E0\uFE0F Admin Panel"
BTN_HOME       = "\U0001F3E0 Main Menu"
BTN_BACK       = "\u2B05\uFE0F Back"
BTN_CANCEL     = "\u274C Cancel"
BTN_CANCEL_DEP = "\u274C Cancel Deposit"

BTN_WA = "\U0001F7E2 WhatsApp"
BTN_TG = "\U0001F535 Telegram"

BTN_DEP_NEW  = "\U0001F4B5 New Deposit"
BTN_DEP_HIST = "\U0001F4DC History"

BTN_ADD_STOCK   = "\U0001F4E6 Add Stock"
BTN_STOCK_STATS = "\U0001F4CA Stock Stats"
BTN_PENDING     = "\U0001F4B0 Pending Deposits"
BTN_USERS       = "\U0001F465 Users"
BTN_STATS       = "\U0001F4C8 Statistics"
BTN_SET_RATE    = "\u2699\uFE0F Set Rate"
BTN_BROADCAST   = "\U0001F4E3 Broadcast"
BTN_SET_WALLET  = "\U0001F4B3 Payment Info"
BTN_OTP_STATS   = "\U0001F4E9 OTP Stats"
BTN_BAN         = "\U0001F512 Ban/Unban"

BTN_ADMINS        = "\U0001F451 Admins"
BTN_ADD_ADMIN     = "\u2795 Add Admin"
BTN_REMOVE_ADMIN  = "\u2796 Remove Admin"
BTN_NO_OTP_FILE   = "\U0001F4C4 No-OTP Numbers (.txt)"
BTN_USER_OTP_FILE = "\U0001F4CA User OTP Report (.txt)"

BTN_MODIFY_USER = "\u270f\ufe0f Modify User"
BTN_MANAGE_REFUND = "\U0001F4B8 Manage Refund"
BTN_REFUND_LIST = "\U0001F4C4 Refund List (.txt)"
BTN_SELLER_FILE = "\U0001F91D Seller Input.txt"
SELLER_REFUND_RATE = 0.10   # supplier pays ~$0.10 per dead number

BTN_WA_STOCK   = "\U0001F7E2 WhatsApp Stock"
BTN_TG_STOCK   = "\U0001F535 Telegram Stock"
BTN_BAN_USER   = "\U0001F512 Ban User"
BTN_UNBAN_USER = "\U0001F513 Unban User"

# States where any non-button text is treated as user input.
# NOTE: menu buttons are handled BEFORE these states, which fixes the old
# bug where a menu tap was saved as TX hash / phone / URL etc.
INPUT_STATES = {
    "search_otp",
    "awaiting_screenshot",
    "dep_custom",
    "admin_add_phone",
    "admin_add_url",
    "admin_set_rate",
    "admin_broadcast",
    "admin_ban",
    "admin_set_pay",
    "admin_modify_user",
    "admin_modbal",
    "admin_approve_amount",
    "admin_otp_stats",
    "admin_add_admin",
    "admin_remove_admin",
}


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def load_admins():
    """v9.15: load DB admins into the live ADMIN_IDS set (boot + edits)."""
    global ADMIN_IDS
    ADMIN_IDS = {ADMIN_ID}
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT telegram_id FROM users WHERE is_admin=1")
            rows = await cur.fetchall()
            await cur.close()
        ADMIN_IDS |= {int(r[0]) for r in rows}
        logger.info("Admins loaded (%s): %s", len(ADMIN_IDS), sorted(ADMIN_IDS))
    except Exception as e:
        logger.warning("load_admins failed (fresh DB?): %s", e)


async def add_admin(telegram_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_admin=1 WHERE telegram_id=?",
                         (telegram_id,))
        await db.commit()
    await load_admins()
    return True


async def remove_admin(telegram_id: int) -> bool:
    if telegram_id == ADMIN_ID:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_admin=0 WHERE telegram_id=?",
                         (telegram_id,))
        await db.commit()
    await load_admins()
    return True


async def list_admins() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT telegram_id, username, first_name FROM users "
            "WHERE is_admin=1 ORDER BY telegram_id")
        rows = [dict(r) for r in await cur.fetchall()]
        await cur.close()
    return rows


def flag_of(country: str) -> str:
    for n, f in COUNTRIES:
        if n == country:
            return f
    return "\U0001F30D"


def _utcnow():
    """Naive UTC datetime (DB stores UTC) without the deprecated utcnow()."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def country_from_button(text: str):
    """Return the country name if `text` matches a country button label."""
    for name, flag in COUNTRIES:
        if text == f"{flag} {name}":
            return name
    return None


# Track last bot messages per user so we can clean up stale menu messages
def _track_msg(context, uid, msg):
    if "bot_msgs" not in context.bot_data:
        context.bot_data["bot_msgs"] = {}
    store = context.bot_data["bot_msgs"].setdefault(uid, [])
    store.append(msg.message_id)
    if len(store) > 20:
        del store[: len(store) - 20]


async def _clear_last_msg(context, uid, chat_id=None):
    """DEPRECATED — kept for compatibility. Does NOT delete anything anymore.
    Users complained that messages disappeared on every button tap.
    The bot must never delete messages."""
    return


async def _send_tracked(update, context, text, reply_markup, parse_mode=None):
    """Render a screen. NEVER deletes any previous message.

    - Normal text update -> reply with the given markup.
    - Inline button tap  -> EDIT the button message in place when the new
      markup is an inline keyboard (classic single-message navigation);
      otherwise send a fresh message so nothing is lost.
    """
    uid = update.effective_user.id
    pm = parse_mode or ParseMode.HTML

    # Don't re-attach a reply keyboard the user already has
    if isinstance(reply_markup, ReplyKeyboardMarkup):
        reply_markup = _kb_dedupe(context, uid, reply_markup)

    if update.callback_query:
        q = update.callback_query
        if isinstance(reply_markup, InlineKeyboardMarkup):
            try:
                await q.edit_message_text(text, parse_mode=pm,
                                          reply_markup=reply_markup)
                _track_msg(context, uid, q.message)
                return q.message
            except BadRequest as e:
                if "not modified" in str(e).lower():
                    return q.message
                # anything else (photo message etc.) -> fall through & send
            except Exception:
                pass
        msg = await context.bot.send_message(
            chat_id=update.effective_chat.id, text=text, parse_mode=pm,
            reply_markup=reply_markup,
        )
        _track_msg(context, uid, msg)
        return msg

    msg = await update.message.reply_text(
        text, parse_mode=pm, reply_markup=reply_markup
    )
    _track_msg(context, uid, msg)
    return msg


async def get_setting(key: str) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = await cur.fetchone()
        await cur.close()
        return row[0] if row else DEFAULT_SETTINGS.get(key, "")


async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO settings(key,value,updated_at) VALUES(?,?,datetime('now')) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')",
            (key, str(value)),
        )
        await db.commit()

# --------------------------------------------------------------------------- #
#  DATABASE
# --------------------------------------------------------------------------- #
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                balance REAL DEFAULT 0.0,
                total_deposit REAL DEFAULT 0.0,
                total_spent REAL DEFAULT 0.0,
                total_purchased INTEGER DEFAULT 0,
                total_otp INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0,
                is_admin INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS stock (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone_number TEXT NOT NULL,
                otp_url TEXT NOT NULL,
                number_type TEXT NOT NULL,
                country TEXT DEFAULT 'USA',
                status TEXT DEFAULT 'available',
                otp_status TEXT DEFAULT 'pending',
                otp_code TEXT,
                added_by INTEGER,
                sold_to INTEGER,
                created_at TEXT DEFAULT (datetime('now')),
                sold_at TEXT,
                otp_fetched_at TEXT,
                refund_state TEXT,
                otp_blocked INTEGER DEFAULT 0,
                baseline_codes TEXT
            );
            CREATE TABLE IF NOT EXISTS deposits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                deposit_id TEXT UNIQUE NOT NULL,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                usdt_address TEXT,
                tx_hash TEXT,
                screenshot_file_id TEXT,
                network TEXT,
                status TEXT DEFAULT 'pending',
                group_message_id INTEGER,
                expires_at TEXT,
                confirmed_by INTEGER,
                created_at TEXT DEFAULT (datetime('now')),
                confirmed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT UNIQUE NOT NULL,
                user_id INTEGER NOT NULL,
                number_type TEXT NOT NULL,
                country TEXT,
                total_amount REAL NOT NULL,
                quantity INTEGER NOT NULL,
                numbers TEXT NOT NULL,
                rate_at_purchase REAL NOT NULL,
                status TEXT DEFAULT 'completed',
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS refunds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                refund_id TEXT UNIQUE NOT NULL,
                user_id INTEGER NOT NULL,
                stock_id INTEGER NOT NULL,
                phone_number TEXT NOT NULL,
                otp_url TEXT NOT NULL,
                amount REAL NOT NULL,
                order_id TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now')),
                decided_at TEXT,
                decided_by INTEGER
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS rate_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rate_type TEXT,
                old_rate REAL,
                new_rate REAL,
                changed_by INTEGER,
                changed_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS user_states (
                user_id INTEGER PRIMARY KEY,
                state TEXT,
                data TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            );
            """
        )
        # Safe column adds for older DBs
        for col, typedef in [("total_purchased", "INTEGER DEFAULT 0"),
                             ("total_otp", "INTEGER DEFAULT 0")]:
            try:
                await db.execute(f"ALTER TABLE users ADD COLUMN {col} {typedef};")
            except Exception:
                pass
        try:
            await db.execute("ALTER TABLE stock ADD COLUMN country TEXT DEFAULT 'USA';")
        except Exception:
            pass
        for col, typedef in [
            ("refund_state", "TEXT"),
            ("otp_blocked", "INTEGER DEFAULT 0"),
            ("baseline_codes", "TEXT"),
        ]:
            try:
                await db.execute(f"ALTER TABLE stock ADD COLUMN {col} {typedef};")
            except Exception:
                pass
        for col, typedef in [
            ("pay_amount", "REAL"),
            ("created_ts", "INTEGER"),
            ("screenshot_chat_id", "INTEGER"),
            ("screenshot_msg_id", "INTEGER"),
            ("admin_msg_ids", "TEXT"),
        ]:
            try:
                await db.execute(f"ALTER TABLE deposits ADD COLUMN {col} {typedef};")
            except Exception:
                pass
        # Seed default settings
        for k, v in DEFAULT_SETTINGS.items():
            await db.execute(
                "INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v)
            )
        # v9.10: enforce the new minimum deposit on old databases
        await db.execute(
            "UPDATE settings SET value='0.15' WHERE key='min_deposit' "
            "AND CAST(value AS REAL) < 0.15")
        # v9.12: deposit audit trail (append-only)
        await db.execute(
            "CREATE TABLE IF NOT EXISTS deposit_trace("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "ts INTEGER NOT NULL, deposit_id TEXT, user_id INTEGER,"
            "network TEXT, txid TEXT, event TEXT NOT NULL, detail TEXT)")
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_deptrace_dep "
            "ON deposit_trace(deposit_id)")
        # Mark admin
        await db.execute(
            "UPDATE users SET is_admin=1 WHERE telegram_id=?", (ADMIN_ID,)
        )
        await db.commit()
    logger.info("Database ready at %s", DB_PATH)


# --------------------------------------------------------------------------- #
#  CRUD
# --------------------------------------------------------------------------- #
async def get_or_create_user(telegram_id, username=None, first_name=None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM users WHERE telegram_id=?", (telegram_id,)
        )
        row = await cur.fetchone()
        await cur.close()
        if row is None:
            is_adm = 1 if telegram_id in ADMIN_IDS else 0
            cur = await db.execute(
                "INSERT INTO users(telegram_id,username,first_name,is_admin) "
                "VALUES(?,?,?,?)",
                (telegram_id, username, first_name, is_adm),
            )
            await db.commit()
            uid = cur.lastrowid
            cur2 = await db.execute("SELECT * FROM users WHERE id=?", (uid,))
            row = await cur2.fetchone()
            await cur2.close()
        return dict(row)


async def get_user(telegram_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM users WHERE telegram_id=?", (telegram_id,)
        )
        row = await cur.fetchone()
        await cur.close()
        return dict(row) if row else None


async def deduct_balance(telegram_id, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET balance=balance-?, total_spent=total_spent+?, "
            "total_purchased=total_purchased+1, updated_at=datetime('now') "
            "WHERE telegram_id=?",
            (amount, amount, telegram_id),
        )
        await db.commit()


async def increment_otp_count(telegram_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET total_otp=total_otp+1 WHERE telegram_id=?",
            (telegram_id,),
        )
        await db.commit()


async def set_ban(telegram_id, banned: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET is_banned=? WHERE telegram_id=?",
            (1 if banned else 0, telegram_id),
        )
        await db.commit()


async def set_balance(telegram_id, amount: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET balance=?, updated_at=datetime('now') "
            "WHERE telegram_id=?",
            (round(float(amount), 2), telegram_id),
        )
        await db.commit()


async def get_all_users():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users ORDER BY id")
        rows = await cur.fetchall()
        await cur.close()
        return [dict(r) for r in rows]


async def add_stock(phone, otp_url, ntype, country, added_by):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO stock(phone_number,otp_url,number_type,country,added_by) "
            "VALUES(?,?,?,?,?)",
            (phone, otp_url, ntype, country, added_by),
        )
        await db.commit()


async def phone_in_available_stock(phone):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM stock WHERE phone_number=? AND status='available'",
            (phone,),
        )
        n = (await cur.fetchone())[0]
        await cur.close()
        return n > 0


async def phone_in_stock_any(phone):
    """True if the phone exists in stock in ANY state (sold/refunded too)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM stock WHERE phone_number=?", (phone,)
        )
        n = (await cur.fetchone())[0]
        await cur.close()
        return n > 0


async def get_available_stock(ntype=None, country=None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        q = "SELECT * FROM stock WHERE status='available'"
        params = []
        if ntype:
            q += " AND number_type=?"
            params.append(ntype)
        if country:
            q += " AND country=?"
            params.append(country)
        q += " ORDER BY id LIMIT 1"
        cur = await db.execute(q, params)
        row = await cur.fetchone()
        await cur.close()
        return dict(row) if row else None


async def get_stock_counts():
    async with aiosqlite.connect(DB_PATH) as db:
        counts = {}
        for nt in ("whatsapp", "telegram"):
            cur = await db.execute(
                "SELECT country, COUNT(*) c FROM stock WHERE status='available' "
                "AND number_type=? GROUP BY country",
                (nt,),
            )
            rows = await cur.fetchall()
            await cur.close()
            counts[nt] = {r[0]: r[1] for r in rows}
        cur = await db.execute(
            "SELECT COUNT(*) FROM stock WHERE status='available'"
        )
        total = (await cur.fetchone())[0]
        await cur.close()
        return counts, total


async def mark_stock_sold(stock_id, sold_to):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE stock SET status='sold', sold_to=?, sold_at=datetime('now') "
            "WHERE id=?",
            (sold_to, stock_id),
        )
        await db.commit()


async def get_stock_item(stock_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM stock WHERE id=?", (stock_id,))
        row = await cur.fetchone()
        await cur.close()
        return dict(row) if row else None


async def update_otp_for_stock(stock_id, otp_code):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE stock SET otp_code=?, otp_status='used', "
            "otp_fetched_at=datetime('now') WHERE id=?",
            (otp_code, stock_id),
        )
        await db.commit()


async def get_stock_baseline(stock_id):
    """Codes that were already on the number's API at purchase time."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT baseline_codes FROM stock WHERE id=?", (stock_id,)
        )
        row = await cur.fetchone()
        await cur.close()
        if not row or not row[0]:
            return []
        try:
            return json.loads(row[0])
        except Exception:
            return []


async def save_stock_baseline(stock_id, codes):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE stock SET baseline_codes=? WHERE id=?",
            (json.dumps(list(codes or [])), stock_id),
        )
        await db.commit()


async def set_stock_refund_state(stock_id, state, otp_blocked=None, status=None):
    async with aiosqlite.connect(DB_PATH) as db:
        sets, params = ["refund_state=?"], [state]
        if otp_blocked is not None:
            sets.append("otp_blocked=?")
            params.append(1 if otp_blocked else 0)
        if status:
            sets.append("status=?")
            params.append(status)
        params.append(stock_id)
        await db.execute(
            f"UPDATE stock SET {', '.join(sets)} WHERE id=?", params
        )
        await db.commit()


async def credit_refund_balance(telegram_id, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET balance=balance+?, updated_at=datetime('now') "
            "WHERE telegram_id=?",
            (amount, telegram_id),
        )
        await db.commit()


async def get_order_amount_for(uid, phone):
    """(amount, order_id) of the order that contained this phone, or (None, None)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT total_amount, order_id FROM orders "
            "WHERE user_id=? AND numbers LIKE ? ORDER BY id DESC LIMIT 1",
            (uid, f'%"{phone}"%'),
        )
        row = await cur.fetchone()
        await cur.close()
        if row and row[0] is not None:
            return float(row[0]), row[1]
        return None, None


async def create_refund_request(uid, stock, amount, order_id=None):
    refund_id = f"RFD{uuid.uuid4().hex[:8].upper()}"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO refunds(refund_id,user_id,stock_id,phone_number,"
            "otp_url,amount,order_id) VALUES(?,?,?,?,?,?,?)",
            (refund_id, uid, stock["id"], stock["phone_number"],
             stock["otp_url"], float(amount), order_id),
        )
        await db.commit()
    return refund_id


async def get_pending_refunds():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM refunds WHERE status='pending' ORDER BY id ASC"
        )
        rows = await cur.fetchall()
        await cur.close()
        return [dict(r) for r in rows]


async def count_refunds(status):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM refunds WHERE status=?", (status,)
        )
        n = (await cur.fetchone())[0]
        await cur.close()
        return n


async def mark_refund(refund_id, status, decided_by):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE refunds SET status=?, decided_at=datetime('now'), "
            "decided_by=? WHERE refund_id=?",
            (status, decided_by, refund_id),
        )
        await db.commit()


async def get_refunds_by_status(status):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM refunds WHERE status=? ORDER BY id ASC",
            (status,),
        )
        rows = await cur.fetchall()
        await cur.close()
        return [dict(r) for r in rows]


def normalize_url(u):
    return (u or "").strip().rstrip("/")


async def create_order(user_id, ntype, country, amount, numbers, rate):
    order_id = f"ORD{uuid.uuid4().hex[:8].upper()}"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO orders(order_id,user_id,number_type,country,total_amount,"
            "quantity,numbers,rate_at_purchase) VALUES(?,?,?,?,?,?,?,?)",
            (order_id, user_id, ntype, country, amount, 1, json.dumps(numbers), rate),
        )
        await db.commit()
    return order_id


async def create_deposit(user_id, amount, method="bkash"):
    deposit_id = f"DEP{uuid.uuid4().hex[:8].upper()}"
    mins = int(await get_setting("deposit_expiry_minutes"))
    expires = (_utcnow() + timedelta(minutes=mins)).strftime(
        "%Y-%m-%d %H:%M UTC"
    )
    created_ts = int(_utcnow().timestamp())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO deposits(deposit_id,user_id,amount,pay_amount,"
            "network,created_ts,expires_at) VALUES(?,?,?,?,?,?,?)",
            (deposit_id, user_id, amount, amount, method,
             created_ts, expires),
        )
        await db.commit()
    return deposit_id, expires


async def get_deposit(deposit_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM deposits WHERE deposit_id=?", (deposit_id,)
        )
        row = await cur.fetchone()
        await cur.close()
        return dict(row) if row else None


async def update_deposit_tx(deposit_id, tx_hash, screenshot_file_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE deposits SET tx_hash=?, screenshot_file_id=? WHERE deposit_id=?",
            (tx_hash, screenshot_file_id, deposit_id),
        )
        await db.commit()


async def cancel_pending_deposit(uid, deposit_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE deposits SET status='cancelled' "
            "WHERE deposit_id=? AND user_id=? AND status='pending'",
            (deposit_id, uid),
        )
        await db.commit()


async def get_pending_deposits():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM deposits WHERE status='pending' AND screenshot_file_id IS NOT NULL "
            "ORDER BY id DESC"
        )
        rows = await cur.fetchall()
        await cur.close()
        return [dict(r) for r in rows]


async def confirm_deposit(dep_id, admin_id, credit_amount=None):
    """Confirm a pending manual deposit. credit_amount (typed by the
    admin) overrides the user-claimed amount. Double-tap safe."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM deposits WHERE deposit_id=? AND status='pending'",
            (dep_id,),
        )
        dep = await cur.fetchone()
        await cur.close()
        if not dep:
            return None
        dep = dict(dep)
        amount = float(credit_amount if credit_amount is not None
                       else dep["amount"])
        cur = await db.execute(
            "UPDATE deposits SET status='confirmed', amount=?, confirmed_by=?, "
            "confirmed_at=datetime('now') WHERE deposit_id=? AND status='pending'",
            (amount, admin_id, dep_id),
        )
        if cur.rowcount == 0:   # decided between the two queries - no double pay
            return None
        await db.execute(
            "UPDATE users SET balance=balance+?, total_deposit=total_deposit+?, "
            "updated_at=datetime('now') WHERE telegram_id=?",
            (amount, amount, dep["user_id"]),
        )
        await db.commit()
        dep["amount"] = amount
        return dep


async def reject_deposit(deposit_id, admin_id):
    """Reject ONLY a still-pending deposit (double-tap safe)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE deposits SET status='rejected', confirmed_by=?, "
            "confirmed_at=datetime('now') WHERE deposit_id=? AND status='pending'",
            (admin_id, deposit_id),
        )
        await db.commit()
        return cur.rowcount > 0


async def get_statistics():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM users")
        users = (await cur.fetchone())[0]; await cur.close()
        cur = await db.execute("SELECT COUNT(*) FROM stock WHERE status='available'")
        avail = (await cur.fetchone())[0]; await cur.close()
        cur = await db.execute("SELECT COUNT(*) FROM stock WHERE status='sold'")
        sold = (await cur.fetchone())[0]; await cur.close()
        cur = await db.execute("SELECT COUNT(*) FROM deposits WHERE status='pending'")
        pend = (await cur.fetchone())[0]; await cur.close()
        cur = await db.execute("SELECT COALESCE(SUM(total_deposit),0) FROM users")
        tot_dep = (await cur.fetchone())[0]; await cur.close()
        cur = await db.execute("SELECT COALESCE(SUM(total_spent),0) FROM users")
        tot_spend = (await cur.fetchone())[0]; await cur.close()
        return {
            "users": users, "available": avail, "sold": sold,
            "pending_deposits": pend, "total_deposit": tot_dep,
            "total_spent": tot_spend,
        }


async def set_user_state(user_id, state, data=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO user_states(user_id,state,data,updated_at) "
            "VALUES(?,?,?,datetime('now')) "
            "ON CONFLICT(user_id) DO UPDATE SET state=excluded.state, "
            "data=excluded.data, updated_at=datetime('now')",
            (user_id, state, json.dumps(data) if data else None),
        )
        await db.commit()


async def get_user_state(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM user_states WHERE user_id=?", (user_id,)
        )
        row = await cur.fetchone()
        await cur.close()
        if not row:
            return None, None
        return row["state"], (json.loads(row["data"]) if row["data"] else None)


async def clear_user_state(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM user_states WHERE user_id=?", (user_id,))
        await db.commit()


# --------------------------------------------------------------------------- #
#  OTP FETCH  (backend fetches secret URL, user never sees URL)
# --------------------------------------------------------------------------- #
async def fetch_sms_text(url, session=None, timeout: int = 15):
    """GET the OTP API URL and return the raw response text (or None)."""
    if not url or not str(url).strip():
        return None
    try:
        if session is not None:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                return await resp.text()
        async with aiohttp.ClientSession() as sess:
            async with sess.get(
                url, timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                return await resp.text()
    except Exception as e:
        logger.warning("SMS API fetch failed: %s", e)
        return None


def _otp_codes(text):
    """Extract OTP-looking codes from an API response, best candidates first.
    Priority: 6-digit > 123-456 style > 5-digit > 4-digit."""
    if not text:
        return []
    text = str(text)
    out = []
    for pat in (
        r"(?<!\d)(\d{6})(?!\d)",
        r"(?<!\d)(\d{3})[-\s](\d{3})(?!\d)",
        r"(?<!\d)(\d{5})(?!\d)",
        r"(?<!\d)(\d{4})(?!\d)",
    ):
        for m in re.finditer(pat, text):
            code = "".join(g for g in m.groups() if g)
            if code and code not in out:
                out.append(code)
        if out:
            break  # never mix weaker patterns once a stronger one matched
    return out


async def fetch_otp(otp_url: str, timeout: int = 25):
    """Fetch OTP from the secret provider URL. Returns OTP string or None."""
    text = await fetch_sms_text(otp_url, None, timeout)
    codes = _otp_codes(text)
    return codes[0] if codes else None


def api_sms_endpoint(otp_url: str) -> str:
    """Seller-style clean probe endpoint: /sms/ -> /api/sms/.
    That endpoint answers pure digits when an OTP exists and plain
    text (WAITING / expiry notice) otherwise."""
    u = (otp_url or "").strip()
    if "/api/sms/" in u:
        return u
    if "/sms/" in u:
        return u.replace("/sms/", "/api/sms/", 1)
    return u


LIVE_CODE_RE = re.compile(r"^\d{3,10}$")


async def check_live_otp(otp_url: str, timeout: int = 6):
    """Live OTP probe using the seller's own rule: ONLY a pure-digit
    response proves a code exists (WAITING / errors prove nothing).
    Returns ("otp", code) | ("waiting", None) | ("unknown", None)."""
    if not otp_url:
        return ("unknown", None)
    text = await fetch_sms_text(api_sms_endpoint(otp_url), None, timeout)
    if text is None:
        return ("unknown", None)
    t = str(text).strip()
    if t and LIVE_CODE_RE.match(t):
        return ("otp", t)
    return ("waiting", None)


# --------------------------------------------------------------------------- #
#  STOCK PARSER  ("+14133525884 | http://otp-api")  — auto-fixes bad formats
# --------------------------------------------------------------------------- #
PHONE_RE = re.compile(r"\+?\d{10,15}")
URL_RE = re.compile(r"https?://[^\s|;,<>]+", re.IGNORECASE)
BARE_IP_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}:\d{2,5}/\S+")


def normalize_phone(raw: str):
    digits = re.sub(r"\D", "", raw or "")
    if not (10 <= len(digits) <= 15):
        return None
    return "+" + digits


def parse_stock_line(line: str):
    """Parse one stock line.
    Returns ((phone, url), None) on success or ((None, None), reason)."""
    line = (line or "").strip()
    if not line:
        return (None, None), "empty"

    url = ""
    rest = line
    m = URL_RE.search(line)
    if m:
        url = m.group(0).rstrip(".,;)")
        rest = line[: m.start()] + " " + line[m.end():]
    else:
        m2 = BARE_IP_RE.search(rest)  # forgot http:// but it's an IP link
        if m2:
            url = "http://" + m2.group(0)
            rest = rest.replace(m2.group(0), " ", 1)

    # separators the admin might use instead of |
    rest = rest.replace("|", " ").replace(";", " ").replace(",", " ")
    rest = rest.replace("\t", " ")
    # drop phone-formatting punctuation, then glue everything together
    rest = re.sub(r"[()\u2013\u2014.\-]", " ", rest)
    rest = re.sub(r"\s+", "", rest)

    pm = PHONE_RE.search(rest)
    if not pm:
        return (None, None), "no phone number found"
    phone = normalize_phone(pm.group(0))
    if not phone:
        return (None, None), "invalid number length"
    return (phone, url), None


def parse_stock_lines(text: str):
    """Parse a multi-line stock dump.
    Returns (entries, errors):
      entries = [(phone, url), ...]
      errors  = [(line_no, sample, reason), ...]
    """
    entries, errors = [], []
    for i, line in enumerate((text or "").splitlines(), 1):
        res, err = parse_stock_line(line)
        if err == "empty":
            continue
        if err:
            errors.append((i, line.strip()[:48], err))
        else:
            entries.append(res)
    return entries, errors


# --------------------------------------------------------------------------- #
#  KEYBOARDS
#  MAIN MENU + ADMIN PANEL + TEXT-INPUT PROMPTS -> bottom REPLY keyboard
#  ALL SUB-MENUS -> INLINE keyboards on the message (classic edit-in-place)
#  The reply keyboard is NOT persistent: Telegram closes it after every
#  button tap, so submenus stay clean. Top-level screens (main menu /
#  admin panel / input prompts) re-attach it -> it pops back up.
# --------------------------------------------------------------------------- #
def _kb(rows, placeholder):
    return ReplyKeyboardMarkup(
        rows, resize_keyboard=True, is_persistent=False,
        input_field_placeholder=placeholder,
    )


def _ikb(rows):
    return InlineKeyboardMarkup(rows)


def _kb_dedupe(context, uid, markup):
    """Always return the markup.

    Earlier this suppressed re-sending an identical keyboard, but the
    reply keyboard is NOT persistent anymore: Telegram closes it after
    every button tap, so every top-level reply MUST re-attach it or the
    menu would disappear forever."""
    return markup


def _nav_row():
    return [
        KeyboardButton(BTN_BACK, style=KeyboardButtonStyle.DANGER),
        KeyboardButton(BTN_HOME, style=KeyboardButtonStyle.DANGER),
    ]


def _inline_nav_row(back_cb=None):
    """Inline Back / Main-Menu row. Back edits in place, Main Menu sends fresh."""
    row = []
    if back_cb:
        row.append(InlineKeyboardButton("\u2b05\ufe0f Back",
                                        callback_data=back_cb,
                                        style=KeyboardButtonStyle.DANGER))
    row.append(InlineKeyboardButton("\U0001f3e0 Main Menu",
                                    callback_data="nav:home",
                                    style=KeyboardButtonStyle.DANGER))
    return row


def main_menu_kb(is_adm: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(BTN_BUY, style=KeyboardButtonStyle.SUCCESS),
         KeyboardButton(BTN_PROFILE, style=KeyboardButtonStyle.PRIMARY)],
        [KeyboardButton(BTN_SEARCH_OTP, style=KeyboardButtonStyle.PRIMARY),
         KeyboardButton(BTN_DEPOSIT, style=KeyboardButtonStyle.PRIMARY)],
        [KeyboardButton(BTN_SUPPORT, style=KeyboardButtonStyle.PRIMARY)],
    ]
    if is_adm:
        rows.append([KeyboardButton(BTN_ADMIN, style=KeyboardButtonStyle.SUCCESS)])
    return _kb(rows, "Choose an option \U0001F447")


def home_only_kb() -> InlineKeyboardMarkup:
    return _ikb([_inline_nav_row()])


def back_home_kb() -> InlineKeyboardMarkup:
    return _ikb([_inline_nav_row("nav:back")])


def buy_type_kb() -> InlineKeyboardMarkup:
    return _ikb(
        [
            [InlineKeyboardButton(BTN_WA, callback_data="buy:wa",
                                  style=KeyboardButtonStyle.SUCCESS),
             InlineKeyboardButton(BTN_TG, callback_data="buy:tg",
                                  style=KeyboardButtonStyle.PRIMARY)],
            _inline_nav_row(),
        ]
    )


def country_kb(prefix: str = "buy", ntype: str = "wa") -> InlineKeyboardMarkup:
    back_cb = "buy:back_type" if prefix == "buy" else "adst:back"
    rows, pair = [], []
    for name, flag in COUNTRIES:
        pair.append(InlineKeyboardButton(f"{flag} {name}",
                                         callback_data=f"{prefix}:{ntype}:{name}",
                                         style=KeyboardButtonStyle.PRIMARY))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data=back_cb,
                                      style=KeyboardButtonStyle.DANGER)])
    return _ikb(rows)


def buy_confirm_kb(price: float, ntype: str = "wa",
                   country: str = "USA") -> InlineKeyboardMarkup:
    return _ikb(
        [
            [InlineKeyboardButton(f"✅ Buy — ${price:.2f}",
                                  callback_data=f"buy:do:{ntype}:{country}",
                                  style=KeyboardButtonStyle.SUCCESS)],
            [InlineKeyboardButton("⬅️ Back",
                                  callback_data=f"buy:back_ctry:{ntype}",
                                  style=KeyboardButtonStyle.DANGER)],
        ]
    )


def deposit_menu_kb() -> InlineKeyboardMarkup:
    return _ikb(
        [
            [InlineKeyboardButton(BTN_DEP_NEW, callback_data="dep:new",
                                  style=KeyboardButtonStyle.SUCCESS)],
            [InlineKeyboardButton(BTN_DEP_HIST, callback_data="dep:hist",
                                  style=KeyboardButtonStyle.PRIMARY)],
            [InlineKeyboardButton(BTN_BACK, callback_data="nav:back",
                                  style=KeyboardButtonStyle.DANGER)],
        ]
    )


def deposit_amount_kb() -> InlineKeyboardMarkup:
    """v9.15: legacy name kept - now shows the payment methods."""
    return deposit_method_kb()


def deposit_method_kb() -> InlineKeyboardMarkup:
    return _ikb(
        [[InlineKeyboardButton("\U0001F7E6 bKash",
                               callback_data="dep:mth:bkash",
                               style=KeyboardButtonStyle.PRIMARY),
          InlineKeyboardButton("\U0001F7E4 Nagad",
                               callback_data="dep:mth:nagad",
                               style=KeyboardButtonStyle.PRIMARY)],
         [InlineKeyboardButton("\U0001F7E2 Binance Pay",
                               callback_data="dep:mth:binance",
                               style=KeyboardButtonStyle.SUCCESS)],
         [InlineKeyboardButton(BTN_BACK, callback_data="dep:back",
                               style=KeyboardButtonStyle.DANGER)],
        ]
    )


def deposit_wait_kb(deposit_id=None) -> InlineKeyboardMarkup:
    """v9.15 payment-details screen: user pays, then just sends the
    screenshot as a photo (state is already awaiting_screenshot)."""
    cb = f"dep:cancel:{deposit_id}" if deposit_id else "dep:cancel"
    return _ikb(
        [[InlineKeyboardButton(BTN_CANCEL_DEP, callback_data=cb,
                               style=KeyboardButtonStyle.DANGER)]],
    )


def deposit_custom_kb() -> InlineKeyboardMarkup:
    """CUSTOM AMOUNT screen: the user only types an amount here."""
    return _ikb(
        [[InlineKeyboardButton(BTN_CANCEL_DEP, callback_data="dep:cancel",
                               style=KeyboardButtonStyle.DANGER)]],
    )


def screenshot_kb(deposit_id=None) -> InlineKeyboardMarkup:
    """Screenshot screen: user sends payment screenshot. Cancel only."""
    cb = f"dep:cancel:{deposit_id}" if deposit_id else "dep:cancel"
    return _ikb(
        [[InlineKeyboardButton(BTN_CANCEL_DEP, callback_data=cb,
                               style=KeyboardButtonStyle.DANGER)]],
    )


def back_only_kb() -> InlineKeyboardMarkup:
    return _ikb(
        [[InlineKeyboardButton(BTN_BACK, callback_data="nav:back",
                               style=KeyboardButtonStyle.DANGER)]],
    )


def insufficient_kb() -> InlineKeyboardMarkup:
    return _ikb(
        [[InlineKeyboardButton(BTN_DEPOSIT, callback_data="nav:dep",
                               style=KeyboardButtonStyle.SUCCESS)],
         _inline_nav_row()],
    )


def admin_panel_kb() -> ReplyKeyboardMarkup:
    return _kb(
        [
            [KeyboardButton(BTN_ADD_STOCK, style=KeyboardButtonStyle.SUCCESS),
             KeyboardButton(BTN_STOCK_STATS, style=KeyboardButtonStyle.PRIMARY),
             KeyboardButton(BTN_PENDING, style=KeyboardButtonStyle.PRIMARY)],
            [KeyboardButton(BTN_USERS, style=KeyboardButtonStyle.PRIMARY),
             KeyboardButton(BTN_MODIFY_USER, style=KeyboardButtonStyle.SUCCESS),
             KeyboardButton(BTN_STATS, style=KeyboardButtonStyle.PRIMARY)],
            [KeyboardButton(BTN_SET_RATE, style=KeyboardButtonStyle.PRIMARY),
             KeyboardButton(BTN_BROADCAST, style=KeyboardButtonStyle.PRIMARY),
             KeyboardButton(BTN_SET_WALLET, style=KeyboardButtonStyle.PRIMARY)],
            [KeyboardButton(BTN_OTP_STATS, style=KeyboardButtonStyle.PRIMARY),
             KeyboardButton(BTN_NO_OTP_FILE, style=KeyboardButtonStyle.PRIMARY),
             KeyboardButton(BTN_USER_OTP_FILE, style=KeyboardButtonStyle.PRIMARY)],
            [KeyboardButton(BTN_MANAGE_REFUND, style=KeyboardButtonStyle.DANGER),
             KeyboardButton(BTN_ADMINS, style=KeyboardButtonStyle.SUCCESS)],
            [KeyboardButton(BTN_BAN, style=KeyboardButtonStyle.DANGER),
             KeyboardButton(BTN_HOME, style=KeyboardButtonStyle.DANGER)],
        ],
        "Select an action \U0001F447",
    )


def admin_admins_kb() -> InlineKeyboardMarkup:
    """\U0001F451 Admins screen: add / remove admin."""
    return _ikb(
        [
            [InlineKeyboardButton(BTN_ADD_ADMIN, callback_data="admg:add",
                                  style=KeyboardButtonStyle.SUCCESS),
             InlineKeyboardButton(BTN_REMOVE_ADMIN, callback_data="admg:rm",
                                  style=KeyboardButtonStyle.DANGER)],
            [InlineKeyboardButton("\u2b05\ufe0f Back", callback_data="nav:back",
                                  style=KeyboardButtonStyle.DANGER)],
        ]
    )


async def show_admin_admins(update, context):
    """\U0001F451 ADMINS screen: current list + add/remove."""
    await set_user_state(update.effective_user.id, "admin_admins")
    rows = await list_admins()
    lines = [
        "\U0001F451 <b>ADMINS</b>\n",
        f"{DIV}",
        f"\U0001F464 <b>Total:</b> {len(rows)}",
        f"{DIV}",
    ]
    for r in rows:
        uname = f"@{r['username']}" if r.get("username") else "\u2014"
        crown = " \U0001F451 SUPER" if r["telegram_id"] == ADMIN_ID else ""
        lines.append(
            f"\U0001F194 <code>{r['telegram_id']}</code> \u2014 "
            f"{html_escape(str(r.get('first_name') or '?'))} {uname}{crown}")
    lines.append(DIV)
    await _send_tracked(update, context, "\n".join(lines),
                        admin_admins_kb())


async def prompt_admin_add_admin(update, context):
    await set_user_state(update.effective_user.id, "admin_add_admin")
    await _send_tracked(update, context,
                        "\u2795 <b>ADD ADMIN</b>\n"
                        f"{DIV}\n"
                        "\U0001F194 Send the <b>Telegram user ID</b> of the "
                        "new admin:\n"
                        "<i>(The user must have opened the bot at least "
                        "once)</i>",
                        admin_input_kb())


async def prompt_admin_remove_admin(update, context):
    await set_user_state(update.effective_user.id, "admin_remove_admin")
    await _send_tracked(update, context,
                        "\u2796 <b>REMOVE ADMIN</b>\n"
                        f"{DIV}\n"
                        "\U0001F194 Send the <b>Telegram user ID</b> to "
                        "remove:\n"
                        "<i>(The super admin can\'t be removed)</i>",
                        admin_input_kb())


async def send_no_otp_file(update, context):
    """\U0001F4C4 Feature 2: .txt of EVERY sold number with NO OTP."""
    if not is_admin(update.effective_user.id):
        return
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT s.phone_number, s.number_type, s.sold_to, s.otp_url, "
            "u.username, u.first_name "
            "FROM stock s LEFT JOIN users u ON u.telegram_id = s.sold_to "
            "WHERE s.sold_to IS NOT NULL "
            "AND (s.otp_code IS NULL OR s.otp_status != 'used') "
            "ORDER BY s.sold_at DESC")
        rows = [dict(r) for r in await cur.fetchall()]
        await cur.close()
    if not rows:
        await _send_tracked(update, context,
                            "\u2705 <b>No dead numbers!</b>\n"
                            f"{DIV}\n"
                            "Every sold number got its OTP.",
                            admin_panel_kb())
        return
    head = [
        "=" * 62,
        " NO-OTP NUMBERS REPORT (full bot)",
        " Generated: " + _utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        " Total numbers without OTP: " + str(len(rows)),
        "=" * 62,
        "",
        " Format: phone | type | user_id | tg_username | otp_url",
        "",
    ]
    body = []
    for r in rows:
        uname = ("@" + r["username"]) if r.get("username") else "-"
        body.append(
            f"{r['phone_number']} | {r['number_type']} | {r['sold_to']} | "
            f"{uname} | {r['otp_url']}")
    content = "\n".join(head + body) + "\n"
    fname = "no_otp_numbers_%s.txt" % _utcnow().strftime("%Y%m%d_%H%M%S")
    await update.message.reply_document(
        document=content.encode("utf-8"), filename=fname,
        caption=(
            "\U0001F4C4 <b>No-OTP Numbers</b> \u2014 "
            f"<b>{len(rows)}</b> number(s)\n\n"
            "Every sold number in the whole bot that never received "
            "its OTP."),
        parse_mode=ParseMode.HTML,
    )


async def send_user_otp_report(update, context):
    """\U0001F4CA Feature 3: per-user .txt report (username, ID, count)."""
    if not is_admin(update.effective_user.id):
        return
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT s.sold_to, s.phone_number, s.number_type, s.otp_url, "
            "u.username, u.first_name "
            "FROM stock s LEFT JOIN users u ON u.telegram_id = s.sold_to "
            "WHERE s.sold_to IS NOT NULL "
            "AND (s.otp_code IS NULL OR s.otp_status != 'used') "
            "ORDER BY s.sold_to, s.id")
        rows = [dict(r) for r in await cur.fetchall()]
        await cur.close()
    if not rows:
        await _send_tracked(update, context,
                            "\u2705 <b>No dead numbers!</b>\n"
                            f"{DIV}\n"
                            "No user has a number without OTP.",
                            admin_panel_kb())
        return
    by_user = {}
    for r in rows:
        by_user.setdefault(r["sold_to"], []).append(r)
    head = [
        "=" * 62,
        " USER OTP REPORT (per-user no-OTP breakdown)",
        " Generated: " + _utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        " Users with no-OTP numbers: " + str(len(by_user)),
        " Total no-OTP numbers: " + str(len(rows)),
        "=" * 62,
        "",
    ]
    body = []
    for uid_ in sorted(by_user, key=lambda k: -len(by_user[k])):
        rs = by_user[uid_]
        r0 = rs[0]
        uname = ("@" + r0["username"]) if r0.get("username") else "-"
        body.append("-" * 62)
        body.append(f"USER: {html_escape(str(r0.get('first_name') or '?'))}")
        body.append(f"TG USERNAME: {uname}")
        body.append(f"USER ID: {uid_}")
        body.append(f"NUMBERS WITHOUT OTP: {len(rs)}")
        body.append("")
        for r in rs:
            body.append(f"  {r['phone_number']} | {r['number_type']} | "
                        f"{r['otp_url']}")
        body.append("")
    content = "\n".join(head + body) + "\n"
    fname = "user_otp_report_%s.txt" % _utcnow().strftime("%Y%m%d_%H%M%S")
    await update.message.reply_document(
        document=content.encode("utf-8"), filename=fname,
        caption=(
            "\U0001F4CA <b>User OTP Report</b> \u2014 "
            f"<b>{len(by_user)}</b> user(s), <b>{len(rows)}</b> no-OTP "
            "number(s)\n\n"
            "Per-user breakdown: TG username, user ID, and every "
            "number without OTP."),
        parse_mode=ParseMode.HTML,
    )


def admin_input_kb() -> ReplyKeyboardMarkup:
    return _kb(
        [[KeyboardButton(BTN_CANCEL, style=KeyboardButtonStyle.DANGER),
          KeyboardButton(BTN_ADMIN, style=KeyboardButtonStyle.PRIMARY)]],
        "Type your input, or Cancel",
    )


def admin_refund_kb() -> ReplyKeyboardMarkup:
    return _kb(
        [[KeyboardButton(BTN_REFUND_LIST, style=KeyboardButtonStyle.PRIMARY)],
         [KeyboardButton(BTN_SELLER_FILE, style=KeyboardButtonStyle.SUCCESS)],
         [KeyboardButton(BTN_CANCEL, style=KeyboardButtonStyle.DANGER),
          KeyboardButton(BTN_ADMIN, style=KeyboardButtonStyle.PRIMARY)]],
        "Manage refunds \U0001F447",
    )


def admin_add_type_kb() -> InlineKeyboardMarkup:
    """Number-type picker for Add Stock (inline, edit-in-place)."""
    return _ikb(
        [
            [InlineKeyboardButton(BTN_WA_STOCK, callback_data="adst:wa",
                                  style=KeyboardButtonStyle.SUCCESS),
             InlineKeyboardButton(BTN_TG_STOCK, callback_data="adst:tg",
                                  style=KeyboardButtonStyle.PRIMARY)],
            [InlineKeyboardButton("\u2b05\ufe0f Back", callback_data="nav:back",
                                  style=KeyboardButtonStyle.DANGER)],
        ]
    )


def admin_rate_pick_kb(wa: str, tg: str) -> InlineKeyboardMarkup:
    return _ikb(
        [
            [InlineKeyboardButton(f"🟢 WhatsApp — ${wa}",
                                  callback_data="adrt:wa",
                                  style=KeyboardButtonStyle.SUCCESS)],
            [InlineKeyboardButton(f"🔵 Telegram — ${tg}",
                                  callback_data="adrt:tg",
                                  style=KeyboardButtonStyle.PRIMARY)],
            [InlineKeyboardButton("⬅️ Back", callback_data="nav:back",
                                  style=KeyboardButtonStyle.DANGER)],
        ]
    )


def admin_ban_pick_kb() -> InlineKeyboardMarkup:
    return _ikb(
        [
            [InlineKeyboardButton(BTN_BAN_USER, callback_data="adbn:ban",
                                  style=KeyboardButtonStyle.DANGER),
             InlineKeyboardButton(BTN_UNBAN_USER, callback_data="adbn:unban",
                                  style=KeyboardButtonStyle.SUCCESS)],
            [InlineKeyboardButton("⬅️ Back", callback_data="nav:back",
                                  style=KeyboardButtonStyle.DANGER)],
        ]
    )


def otp_kb(stock_id: int, otp_url: str = "") -> InlineKeyboardMarkup:
    """v9.16 receipt keyboard: Get OTP + Open SMS Link + Main Menu."""
    rows = [
        [InlineKeyboardButton("\U0001F4E9 Get OTP", callback_data=f"otp:{stock_id}",
                              style=KeyboardButtonStyle.SUCCESS)],
    ]
    if (otp_url or "").strip():
        rows.append([InlineKeyboardButton(
            "\U0001F517 Open SMS Inbox", url=(otp_url or "").strip(),
            style=KeyboardButtonStyle.PRIMARY)])
    rows.append([InlineKeyboardButton("\U0001F3E0 Main Menu", callback_data="nav:home",
                                      style=KeyboardButtonStyle.PRIMARY)])
    return InlineKeyboardMarkup(rows)


def otp_link_kb(stock_id: int, otp_url: str = "") -> InlineKeyboardMarkup:
    """v9.16 waiting card: Get OTP retry + Open SMS Link."""
    rows = [
        [InlineKeyboardButton("\U0001F4E9 Get OTP", callback_data=f"otp:{stock_id}",
                              style=KeyboardButtonStyle.SUCCESS)],
    ]
    if (otp_url or "").strip():
        rows.append([InlineKeyboardButton(
            "\U0001F517 Open SMS Inbox", url=(otp_url or "").strip(),
            style=KeyboardButtonStyle.PRIMARY)])
    return InlineKeyboardMarkup(rows)


def admin_deposit_approve_kb(deposit_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("\u2705 Approve", callback_data=f"admdep:ok:{deposit_id}",
                               style=KeyboardButtonStyle.SUCCESS),
          InlineKeyboardButton("\u274C Reject", callback_data=f"admdep:no:{deposit_id}",
                               style=KeyboardButtonStyle.DANGER)]]
    )


# --------------------------------------------------------------------------- #
#  MESSAGES  (2026 premium card design)
# --------------------------------------------------------------------------- #
def menu_info_text() -> str:
    return (
        f"\U0001F3E0 <b>Main Menu</b>\n"
        f"{DIV}\n"
        f"\U0001F449 Where to next?"
    )


def menu_footer_text() -> str:
    return f"\u2705 Done! You\'re back at the main menu \U0001F447"


async def welcome_text(first_name: str, user: dict) -> str:
    bot_name = await get_setting("bot_name")
    safe_name = html_escape(first_name or "User")
    bal = (user or {}).get("balance", 0.0) or 0.0
    _, total = await get_stock_counts()
    return (
        f"\U0001F44B <b>Hey {safe_name}, welcome back!</b>\n"
        f"{DIV}\n"
        f"\U0001F48E <b>{html_escape(bot_name)}</b>\n"
        f"\U0001F4F2 Premium WhatsApp &amp; Telegram numbers\n"
        f"\u26A1 Instant delivery \u2022 OTP included\n\n"
        f"\U0001F4B0 Balance: <code>${bal:.2f}</code>\n"
        f"\U0001F4E6 In Stock: <code>{total}</code> numbers\n"
        f"{DIV}\n"
        f"\U0001F449 Tap a button below to get started"
    )


def profile_text(user: dict) -> str:
    uid = user["telegram_id"]
    uname = f"@{html_escape(user['username'])}" if user.get("username") else "\u2014"
    name = html_escape(user.get("first_name") or "\u2014")
    bal = user.get("balance", 0.0) or 0.0
    purchased = user.get("total_purchased", 0) or 0
    spent = user.get("total_spent", 0.0) or 0.0
    deposit = user.get("total_deposit", 0.0) or 0.0
    otp = user.get("total_otp", 0) or 0
    ratio = f"{(otp/purchased*100):.0f}%" if purchased else "0%"
    return (
        f"\U0001F464 <b>Your Profile</b>\n"
        f"{DIV}\n"
        f"\U0001F194 ID: <code>{uid}</code>\n"
        f"\U0001F4DB Name: {name}\n"
        f"\U0001F310 Username: {uname}\n"
        f"{DIV}\n"
        f"\U0001F4B0 Balance: <code>${bal:.2f}</code>\n"
        f"\U0001F6D2 Purchased: <code>{purchased}</code>\n"
        f"\U0001F4B8 Spent: <code>${spent:.2f}</code>\n"
        f"\U0001F3E6 Deposited: <code>${deposit:.2f}</code>\n"
        f"\U0001F4E9 OTPs: <code>{otp} ({ratio})</code>\n"
        f"{DIV}"
    )


def support_text() -> str:
    return (
        f"\U0001F4AC <b>Need Help?</b>\n"
        f"{DIV}\n"
        f"\U0001F468\u200D\U0001F4BB Admin: {SUPPORT_USERNAME}\n"
        f"\u26A1 Reply time: usually just minutes\n"
        f"{DIV}\n"
        f"Payments, OTP issues, stock questions \u2014 just message us, "
        f"we've got you. \U0001F64C"
    )


async def buy_intro_text() -> str:
    wa = float(await get_setting("whatsapp_rate"))
    tg = float(await get_setting("telegram_rate"))
    return (
        f"\U0001F6D2 <b>Buy a Number</b>\n"
        f"{DIV}\n"
        f"\U0001F7E2 WhatsApp \u2014 <code>${wa:.2f}</code>\n"
        f"\U0001F535 Telegram \u2014 <code>${tg:.2f}</code>\n"
        f"{DIV}\n"
        f"\U0001F449 Pick a type to continue"
    )


def buy_country_text(ntype: str) -> str:
    label = "WhatsApp" if ntype == "wa" else "Telegram"
    return (
        f"\U0001F30D <b>Choose a Country</b>\n"
        f"{DIV}\n"
        f"\U0001F4F2 {label} numbers available\n"
        f"{DIV}\n"
        f"\U0001F449 Select below"
    )


async def buy_confirm_text(ntype: str, country: str, balance: float) -> str:
    rate = float(await get_setting("whatsapp_rate" if ntype == "wa" else "telegram_rate"))
    label = "WhatsApp" if ntype == "wa" else "Telegram"
    flag = flag_of(country)
    return (
        f"\U0001F9FE <b>Confirm Your Order</b>\n"
        f"{DIV}\n"
        f"\U0001F4F2 Type: {label}\n"
        f"\U0001F30D Country: {flag} {country}\n"
        f"\U0001F4B5 Price: <code>${rate:.2f}</code>\n"
        f"\U0001F4B0 Your Balance: <code>${balance:.2f}</code>\n"
        f"{DIV}\n"
        f"\U0001F449 All good? Confirm below"
    )


def purchase_success_text(number: str, label: str, country: str,
                          rate: float, order_id: str,
                          otp_url: str = "") -> str:
    flag = flag_of(country)
    link_line = ""
    if (otp_url or "").strip():
        link_line = (
            f"\U0001F517 OTP link: <a href=\"{html_escape((otp_url or '').strip())}\">"
            "open the number's SMS inbox</a>\n")
    return (
        f"\u2705 <b>Purchase Complete!</b>\n"
        f"{DIV}\n"
        f"\U0001F4F1 Number: <code>{html_escape(number)}</code>\n"
        f"\U0001F3F7\uFE0F {label} \u2022 {flag} {country}\n"
        f"\U0001F4B5 Paid: <code>${rate:.2f}</code>\n"
        f"\U0001F9FE Order: <code>{order_id}</code>\n"
        f"{DIV}\n"
        f"{link_line}"
        f"\U0001F4E9 Tap <b>Get OTP</b> below anytime to fetch your code\n"
        f"\U0001F4CB Tap the number to copy it"
    )


def insufficient_text(rate: float, bal: float, need: float) -> str:
    return (
        f"\u26A0\uFE0F <b>Not Enough Balance</b>\n"
        f"{DIV}\n"
        f"\U0001F4B5 Price: <code>${rate:.2f}</code>\n"
        f"\U0001F4B0 Balance: <code>${bal:.2f}</code>\n"
        f"\u2757 You need: <code>${need:.2f}</code> more\n"
        f"{DIV}\n"
        f"\U0001F449 Top up in one tap"
    )


def out_of_stock_text(label: str, country: str) -> str:
    flag = flag_of(country)
    return (
        f"\u274C <b>Out of Stock</b>\n"
        f"{DIV}\n"
        f"\U0001F3F7\uFE0F {label} \u2014 {flag} {country}\n"
        f"{DIV}\n"
        f"\U0001F449 Try another country, or ping \U0001F4AC Support"
    )


async def deposit_intro_text() -> str:
    min_dep = float(await get_setting("min_deposit"))
    return (
        "\U0001F4B3 <b>Deposit</b>\n"
        f"{DIV}\n"
        f"\U0001F4B5 Min: <code>${min_dep:.2f}</code> \u2022 "
        "bKash / Nagad / Binance\n"
        f"{DIV}\n"
        "\U0001F449 Pick your payment method - pay - upload the "
        "screenshot. Done!"
    )


async def payment_account(method: str) -> str:
    meta = PAYMENT_METHODS.get(method) or PAYMENT_METHODS["bkash"]
    return ((await get_setting(meta["key"])) or "").strip() or \
        "not set \u2014 contact support"


def screenshot_prompt_text(dep_id: str, method: str) -> str:
    meta = PAYMENT_METHODS.get(method) or PAYMENT_METHODS["bkash"]
    return (
        f"\U0001F4F8 <b>Send Your Payment Screenshot</b>\n"
        f"{DIV}\n"
        f"\U0001F4B3 Method: <b>{meta['label']}</b>\n"
        "\U0001F4CB Send the screenshot of your successful payment "
        "as a <b>photo</b> here.\n"
        f"{DIV}\n"
        "\u2705 Admin verifies \u2192 balance credited\n"
        f"\U0001F9FE <code>{dep_id}</code>"
    )


def payment_card_text(method: str, account: str,
                      deposit_id: str, expires: str) -> str:
    meta = PAYMENT_METHODS.get(method) or PAYMENT_METHODS["bkash"]
    return (
        f"\U0001F4B8 <b>Pay via {meta['label']}</b>\n"
        f"\U0001F4B3 Method: <b>{meta['label']}</b> \u2014 {meta['hint']}\n"
        f"{DIV}\n"
        f"\U0001F4CD {meta['label']} number (tap to copy):\n"
        f"<code>{html_escape(account)}</code>\n"
        f"{DIV}\n"
        "\u2705 Paid? Send the screenshot of your payment here as a "
        "<b>photo</b>.\n"
        "\u23F3 Admin verifies it and credits your balance.\n"
        f"\U0001F9FE <code>{deposit_id}</code> \u2022 expires {expires} \u23F3"
    )


def deposit_history_text(rows) -> str:
    if not rows:
        return (
            f"\U0001F4DC <b>Deposit History</b>\n"
            f"{DIV}\n"
            f"No deposits yet \u2014 your first one will show up here.\n"
            f"{DIV}"
        )
    lines = [
        f"\U0001F4DC <b>Deposit History</b>\n{DIV}"
    ]
    for r in rows[:10]:
        st = {"pending": "\u23F3", "confirmed": "\u2705",
              "rejected": "\u274C", "cancelled": "\u26D4"}.get(r["status"], "\u23F3")
        lines.append(f"{st} <code>{r['deposit_id']}</code> \u2014 ${r['amount']:.2f}")
    lines.append(DIV)
    return "\n".join(lines)

# --------------------------------------------------------------------------- #
#  SCREEN RENDERERS
#  Every screen: (1) sets the user state  ->  state memory / phone-back fix
#                (2) sends message + BOTTOM reply keyboard
# --------------------------------------------------------------------------- #
async def show_main_menu(update, context):
    await clear_user_state(update.effective_user.id)
    await _send_tracked(update, context,
                        menu_info_text(), main_menu_kb(is_admin(update.effective_user.id)))


async def show_profile(update, context):
    uid = update.effective_user.id
    await clear_user_state(uid)
    u = await get_or_create_user(uid)
    await _send_tracked(update, context, profile_text(u), home_only_kb())


async def show_support(update, context):
    await clear_user_state(update.effective_user.id)
    await _send_tracked(update, context, support_text(), home_only_kb())


async def show_buy_type(update, context):
    await set_user_state(update.effective_user.id, "buy_type")
    await _send_tracked(update, context, await buy_intro_text(), buy_type_kb())


async def show_buy_country(update, context, ntype):
    await set_user_state(update.effective_user.id, "buy_country", {"ntype": ntype})
    await _send_tracked(update, context, buy_country_text(ntype), country_kb("buy", ntype))


async def show_buy_confirm(update, context, ntype, country):
    uid = update.effective_user.id
    user = await get_user(uid)
    bal = (user or {}).get("balance", 0.0) or 0.0
    rate = float(await get_setting("whatsapp_rate" if ntype == "wa" else "telegram_rate"))
    await set_user_state(uid, "buy_confirm", {"ntype": ntype, "country": country})
    await _send_tracked(update, context,
                        await buy_confirm_text(ntype, country, bal),
                        buy_confirm_kb(rate, ntype, country))


async def show_dep_menu(update, context):
    await set_user_state(update.effective_user.id, "dep_menu")
    await _send_tracked(update, context, await deposit_intro_text(), deposit_menu_kb())


async def show_dep_amount(update, context):
    """v9.15: amount picking removed - straight to payment methods."""
    return await show_dep_methods(update, context)


async def show_dep_methods(update, context, amount=None):
    """v9.15: Deposit \u2192 payment method (NO amount picking \u2014 the
    admin reads the real amount from the screenshot)."""
    await set_user_state(update.effective_user.id, "dep_method")
    min_dep = float(await get_setting("min_deposit"))
    await _send_tracked(update, context,
                        "\U0001F4B3 <b>Select Payment Method</b>\n"
                        f"{DIV}\n"
                        f"\U0001F4B5 Min: <code>${min_dep:.2f}</code>\n"
                        f"{DIV}\n"
                        "\U0001F449 Tap your payment method",
                        deposit_method_kb())


async def show_dep_history(update, context):
    uid = update.effective_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM deposits WHERE user_id=? ORDER BY id DESC LIMIT 10", (uid,)
        )
        rows = await cur.fetchall()
        await cur.close()
    # Back from history returns to the deposit menu
    await set_user_state(uid, "dep_hist")
    await _send_tracked(update, context, deposit_history_text(rows), back_only_kb())


async def show_admin_panel(update, context):
    await clear_user_state(update.effective_user.id)
    s = await get_statistics()
    txt = (
        f"\U0001F6E0\uFE0F <b>ADMIN PANEL</b>\n\n"
        f"{DIV}\n"
        f"\U0001F465 {s['users']} users \u2022 \U0001F4E6 {s['available']} stock\n"
        f"\u23F3 {s['pending_deposits']} pending deposits\n"
        f"{DIV}\n\n"
        f"\U0001F447 <b>Select an action</b>"
    )
    await _send_tracked(update, context, txt, admin_panel_kb())


async def show_admin_add_type(update, context):
    await set_user_state(update.effective_user.id, "admin_add_type")
    await _send_tracked(update, context,
                        "\U0001F4E6 <b>ADD STOCK</b>\n\n"
                        f"{DIV}\n\U0001F447 <b>Select number type</b>",
                        admin_add_type_kb())


async def show_admin_add_country(update, context, ntype):
    await set_user_state(update.effective_user.id, "admin_add_country", {"ntype": ntype})
    label = "WhatsApp" if ntype == "wa" else "Telegram"
    await _send_tracked(update, context,
                        f"\U0001F4E6 <b>ADD {label.upper()} STOCK</b>\n\n"
                        f"{DIV}\n\U0001F447 <b>Select country</b>",
                        country_kb("adstc", ntype))


async def prompt_admin_add_phone(update, context, ntype, country):
    await set_user_state(update.effective_user.id, "admin_add_phone",
                         {"ntype": ntype, "country": country})
    label = "WhatsApp" if ntype == "wa" else "Telegram"
    await _send_tracked(update, context,
                        f"\U0001F4E6 <b>ADD {label.upper()} STOCK \u2014 "
                        f"{flag_of(country)} {country}</b>\n\n"
                        + stock_format_hint(),
                        admin_input_kb())



async def show_admin_set_rate(update, context):
    wa = await get_setting("whatsapp_rate")
    tg = await get_setting("telegram_rate")
    await set_user_state(update.effective_user.id, "admin_set_rate_pick")
    await _send_tracked(update, context,
                        f"\u2699\uFE0F <b>SET RATE</b>\n\n"
                        f"{DIV}\n\U0001F447 <b>Select which rate to change</b>",
                        admin_rate_pick_kb(wa, tg))


async def prompt_admin_set_rate(update, context, ntype):
    label = "WhatsApp" if ntype == "wa" else "Telegram"
    await set_user_state(update.effective_user.id, "admin_set_rate", {"ntype": ntype})
    await _send_tracked(update, context,
                        f"\u2699\uFE0F <b>SET {label.upper()} RATE</b>\n\n"
                        f"{DIV}\n\U0001F4B0 <b>Send new price</b> <i>(e.g. 2.50)</i>",
                        admin_input_kb())


async def show_admin_ban_pick(update, context):
    await set_user_state(update.effective_user.id, "admin_ban_pick")
    await _send_tracked(update, context,
                        f"\U0001F512 <b>BAN / UNBAN</b>\n\n"
                        f"{DIV}\n\U0001F447 <b>Select action</b>",
                        admin_ban_pick_kb())


async def prompt_admin_ban(update, context, action):
    await set_user_state(update.effective_user.id, "admin_ban", {"action": action})
    label = "BAN" if action == "ban" else "UNBAN"
    await _send_tracked(update, context,
                        f"\U0001F512 <b>{label} USER</b>\n\n"
                        f"{DIV}\n\U0001F194 <b>Send the Telegram user ID</b>",
                        admin_input_kb())


async def show_admin_modify_user(update, context):
    await set_user_state(update.effective_user.id, "admin_modify_user")
    await _send_tracked(update, context,
                        "\u270f\ufe0f <b>MODIFY USER</b>\n\n"
                        f"{DIV}\n\U0001F194 <b>Send the user's chat ID</b>\n"
                        f"<i>e.g. 8105697199</i>",
                        admin_input_kb())


def admin_user_kb(target: int) -> InlineKeyboardMarkup:
    return _ikb(
        [
            [InlineKeyboardButton("\U0001F4B5 Modify Balance",
                                  callback_data=f"admuser:bal:{target}",
                                  style=KeyboardButtonStyle.SUCCESS)],
            [InlineKeyboardButton("\U0001F4E9 OTP History",
                                  callback_data=f"admuser:otp:{target}",
                                  style=KeyboardButtonStyle.PRIMARY)],
            [InlineKeyboardButton("\u2B05\uFE0F Admin Panel",
                                  callback_data="admuser:back",
                                  style=KeyboardButtonStyle.DANGER)],
        ]
    )


async def admin_user_details(update, context, target, note=None):
    """Full user card for the admin: balance, purchases, OTPs, orders..."""
    u = await get_user(target)
    if not u:
        await _send_tracked(update, context,
                            "\u26a0\ufe0f <b>User not found.</b> "
                            "Send another chat ID:",
                            admin_input_kb())
        return
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT COUNT(*) AS c, COALESCE(SUM(total_amount),0) AS s "
            "FROM orders WHERE user_id=?", (target,))
        o = await cur.fetchone()
        await cur.close()
    uname = f"@{u['username']}" if u.get("username") else "\u2014"
    name = html_escape(u.get("first_name") or "\u2014")
    banned = "\U0001F6AB YES" if u.get("is_banned") else "\u2705 No"
    is_adm = "\U0001F451 YES" if u.get("is_admin") else "\u274c No"
    txt = (
        "\u270f\ufe0f <b>USER DETAILS</b>\n\n"
        f"{DIV}\n"
        f"\U0001F464 <b>Name:</b> {name}\n"
        f"\U0001F465 <b>Username:</b> {uname}\n"
        f"\U0001F194 <b>Chat ID:</b> <code>{target}</code>\n"
        f"{DIV}\n"
        f"\U0001F4B0 <b>Balance:</b> ${u.get('balance', 0.0) or 0.0:.2f}\n"
        f"\U0001F4B5 <b>Total Deposit:</b> ${u.get('total_deposit', 0.0) or 0.0:.2f}\n"
        f"\U0001F4B8 <b>Total Spent:</b> ${u.get('total_spent', 0.0) or 0.0:.2f}\n"
        f"{DIV}\n"
        f"\U0001F6D2 <b>Numbers Bought:</b> {u.get('total_purchased', 0) or 0}\n"
        f"\U0001F4E9 <b>OTPs Received:</b> {u.get('total_otp', 0) or 0}\n"
        f"\U0001F9FE <b>Orders:</b> {o['c']} (${o['s']:.2f})\n"
        f"{DIV}\n"
        f"\U0001F6AB <b>Banned:</b> {banned}\n"
        f"\U0001F451 <b>Admin:</b> {is_adm}\n"
        f"\U0001F4C5 <b>Joined:</b> {u.get('created_at', '?')}\n"
        f"{DIV}\n\n"
        f"\U0001F447 <b>Use the button on the card</b>"
    )
    if note:
        txt = f"{note}\n\n{txt}"
    await set_user_state(update.effective_user.id, "admin_user_view",
                         {"target": target})
    await _send_tracked(update, context, txt, admin_user_kb(target))


async def prompt_admin_modbal(update, context, target):
    u = await get_user(target)
    cur_bal = (u or {}).get("balance", 0.0) or 0.0
    await set_user_state(update.effective_user.id, "admin_modbal",
                         {"target": target})
    await _send_tracked(update, context,
                        "\U0001F4B5 <b>MODIFY BALANCE</b>\n\n"
                        f"{DIV}\n"
                        f"\U0001F464 <b>User:</b> <code>{target}</code>\n"
                        f"\U0001F4B0 <b>Current:</b> ${cur_bal:.2f}\n"
                        f"{DIV}\n\n"
                        f"\U0001F449 <b>Send the new balance:</b>\n"
                        f"\u2022 <code>10.50</code> \u2014 set exactly\n"
                        f"\u2022 <code>+5</code> \u2014 add $5\n"
                        f"\u2022 <code>-2</code> \u2014 deduct $2",
                        admin_input_kb())


async def show_admin_broadcast(update, context):
    await set_user_state(update.effective_user.id, "admin_broadcast")
    await _send_tracked(update, context,
                        f"\U0001F4E3 <b>BROADCAST</b>\n\n"
                        f"{DIV}\n\U0001F449 <b>Send the message to broadcast</b>\n"
                        f"<i>HTML tags allowed (&lt;b&gt;, &lt;i&gt; ...)</i>",
                        admin_input_kb())


async def show_admin_set_pay(update, context):
    b = await get_setting("bkash_number")
    n = await get_setting("nagad_number")
    bi = await get_setting("binance_id")
    await set_user_state(update.effective_user.id, "admin_set_pay")
    await _send_tracked(update, context,
                        f"\U0001F4B3 <b>PAYMENT INFO</b>\n\n"
                        f"{DIV}\n"
                        f"\U0001F7E6 bKash:\n<code>{html_escape(b or '-')}</code>\n\n"
                        f"\U0001F7E4 Nagad:\n<code>{html_escape(n or '-')}</code>\n\n"
                        f"\U0001F7E2 Binance Pay ID:\n<code>{html_escape(bi or '-')}</code>\n"
                        f"{DIV}\n\n"
                        f"\U0001F449 <b>Send:</b>\n"
                        f"<code>bkash 01712345678</code>\n"
                        f"<code>nagad 01812345678</code>\n"
                        f"<code>binance 123456789</code>",
                        admin_input_kb())


# --------------------------------------------------------------------------- #
#  BACK NAVIGATION  (smart Back: knows which screen you came from)
# --------------------------------------------------------------------------- #
async def go_back(update, context, state, sdata):
    d = sdata or {}
    if state == "buy_confirm":
        return await show_buy_country(update, context, d.get("ntype", "wa"))
    if state == "buy_country":
        return await show_buy_type(update, context)
    if state in ("dep_amount", "dep_custom"):
        return await show_dep_menu(update, context)
    if state == "dep_method":
        return await show_dep_amount(update, context)
    if state == "awaiting_screenshot":
        return await show_dep_menu(update, context)
    if state == "search_otp":
        return await show_main_menu(update, context)
    if state == "dep_hist":
        return await show_dep_menu(update, context)
    if state == "admin_add_country":
        return await show_admin_add_type(update, context)
    if state == "admin_set_rate":
        return await show_admin_set_rate(update, context)
    if state == "admin_ban":
        return await show_admin_ban_pick(update, context)
    if state == "admin_admins":
        return await show_admin_panel(update, context)
    if state in ("admin_add_admin", "admin_remove_admin"):
        return await show_admin_admins(update, context)
    if state in ("admin_add_type", "admin_add_phone", "admin_add_url",
                 "admin_set_rate_pick", "admin_ban_pick",
                 "admin_broadcast", "admin_set_pay",
                 "admin_modify_user", "admin_modbal", "admin_user_view",
                 "admin_approve_amount", "admin_otp_stats"):
        return await show_admin_panel(update, context)
    # buy_type / dep_menu / awaiting_tx / admin_panel / None / unknown
    return await show_main_menu(update, context)


async def reshow_state(update, context, state, sdata):
    """Re-render the CURRENT screen (keyboard re-sync when unexpected text arrives)."""
    d = sdata or {}
    if state == "buy_type":
        return await show_buy_type(update, context)
    if state == "buy_country":
        return await show_buy_country(update, context, d.get("ntype", "wa"))
    if state == "buy_confirm":
        return await show_buy_confirm(update, context, d.get("ntype", "wa"), d.get("country"))
    if state == "dep_menu":
        return await show_dep_menu(update, context)
    if state == "dep_hist":
        return await show_dep_history(update, context)
    if state == "search_otp":
        return await show_search_otp(update, context)
    if state == "awaiting_screenshot":
        return await show_dep_menu(update, context)
    if state == "dep_amount":
        return await show_dep_amount(update, context)
    if state == "admin_add_type":
        return await show_admin_add_type(update, context)
    if state == "admin_add_country":
        return await show_admin_add_country(update, context, d.get("ntype", "wa"))
    if state == "admin_set_rate_pick":
        return await show_admin_set_rate(update, context)
    if state == "admin_ban_pick":
        return await show_admin_ban_pick(update, context)
    if state == "admin_modify_user":
        return await show_admin_modify_user(update, context)
    if state == "admin_modbal":
        return await prompt_admin_modbal(update, context, (d or {}).get("target"))
    if state == "admin_user_view":
        return await admin_user_details(update, context, (d or {}).get("target"))
    if state == "dep_custom":
        return await prompt_custom_amount(update, context,
                                          update.effective_user.id)
    return await show_main_menu(update, context)


# --------------------------------------------------------------------------- #
#  SEARCH OTP  (user checks: OTP aya hai ya nahi on his purchased number)
# --------------------------------------------------------------------------- #
async def show_search_otp(update, context):
    uid = update.effective_user.id
    await set_user_state(uid, "search_otp")
    await _send_tracked(update, context,
                        f"\U0001F50D <b>Search OTP</b>\n"
                        f"{DIV}\n"
                        "\U0001F4F1 Send the <b>phone number</b> you purchased\n"
                        "The bot will check whether the OTP has arrived\n"
                        f"{DIV}",
                        back_only_kb())


async def handle_search_otp(update, context, uid, text):
    digits = re.sub(r"\D", "", text)
    if len(digits) < 7:
        await _send_tracked(update, context,
                            "\u274C <b>Invalid number.</b> Send the full "
                            "number (as shown on your receipt):",
                            back_only_kb())
        return
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM stock WHERE phone_number LIKE ? ORDER BY id DESC",
            (f"%{digits}%",))
        rows = [dict(r) for r in await cur.fetchall()]
        await cur.close()
    mine = [r for r in rows if r.get("sold_to") == uid]
    if not rows:
        await _send_tracked(update, context,
                            "\u274C <b>Number not found.</b>\n"
                            f"{DIV}\n"
                            f"\U0001F4F1 <code>{html_escape(text[:32])}</code>\n"
                            f"{DIV}\n"
                            "\u2139\uFE0F Only numbers purchased from this "
                            "bot can be checked.",
                            back_only_kb())
        return
    if not mine:
        await _send_tracked(update, context,
                            "\u274C <b>Not your number.</b>\n"
                            f"{DIV}\n"
                            "This number belongs to another user \u2014 you "
                            "can only check numbers you purchased yourself.",
                            back_only_kb())
        return
    stock = mine[0]
    phone = stock["phone_number"]
    if stock.get("otp_blocked") or stock.get("refund_state") in (
            "requested", "approved"):
        await _send_tracked(update, context,
                            f"\U0001F512 <b>OTP Blocked</b>\n"
                            f"{DIV}\n"
                            f"\U0001F7E2 <code>{html_escape(phone)}</code>\n"
                            f"{DIV}\n"
                            "This number was refunded \u2014 OTP can never "
                            "arrive here again.",
                            back_only_kb())
        return
    if stock.get("otp_code") and stock.get("otp_status") == "used":
        await _send_tracked(update, context,
                            f"\U0001F389 <b>OTP Received!</b>\n"
                            f"{DIV}\n"
                            f"\U0001F7E2 <code>{html_escape(phone)}</code>\n"
                            f"\u2705 <code>{html_escape(stock['otp_code'])}</code>",
                            back_only_kb())
        return
    # live probe on the number's OTP API
    await context.bot.send_chat_action(chat_id=uid, action=ChatAction.TYPING)
    status, code = await check_live_otp((stock.get("otp_url") or "").strip())
    if status == "otp":
        await update_otp_for_stock(stock["id"], code)
        await increment_otp_count(uid)
        await _send_tracked(update, context,
                            f"\U0001F389 <b>OTP Received!</b>\n"
                            f"{DIV}\n"
                            f"\U0001F7E2 <code>{html_escape(phone)}</code>\n"
                            f"\u2705 <code>{html_escape(str(code))}</code>",
                            back_only_kb())
    elif status == "waiting":
        await _send_tracked(update, context,
                            f"\u23F3 <b>No OTP Yet</b>\n"
                            f"{DIV}\n"
                            f"\U0001F7E2 <code>{html_escape(phone)}</code>\n"
                            f"{DIV}\n"
                            "The OTP has <b>not arrived</b> on this number yet.\n"
                            "SMS delays happen \u2014 search again in a while.",
                            back_only_kb())
    else:
        _url = (stock.get("otp_url") or "").strip()
        if not _url:
            await _send_tracked(update, context,
                                f"\u26A0\uFE0F <b>OTP Check Unavailable</b>\n"
                                f"{DIV}\n"
                                f"\U0001F7E2 <code>{html_escape(phone)}</code>\n"
                                f"{DIV}\n"
                                "This number has no OTP-monitoring link attached,\n"
                                f"so the bot cannot check it. Contact {SUPPORT_USERNAME} "
                                "for help.",
                                back_only_kb())
            return
        await _send_tracked(update, context,
                            f"\u26A0\uFE0F <b>Check Failed</b>\n"
                            f"{DIV}\n"
                            f"\U0001F7E2 <code>{html_escape(phone)}</code>\n"
                            f"{DIV}\n"
                            "The OTP server was busy \u2014 please search "
                            "again in a little while.",
                            back_only_kb())


# --------------------------------------------------------------------------- #
#  ADMIN OTP STATS  (per-user OTP history, searchable by TG ID)
# --------------------------------------------------------------------------- #
async def show_admin_otp_stats(update, context):
    await set_user_state(update.effective_user.id, "admin_otp_stats")
    await _send_tracked(update, context,
                        f"\U0001F4E9 <b>OTP STATS</b>\n"
                        f"{DIV}\n"
                        "\U0001F194 Send the <b>Telegram user ID</b> to see "
                        "their full OTP history",
                        admin_input_kb())


async def render_otp_history(update, context, target):
    u = await get_user(target)
    if not u:
        await _send_tracked(update, context,
                            "\u26a0\ufe0f <b>User not found.</b> Send another "
                            "chat ID:",
                            admin_input_kb())
        return
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM stock WHERE sold_to=? ORDER BY id DESC", (target,))
        rows = [dict(r) for r in await cur.fetchall()]
        await cur.close()
    received = [r for r in rows
                if r.get("otp_code") and r.get("otp_status") == "used"]
    n_recv, n_not = len(received), len(rows) - len(received)
    uname = f"@{u['username']}" if u.get("username") else "\u2014"
    lines = [
        "\U0001F4E9 <b>OTP HISTORY</b>\n",
        f"{DIV}",
        f"\U0001F464 <b>User:</b> {html_escape(u.get('first_name') or '?')} {uname}",
        f"\U0001F194 <b>ID:</b> <code>{target}</code>",
        f"{DIV}",
        f"\U0001F6D2 <b>Numbers bought:</b> {len(rows)}",
        f"\u2705 <b>OTP received:</b> {n_recv}",
        f"\u274C <b>OTP not received:</b> {n_not}",
        f"{DIV}",
    ]
    for r in rows[:40]:
        got = bool(r.get("otp_code") and r.get("otp_status") == "used")
        if r.get("otp_blocked") or r.get("refund_state") in (
                "requested", "approved"):
            icon = "\U0001F512"
        elif got:
            icon = "\u2705"
        else:
            icon = "\u274C"
        code = html_escape(r.get("otp_code")) if got else "\u2014"
        lines.append(f"{icon} <code>{html_escape(r['phone_number'])}</code> "
                     f"\u2014 {code}")
    if len(rows) > 40:
        lines.append(f"\n<i>...and {len(rows) - 40} more</i>")
    lines.append(DIV)
    await set_user_state(update.effective_user.id, "admin_otp_stats")
    await _send_tracked(update, context, "\n".join(lines), admin_input_kb())


# --------------------------------------------------------------------------- #
#  MANUAL DEPOSIT SCREENSHOT FLOW
# --------------------------------------------------------------------------- #
async def process_deposit_screenshot(update, context, uid, sdata, file_id):
    """v9.15: user sent the payment screenshot -> forward to EVERY admin."""
    dep_id = sdata.get("deposit_id")
    dep = await get_deposit(dep_id) if dep_id else None
    if not dep or dep.get("status") != "pending":
        await clear_user_state(uid)
        await _send_tracked(update, context,
                            "\u2139\uFE0F No active deposit order.\n"
                            "Start a fresh deposit from the menu.",
                            main_menu_kb(is_admin(uid)))
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE deposits SET screenshot_file_id=?, screenshot_chat_id=?, "
            "screenshot_msg_id=? WHERE deposit_id=?",
            (file_id, update.message.chat_id, update.message.message_id,
             dep_id),
        )
        await db.commit()
    meta = PAYMENT_METHODS.get(dep.get("network")) or PAYMENT_METHODS["bkash"]
    u = await get_user(uid)
    uname = f"@{u['username']}" if u and u.get("username") else "\u2014"
    caption = (
        "\U0001F4F8 <b>PAYMENT SCREENSHOT</b>\n\n"
        f"{DIV}\n"
        f"\U0001F464 <b>User:</b> "
        f"{html_escape((u or {}).get('first_name') or '?')} {uname}\n"
        f"\U0001F194 <b>ID:</b> <code>{uid}</code>\n"
        f"\U0001F4B3 <b>Method:</b> {meta['label']}\n"
        "\U0001F4B5 <b>Amount:</b> <i>read from the screenshot</i>\n"
        f"\U0001F9FE <b>Order:</b> <code>{dep_id}</code>\n"
        f"{DIV}"
    )
    # v9.15: forward to EVERY admin; remember the admin copies for cleanup
    admin_msg_ids = []
    for aid in sorted(ADMIN_IDS):
        try:
            m = await context.bot.send_photo(
                chat_id=aid, photo=file_id, caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=admin_deposit_approve_kb(dep_id))
            admin_msg_ids.append((aid, m.message_id))
        except Exception as e:
            logger.warning("screenshot forward to admin %s failed: %s",
                           aid, e)
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE deposits SET admin_msg_ids=? WHERE deposit_id=?",
                (json.dumps(admin_msg_ids), dep_id))
            await db.commit()
    except Exception as e:
        logger.warning("admin_msg_ids save failed: %s", e)
    await clear_user_state(uid)
    await _send_tracked(update, context,
                        "\u2705 <b>Screenshot Received!</b>\n"
                        f"{DIV}\n"
                        f"\U0001F9FE Order: <code>{dep_id}</code>\n"
                        "\u23F3 The admin will verify it \u2014 your balance "
                        "will be added once approved.\n"
                        f"{DIV}",
                        main_menu_kb(is_admin(uid)))

async def handle_admin_approve_amount(update, context, uid, d, text):
    """v9.15: admin typed the real amount -> credit, notify, then DELETE
    the screenshot messages (user chat + every admin chat) with the SS."""
    dep_id = d.get("deposit_id")
    raw = text.strip().replace("$", "").replace(",", "")
    try:
        amount = float(raw)
        if amount <= 0 or amount > 10000:
            raise ValueError
    except ValueError:
        await _send_tracked(update, context,
                            "\u274c <b>Invalid amount.</b> e.g. <code>5.00</code>:",
                            admin_input_kb())
        return
    dep = await confirm_deposit(dep_id, uid, credit_amount=amount)
    if not dep:
        await clear_user_state(uid)
        await _send_tracked(update, context,
                            "\u26a0\ufe0f Deposit already processed or not found.",
                            admin_panel_kb())
        return
    target = dep["user_id"]
    try:
        await context.bot.send_message(
            chat_id=target,
            text=("\u2705 <b>DEPOSIT CONFIRMED</b>\n\n"
                  f"{DIV}\n"
                  f"\U0001F4B5 <b>Amount:</b> ${amount:.2f}\n"
                  f"\U0001F9FE <b>Order:</b> <code>{dep_id}</code>\n"
                  f"{DIV}\n\n"
                  "\U0001F4B0 <b>Balance updated! Happy shopping \U0001F6D2</b>"),
            parse_mode=ParseMode.HTML)
    except Exception:
        pass
    # 1) delete the screenshot from the user's bot chat
    try:
        if dep.get("screenshot_chat_id") and dep.get("screenshot_msg_id"):
            await context.bot.delete_message(
                chat_id=dep["screenshot_chat_id"],
                message_id=dep["screenshot_msg_id"])
    except Exception as e:
        logger.warning("screenshot delete failed: %s", e)
    # v9.15 2) delete EVERY admin copy of this screenshot
    try:
        raw_ids = dep.get("admin_msg_ids")
        pairs = json.loads(raw_ids) if raw_ids else []
        for aid, mid in pairs:
            try:
                await context.bot.delete_message(chat_id=aid, message_id=mid)
            except Exception:
                pass
    except Exception as e:
        logger.warning("admin screenshot delete failed: %s", e)
    # 3) archive the screenshot to the deposit group (proof stays there)
    try:
        if dep.get("screenshot_file_id"):
            await context.bot.send_photo(
                chat_id=DEPOSIT_GROUP_ID,
                photo=dep["screenshot_file_id"],
                caption=("\u2705 <b>DEPOSIT APPROVED</b>\n\n"
                         f"\U0001F194 User: <code>{target}</code>\n"
                         f"\U0001F4B5 Amount: ${amount:.2f}\n"
                         f"\U0001F9FE Order: <code>{dep_id}</code>\n"
                         f"\U0001F464 Approved by admin <code>{uid}</code>"),
                parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.warning("screenshot group forward failed: %s", e)
    await clear_user_state(uid)
    await _send_tracked(update, context,
                        "\u2705 <b>APPROVED &amp; CREDITED</b>\n\n"
                        f"{DIV}\n"
                        f"\U0001F194 User: <code>{target}</code>\n"
                        f"\U0001F4B5 Amount: ${amount:.2f}\n"
                        f"\U0001F9FE Order: <code>{dep_id}</code>\n"
                        "\U0001F4F8 Screenshot archived \u2014 chats cleaned\n"
                        f"{DIV}",
                        admin_panel_kb())

# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
#  COMMAND HANDLERS
# --------------------------------------------------------------------------- #
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    rec = await get_or_create_user(user.id, user.username, user.first_name)
    if rec.get("is_banned"):
        await update.message.reply_text("\U0001F512 <b>Access blocked</b>\nThis account can't use the " "bot anymore.")
        return
    await _send_tracked(update, context,
                        await welcome_text(user.first_name, rec),
                        main_menu_kb(is_admin(user.id)))


async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_main_menu(update, context)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        f"\U0001F4D6 <b>Quick Help</b>\n"
        f"{DIV}\n"
        f"/start \u2014 open main menu\n"
        f"/menu \u2014 show main menu\n"
        f"/admin \u2014 admin panel\n"
        f"{DIV}\n"
        f"\U0001F4A1 Everything\'s just a tap away on the buttons below."
    )
    await _send_tracked(update, context, txt,
                        main_menu_kb(is_admin(update.effective_user.id)))


def _mask_addr(a: str) -> str:
    """Short form for logs: 0x72b0f558a3...e43B8"""
    a = (a or "").strip()
    return "%s\u2026%s" % (a[:12], a[-6:]) if len(a) > 20 else (a or "-")


async def trace_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /trace [DEPID] - full deposit audit trail."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("\U0001F6AB Admins only.")
        return
    arg = ((context.args or [""])[0] or "").strip().upper()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if arg:
            cur = await db.execute(
                "SELECT * FROM deposit_trace WHERE deposit_id=? "
                "ORDER BY id", (arg,))
            head = f"\U0001F50D <b>TRACE {html_escape(arg)}</b>"
        else:
            cur = await db.execute(
                "SELECT * FROM deposit_trace ORDER BY id DESC LIMIT 25")
            head = "\U0001F50D <b>DEPOSIT TRACE</b> \u2014 last 25"
        rows = await cur.fetchall()
        await cur.close()
    if not rows:
        await update.message.reply_text(head + "\n\nNo events yet.",
                                        parse_mode=ParseMode.HTML)
        return
    icon = {"credited": "\u2705", "order_created": "\U0001F195",
            "amount_mismatch": "\u274C", "txid_replay": "\U0001F501",
            "locked": "\U0001F512", "wallet_changed": "\U0001F511",
            "wallet_rotated": "\U0001F504"}
    lines = [head, DIV]
    for r in rows:
        d = dict(r)
        t = time.strftime("%d %b %H:%M UTC", time.gmtime(d.get("ts") or 0))
        ev = d.get("event") or "?"
        lines.append(
            f"{icon.get(ev, chr(8226))} <code>{d.get('deposit_id')}</code> "
            f"{html_escape(ev)} \u2014 {t}\n"
            f"&nbsp;&nbsp;net={html_escape(str(d.get('network')))} "
            f"user=<code>{d.get('user_id')}</code>"
            + (f"\n&nbsp;&nbsp;{html_escape(d['detail'])}"
               if d.get("detail") else ""))
    await update.message.reply_text("\n".join(lines[:90]),
                                    parse_mode=ParseMode.HTML)


async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("\U0001F6AB Admins only.")
        return
    await show_admin_panel(update, context)


# --------------------------------------------------------------------------- #
#  TEXT ROUTER  (the heart of the bot)
#  Priority: 1) global buttons  2) Back  3) flow buttons  4) admin buttons
#            5) text-input states  6) unknown text -> keyboard re-sync
# --------------------------------------------------------------------------- #
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.edited_message
    if msg is None or not msg.text:
        return          # stale/queued non-text update - nothing to route
    text = msg.text.strip()
    uid = update.effective_user.id
    user = await get_user(uid)
    if user and user.get("is_banned"):
        await msg.reply_text("\U0001F512 <b>Access blocked</b>\nThis account can't use the " "bot anymore.")
        return

    state, sdata = await get_user_state(uid)
    adm = is_admin(uid)

    # ---------- 1) Global buttons: ALWAYS work (cancel any pending input) ----------
    if text == BTN_HOME:
        return await show_main_menu(update, context)
    if text == BTN_BUY:
        return await show_buy_type(update, context)
    if text == BTN_PROFILE:
        return await show_profile(update, context)
    if text == BTN_DEPOSIT:
        return await show_dep_menu(update, context)
    if text == BTN_SUPPORT:
        return await show_support(update, context)
    if text == BTN_SEARCH_OTP:
        return await show_search_otp(update, context)
    if text == BTN_ADMIN and adm:
        return await show_admin_panel(update, context)

    # ---------- 2) Back / Cancel ----------
    if text == BTN_BACK:
        return await go_back(update, context, state, sdata)

    if text == BTN_CANCEL:
        if state == "awaiting_screenshot" and \
                (sdata or {}).get("deposit_id"):
            await cancel_pending_deposit(uid, sdata["deposit_id"])
        if adm and state and state.startswith("admin"):
            return await show_admin_panel(update, context)
        return await show_main_menu(update, context)

    # ---------- 3) BUY flow ----------
    if state == "buy_type" and text in (BTN_WA, BTN_TG):
        return await show_buy_country(update, context, "wa" if text == BTN_WA else "tg")

    if state == "buy_country":
        ctry = country_from_button(text)
        if ctry:
            return await show_buy_confirm(update, context, (sdata or {}).get("ntype", "wa"), ctry)

    if state == "buy_confirm" and text.startswith("\u2705 Buy"):
        d = sdata or {}
        return await do_purchase(update, context, uid, d.get("ntype", "wa"), d.get("country"))

    # ---------- 4) DEPOSIT flow ----------
    if state == "dep_menu" and text == BTN_DEP_NEW:
        return await show_dep_amount(update, context)

    if state == "dep_menu" and text == BTN_DEP_HIST:
        return await show_dep_history(update, context)

    if text == BTN_CANCEL_DEP and state == "awaiting_screenshot":
        dep_id = (sdata or {}).get("deposit_id")
        if dep_id:
            await cancel_pending_deposit(uid, dep_id)
        await clear_user_state(uid)
        return await _send_tracked(update, context,
                                   "\u274C <b>Deposit cancelled.</b>",
                                   main_menu_kb(adm))

    # ---------- 5) ADMIN panel buttons + admin flow buttons ----------
    if adm:
        if text == BTN_ADD_STOCK:
            return await show_admin_add_type(update, context)
        if text == BTN_STOCK_STATS:
            return await admin_stock_stats(update, context)
        if text == BTN_PENDING:
            return await admin_pending_deposits(update, context)
        if text == BTN_USERS:
            return await admin_list_users(update, context)
        if text == BTN_STATS:
            return await admin_statistics(update, context)
        if text == BTN_SET_RATE:
            return await show_admin_set_rate(update, context)
        if text == BTN_BROADCAST:
            return await show_admin_broadcast(update, context)
        if text == BTN_SET_WALLET:
            return await show_admin_set_pay(update, context)
        if text == BTN_OTP_STATS:
            return await show_admin_otp_stats(update, context)
        if text == BTN_BAN:
            return await show_admin_ban_pick(update, context)
        if text == BTN_MODIFY_USER:
            return await show_admin_modify_user(update, context)
        if text == BTN_MANAGE_REFUND:
            return await show_admin_refunds(update, context)
        if text == BTN_ADMINS:
            return await show_admin_admins(update, context)
        if text == BTN_NO_OTP_FILE:
            return await send_no_otp_file(update, context)
        if text == BTN_USER_OTP_FILE:
            return await send_user_otp_report(update, context)

        if state == "admin_refund_upload":
            if text == BTN_REFUND_LIST:
                return await send_admin_refund_list(update, context)
            if text == BTN_SELLER_FILE:
                return await send_seller_input_file(update, context)
            if "http" in text:
                # pasted failed-urls list -> processed like an uploaded .txt
                await update.message.reply_text(
                    "\u23F3 <b>Matching refunds (pasted list)...</b>",
                    parse_mode=ParseMode.HTML)
                return await process_refund_file(update, context, uid, text)
            # any other text -> re-show the refund screen (stay in state)
            return await show_admin_refunds(update, context)

        if state == "admin_add_type" and text in (BTN_WA_STOCK, BTN_TG_STOCK):
            return await show_admin_add_country(
                update, context, "wa" if text == BTN_WA_STOCK else "tg")

        if state == "admin_add_country":
            ctry = country_from_button(text)
            if ctry:
                return await prompt_admin_add_phone(
                    update, context, (sdata or {}).get("ntype", "wa"), ctry)

        if state == "admin_set_rate_pick":
            if text.startswith("\U0001F7E2 WhatsApp \u2014"):
                return await prompt_admin_set_rate(update, context, "wa")
            if text.startswith("\U0001F535 Telegram \u2014"):
                return await prompt_admin_set_rate(update, context, "tg")

        if state == "admin_ban_pick" and text in (BTN_BAN_USER, BTN_UNBAN_USER):
            return await prompt_admin_ban(
                update, context, "ban" if text == BTN_BAN_USER else "unban")

    # ---------- 6) Text-input states (button taps never reach here) ----------
    if state in INPUT_STATES:
        return await handle_state_text(update, context, state, sdata, text)

    # ---------- 7) Unknown text -> re-sync keyboard for the current screen ----------
    if state:
        return await reshow_state(update, context, state, sdata)
    return await show_main_menu(update, context)

# --------------------------------------------------------------------------- #
#  BUY FLOW  (purchase)
# --------------------------------------------------------------------------- #
async def do_purchase(update, context, uid, ntype, country):
    """In-flight lock: a double-tap on Buy can never charge twice."""
    lock = f"buying:{uid}"
    if context.bot_data.get(lock):
        if update.callback_query:
            try:
                await update.callback_query.answer(
                    "Processing your purchase... \u23F3", show_alert=True)
            except Exception:
                pass
        return
    context.bot_data[lock] = True
    try:
        return await _do_purchase_impl(update, context, uid, ntype, country)
    finally:
        context.bot_data.pop(lock, None)


async def _do_purchase_impl(update, context, uid, ntype, country):
    user = await get_user(uid)
    rate = float(await get_setting("whatsapp_rate" if ntype == "wa" else "telegram_rate"))
    bal = (user or {}).get("balance", 0.0) or 0.0
    label = "WhatsApp" if ntype == "wa" else "Telegram"

    if bal < rate:
        await clear_user_state(uid)
        await _send_tracked(update, context,
                            insufficient_text(rate, bal, rate - bal),
                            insufficient_kb())
        return

    db_type = "whatsapp" if ntype == "wa" else "telegram"
    stock = await get_available_stock(db_type, country)
    if not stock:
        # Back returns to the country list so the user can pick another one
        await set_user_state(uid, "buy_country", {"ntype": ntype})
        await _send_tracked(update, context,
                            out_of_stock_text(label, country), back_home_kb())
        return

    await deduct_balance(uid, rate)
    await mark_stock_sold(stock["id"], uid)
    order_id = await create_order(uid, ntype, country, rate, [stock["phone_number"]], rate)
    await clear_user_state(uid)

    # Receipt is sent as a FRESH message — it is NEVER edited or deleted,
    # so the user can always come back to the Get OTP button later.
    receipt_txt = purchase_success_text(stock["phone_number"], label, country,
                                        rate, order_id,
                                        (stock.get("otp_url") or "").strip())
    _otp_url = (stock.get("otp_url") or "").strip()
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                receipt_txt, parse_mode=ParseMode.HTML,
                reply_markup=otp_kb(stock["id"], _otp_url),
            )
        except Exception:
            await context.bot.send_message(
                chat_id=uid, text=receipt_txt, parse_mode=ParseMode.HTML,
                reply_markup=otp_kb(stock["id"], _otp_url),
            )
    else:
        await update.message.reply_text(
            receipt_txt, parse_mode=ParseMode.HTML,
            reply_markup=otp_kb(stock["id"], _otp_url),
        )
    # Reset the BOTTOM keyboard to the main menu (fresh message — the
    # receipt above is never touched).
    await context.bot.send_message(
        chat_id=uid, text=menu_footer_text(), parse_mode=ParseMode.HTML,
        reply_markup=_kb_dedupe(context, uid,
                                main_menu_kb(is_admin(uid))),
    )

    await forward_order_history(context, uid, ntype, country, rate, stock, order_id)
    start_otp_poller(context, uid, stock)


# --------------------------------------------------------------------------- #
#  BACKGROUND OTP POLLER  (polls the number's own API for 10 minutes)
# --------------------------------------------------------------------------- #
OTP_POLL_SECONDS = 600   # 10 minutes
OTP_POLL_INTERVAL = 5    # slow lane: every 5s after the fast lane ends
OTP_FAST_INTERVAL = 2    # v9.16 fast lane: every 2s while the OTP is hot
OTP_FAST_SECONDS = 120   # v9.16 fast lane window: first 2 minutes
OTP_HTTP_TIMEOUT = 6     # v9.16 short request timeout (never stall)
REFUND_COOLDOWN_SECONDS = 300   # (admin tooling; user refund button removed v9.14.2)


async def notify_otp(context, uid, phone, code):
    """Instant OTP notification (v9.13 design):
    \U0001F389 OTP Received! / \U0001F7E2 number / \u2705 otp"""
    try:
        await context.bot.send_message(
            chat_id=uid,
            text=(
                f"\U0001F389 <b>OTP Received!</b>\n"
                f"\U0001F7E2 <code>{html_escape(str(phone))}</code>\n"
                f"\u2705 <code>{html_escape(str(code))}</code>"
            ),
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.warning("OTP notify failed user=%s: %s", uid, e)


async def poll_otp_task(context, uid, stock):
    """v9.16 SUPER INSTANT poller: fast lane (every 2s) for the first
    2 minutes - when OTPs almost always land - then every 5s for the
    rest of the 10-minute window. Baseline (old SMS) is persisted per
    stock so Get OTP and the poller agree. STRICT refund guard: the
    moment a refund is requested the poller dies and OTP can never be
    delivered for that number."""
    stock_id = stock["id"]
    phone = stock["phone_number"]
    url = (stock.get("otp_url") or "").strip()
    if not url:
        return
    saved = await get_stock_baseline(stock_id)
    baseline = set(saved) if saved else None
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    deadline = t0 + OTP_POLL_SECONDS
    try:
        async with aiohttp.ClientSession() as session:
            while loop.time() < deadline:
                st = await get_stock_item(stock_id)
                if (not st or st.get("otp_blocked")
                        or st.get("refund_state") in ("requested", "approved")
                        or st.get("otp_status") == "used"):
                    logger.info("OTP poller aborted stock=%s "
                                "(refunded/blocked/delivered)", stock_id)
                    return
                text = await fetch_sms_text(url, session, OTP_HTTP_TIMEOUT)
                codes = _otp_codes(text)
                if baseline is None:
                    baseline = set(codes)  # first response = old SMS
                    await save_stock_baseline(stock_id, codes)
                    if codes:
                        logger.info("OTP poll baseline stock=%s codes=%s",
                                    stock_id, codes)
                else:
                    fresh = [c for c in codes if c not in baseline]
                    if fresh:
                        # final strict re-check right before notifying (race guard)
                        st2 = await get_stock_item(stock_id)
                        if (st2.get("otp_blocked")
                                or st2.get("refund_state")
                                in ("requested", "approved")):
                            logger.info("OTP delivery cancelled stock=%s "
                                        "(refund in progress)", stock_id)
                            return
                        code = fresh[0]
                        await update_otp_for_stock(stock_id, code)
                        await increment_otp_count(uid)
                        await notify_otp(context, uid, phone, code)
                        logger.info("OTP DELIVERED stock=%s user=%s code=%s",
                                    stock_id, uid, code)
                        return
                # v9.16: fast lane while the OTP is hot, slow lane after
                in_fast = (loop.time() - t0) < OTP_FAST_SECONDS
                await asyncio.sleep(OTP_FAST_INTERVAL if in_fast
                                    else OTP_POLL_INTERVAL)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning("OTP poller error stock=%s: %s", stock_id, e)
        return
    # 10 minutes over - no OTP arrived
    try:
        await context.bot.send_message(
            chat_id=uid,
            text=(
                f"\u23F3 <b>No OTP After 10 Minutes</b>\n"
                f"{DIV}\n"
                f"\U0001F7E2 Your Number: "
                f"<code>{html_escape(str(phone))}</code>\n"
                f"{DIV}\n"
                "SMS delays happen. Tap \U0001F511 <b>Get OTP</b> on your "
                "receipt to check again anytime."
            ),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass

def start_otp_poller(context, uid, stock):
    """Start the 10-minute background OTP poller for a purchased number."""
    if (stock.get("otp_blocked")
            or stock.get("refund_state") in ("requested", "approved")):
        logger.info("OTP poller skipped stock=%s (refunded/blocked)",
                    stock.get("id"))
        return
    if not (stock.get("otp_url") or "").strip():
        logger.info("No OTP URL on stock %s - poller skipped", stock.get("id"))
        return
    polls = context.bot_data.setdefault("otp_polls", {})
    sid = stock["id"]
    old = polls.get(sid)
    if old and not old.done():
        return
    polls[sid] = context.application.create_task(
        poll_otp_task(context, uid, stock)
    )
    logger.info("OTP poller started stock=%s user=%s (10 min window)", sid, uid)


# --------------------------------------------------------------------------- #
#  ORDER HISTORY GROUP FORWARD
# --------------------------------------------------------------------------- #
def mask_user_id(uid: int) -> str:
    s = str(uid)
    if len(s) <= 6:
        return s
    keep = 3
    return s[:keep] + "*" * (len(s) - keep * 2) + s[-keep:]


def mask_number(number: str) -> str:
    s = number
    if len(s) <= 6:
        return s
    keep = 5
    return s[:keep] + "*" * max(len(s) - keep - 4, 1) + s[-4:]


async def get_total_bot_balance() -> float:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COALESCE(SUM(balance),0) FROM users")
        val = (await cur.fetchone())[0]
        await cur.close()
        return float(val)


async def forward_order_history(context, uid, ntype, country, rate, stock, order_id):
    """Send a formatted purchase notification to the order-history group."""
    group_id = await get_setting("order_history_group_id")
    if not group_id:
        group_id = str(ORDER_HISTORY_GROUP_ID)
    try:
        gid = int(group_id)
    except Exception:
        return
    platform = "WhatsApp" if ntype == "wa" else "Telegram"
    masked_uid = mask_user_id(uid)
    masked_num = mask_number(stock["phone_number"])
    total_bal = await get_total_bot_balance()
    now = _utcnow().strftime("%Y-%m-%d %H:%M:%S")
    text = (
        "\U0001F525 <b>New Purchase Successful!</b>\n"
        f"Platform: {platform}\n"
        f"\U0001F464 User ID: {masked_uid}\n"
        f"\U0001F4E6 Quantity: 1 pcs\n"
        f"\U0001F4B0 Price: USDT {rate:.2f}\n"
        f"\U0001F517 Number: {masked_num}\n"
        f"\U0001F194 Order ID: {order_id}\n"
        f"\U0001F4B0 Total Bot Balance: USDT {total_bal:,.2f}\n"
        f"\u23F0 Time: {now}"
    )
    try:
        await context.bot.send_message(
            chat_id=gid, text=text, parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.warning("forward_order_history failed: %s", e)


# --------------------------------------------------------------------------- #
#  OTP INLINE  (Get OTP action button on the receipt)
# --------------------------------------------------------------------------- #
async def _safe_answer(q, text=None, show_alert=False):
    """Answer a callback query without dying on stale queries.
    Proven live: a button pressed while the bot was down arrives
    "too old" after restart - the answer API rejects it, but the
    action behind the tap must STILL run."""
    try:
        await q.answer(text=text, show_alert=show_alert)
    except Exception as e:
        logger.info("callback answer skipped (%s)", str(e)[:60])


async def burst_check_otp(otp_url: str, stock_id: int,
                          tries: int = 9, gap: float = 1.5,
                          timeout: int = 6):
    """v9.16 SUPER INSTANT: check now + retry every 1.5s (one shared
    HTTP session). Returns the fresh OTP string or None.
    Baseline-aware: codes already on the number at purchase are never
    shown as new."""
    url = (otp_url or "").strip()
    if not url:
        return None
    baseline = set(await get_stock_baseline(stock_id) or [])
    loop = asyncio.get_running_loop()
    deadline = loop.time() + gap * tries
    async with aiohttp.ClientSession() as session:
        while True:
            text = await fetch_sms_text(url, session, timeout)
            codes = _otp_codes(text)
            if not baseline:
                # first successful response = old SMS baseline
                if codes:
                    await save_stock_baseline(stock_id, codes)
                    baseline = set(codes)
            else:
                fresh = [c for c in codes if c not in baseline]
                if fresh:
                    return fresh[0]
            if loop.time() >= deadline:
                return None
            await asyncio.sleep(gap)


async def otp_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("\u23F3 Fetching your OTP...")
    parts = q.data.split(":")
    try:
        stock_id = int(parts[1])
    except (IndexError, ValueError):
        await q.answer("Invalid request", show_alert=True)
        return
    uid = q.from_user.id
    stock = await get_stock_item(stock_id)
    if not stock:
        await q.answer("\u274C Number not found", show_alert=True)
        return
    if stock.get("sold_to") != uid and not is_admin(uid):
        await q.answer("\u274C Not your number", show_alert=True)
        return

    # STRICT: refunded numbers can never receive OTP again
    if stock.get("otp_blocked") or stock.get("refund_state") in (
            "requested", "approved", "rejected"):
        await q.message.reply_text(
            f"\U0001F512 <b>OTP Blocked</b>\n"
            f"{DIV}\n"
            f"\U0001F7E2 <code>{html_escape(stock['phone_number'])}</code>\n"
            f"{DIV}\n"
            f"This number was refunded \u2014 OTP can never arrive here "
            f"again.",
            parse_mode=ParseMode.HTML,
        )
        return

    if not (stock.get("otp_url") or "").strip():
        await q.answer("\u2139\uFE0F No OTP link on this number — contact "
                       "support",
                       show_alert=True)
        return

    # If already delivered -> show the SAME otp again (exact format)
    if stock.get("otp_code") and stock.get("otp_status") == "used":
        await q.message.reply_text(
            f"\U0001F389 <b>OTP Received!</b>\n"
            f"\U0001F7E2 <code>{html_escape(stock['phone_number'])}</code>\n"
            f"\u2705 <code>{html_escape(stock['otp_code'])}</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    # v9.16 SUPER INSTANT: live burst - the OTP is fetched NOW and
    # retried every 1.5s for ~13s (shared session). Most taps answer
    # instantly; the rest land the moment the provider posts the code.
    await context.bot.send_chat_action(chat_id=uid, action=ChatAction.TYPING)
    code = await burst_check_otp(stock["otp_url"], stock_id)
    if code:
        await update_otp_for_stock(stock_id, code)
        await increment_otp_count(uid)
        await q.message.reply_text(
            f"\U0001F389 <b>OTP Received!</b>\n"
            f"\U0001F7E2 <code>{html_escape(stock['phone_number'])}</code>\n"
            f"\u2705 <code>{html_escape(str(code))}</code>",
            parse_mode=ParseMode.HTML,
        )
    else:
        await q.message.reply_text(
            f"\u23F3 <b>OTP Not Arrived Yet</b>\n"
            f"{DIV}\n"
            f"\U0001F7E2 <code>{html_escape(stock['phone_number'])}</code>\n"
            f"{DIV}\n"
            "The provider hasn't posted the code yet \u2014 we checked "
            "for the last 13 seconds.\n"
            f"\U0001F4E9 Tap <b>Get OTP</b> again anytime, or open the "
            f"OTP link \U0001F517 below to see the inbox directly.\n"
            f"{DIV}",
            parse_mode=ParseMode.HTML,
            reply_markup=otp_link_kb(stock_id,
                                     (stock.get("otp_url") or "").strip()),
        )


# --------------------------------------------------------------------------- #
#  REFUND SYSTEM  (strict: 5-min cooldown, permanent OTP block, pending money,
#                  admin approves via failed-urls .txt matching)
# --------------------------------------------------------------------------- #
async def refund_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """v9.14.2: refunds are ADMIN-ONLY. The button was removed from the
    receipt; this stays only so old buttons from earlier messages answer
    politely instead of dying."""
    q = update.callback_query
    await _safe_answer(q)
    if not is_admin(q.from_user.id):
        await q.answer("Refunds are handled by the admin. Contact support.",
                       show_alert=True)
        return
    # Admin tapped an old refund button: open the refund manager instead
    await show_admin_refunds(update, context)


async def notify_refund_approved(context, r):
    try:
        await context.bot.send_message(
            chat_id=r["user_id"],
            text=(
                f"\u2705 <b>Refund Approved</b>\n"
                f"{DIV}\n"
                f"\U0001F7E2 <code>{html_escape(r['phone_number'])}</code>\n"
                f"\U0001F4B0 <code>${float(r['amount']):.2f}</code> added to "
                f"your balance\n"
                f"{DIV}\n"
                f"\U0001F464 Check it under Profile"
            ),
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.warning("Refund approve notify failed user=%s: %s",
                       r["user_id"], e)


async def notify_refund_rejected(context, r, reason=None):
    if reason == "otp_live":
        body = ("Our on-chain/live check found an OTP already delivered to "
                "this number \u2014 numbers with a received OTP can't be "
                "refunded.")
    else:
        body = "Reviewed manually \u2014 this refund wasn't approved."
    try:
        await context.bot.send_message(
            chat_id=r["user_id"],
            text=(
                f"\u274C <b>Refund Rejected</b>\n"
                f"{DIV}\n"
                f"\U0001F7E2 <code>{html_escape(r['phone_number'])}</code>\n"
                f"{DIV}\n"
                f"{body}\n"
                f"\U0001F512 OTP stays blocked for this number."
            ),
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.warning("Refund reject notify failed user=%s: %s",
                       r["user_id"], e)


async def show_admin_refunds(update, context):
    """Admin refund manager screen (state: admin_refund_upload)."""
    if not is_admin(update.effective_user.id):
        return
    uid = update.effective_user.id
    pending = await get_pending_refunds()
    approved_n = await count_refunds("approved")
    rejected_n = await count_refunds("rejected")
    lines = [
        "\U0001F4B8 <b>MANAGE REFUND</b>\n",
        DIV,
        f"\u23F3 <b>Pending:</b> {len(pending)}   "
        f"\u2705 <b>Approved:</b> {approved_n}   "
        f"\u274C <b>Rejected:</b> {rejected_n}",
        DIV,
        "",
    ]
    if pending:
        for r in pending:
            lines.append(
                f"\U0001F7E2 <code>{html_escape(r['phone_number'])}</code> \u2014 "
                f"${float(r['amount']):.2f} \u2014 user "
                f"<code>{r['user_id']}</code>"
            )
        lines.append("")
        lines.append(DIV)
        lines.append("")
    else:
        lines.append("<i>No pending refunds right now.</i>")
        lines.append("")
    lines += [
        "<b>How it works</b>",
        "1\ufe0f\u20e3 Tap <b>Refund List (.txt)</b> \u2014 you get every "
        "pending refund as <code>number | url</code>",
        "2\ufe0f\u20e3 Check each URL \u2014 did the OTP arrive? Is the number used?",
        "3\ufe0f\u20e3 Upload a <b>.txt with the FAILED urls</b> \u2014 the bot "
        "live-checks every matched URL (/api/sms/): numbers showing an "
        "OTP are <b>blocked automatically</b>, only clean ones are paid",
        "4\ufe0f\u20e3 Everything NOT matched is rejected and returned as a "
        ".txt \u2014 that money is saved",
        "5\ufe0f\u20e3 <b>Seller Input.txt</b> \u2014 approved dead numbers as "
        "supplier-format file (claim them back from your seller)",
    ]
    await set_user_state(uid, "admin_refund_upload")
    await _send_tracked(update, context, "\n".join(lines), admin_refund_kb())


async def send_admin_refund_list(update, context):
    """Send pending refunds as a phone | url .txt file."""
    if not is_admin(update.effective_user.id):
        return
    uid = update.effective_user.id
    pending = await get_pending_refunds()
    await set_user_state(uid, "admin_refund_upload")
    if not pending:
        await _send_tracked(update, context,
                            "\U0001F4C4 No pending refunds right now.\n"
                            "Upload a failed-urls .txt any time \u2014 "
                            "only matching pending refunds get approved.",
                            admin_refund_kb())
        return
    content = "\n".join(
        f"{r['phone_number']} | {r['otp_url']}" for r in pending
    )
    fname = "refund_list_%s.txt" % _utcnow().strftime("%Y%m%d_%H%M%S")
    await update.message.reply_document(
        document=content.encode("utf-8"), filename=fname,
        caption=(
            f"\U0001F4C4 <b>{len(pending)} pending refund(s)</b>\n\n"
            f"Check every URL \u2014 did the OTP arrive? Is the number used?\n"
            f"Then upload a <b>.txt of the FAILED urls</b> here \u2014 "
            f"those refunds get auto-approved and users paid."
        ),
        parse_mode=ParseMode.HTML,
    )


async def send_seller_input_file(update, context):
    """Supplier-claim export: every APPROVED (dead) refund as the
    seller's exact input.txt format: username|user_id|phone|url.
    Named input.txt so the seller's checker tool loads it directly."""
    if not is_admin(update.effective_user.id):
        return
    uid = update.effective_user.id
    await set_user_state(uid, "admin_refund_upload")
    rows = await get_refunds_by_status("approved")
    if not rows:
        await _send_tracked(
            update, context,
            "\U0001F91D <b>No dead numbers yet.</b>\n"
            "Approved refunds show up here as a supplier-format "
            "<code>input.txt</code> claim file.",
            admin_refund_kb())
        return
    admin_user = await get_user(ADMIN_ID) or {}
    uname = admin_user.get("username") or "admin"
    ident = f"{uname}|{ADMIN_ID}"
    content = "\n".join(
        f"{ident}|{r['phone_number']}|{r['otp_url']}" for r in rows
    )
    expect = len(rows) * SELLER_REFUND_RATE
    await update.message.reply_document(
        document=content.encode("utf-8"), filename="input.txt",
        caption=(
            f"\U0001F91D <b>SELLER INPUT FILE</b> \u2014 dead numbers\n\n"
            f"{DIV}\n"
            f"\U0001F7E2 Numbers: <b>{len(rows)}</b>\n"
            f"\U0001F4B0 Expected back: <b>~${expect:.2f}</b> "
            f"(${SELLER_REFUND_RATE:.2f}/number)\n"
            f"{DIV}\n\n"
            f"\U0001F4C4 Format: <code>username|user_id|number|url</code> "
            f"\u2014 named <code>input.txt</code>, the seller\u2019s "
            f"checker loads it directly.\n"
            f"\U0001F50D He will verify every URL \u2014 only no-OTP "
            f"numbers get paid."
        ),
        parse_mode=ParseMode.HTML,
    )


async def process_refund_file(update, context, admin_id, text):
    """Match uploaded failed-urls against pending refunds.
    Every matched refund passes a LIVE /api/sms/ double-check first
    (seller rule: only a pure-digit response proves an OTP exists):
      matched + no OTP seen -> approve + credit user + notify
      matched + OTP visible -> BLOCKED (rejected, no payment)
      unmatched             -> rejected + returned as .txt (money saved)."""
    wanted = {normalize_url(u) for u in URL_RE.findall(text or "") if u.strip()}
    pending = await get_pending_refunds()
    matched = [r for r in pending
               if normalize_url(r["otp_url"]) in wanted]
    rejected = [r for r in pending
                if normalize_url(r["otp_url"]) not in wanted]

    # ---- LIVE double-check before any money moves --------------------- #
    checks = await asyncio.gather(
        *(check_live_otp(r["otp_url"]) for r in matched)
    ) if matched else []
    approved, blocked = [], []
    for r, res in zip(matched, checks):
        if res and res[0] == "otp":
            blocked.append((r, res[1]))
        else:
            approved.append(r)

    total = 0.0
    for r in approved:
        await mark_refund(r["refund_id"], "approved", admin_id)
        await set_stock_refund_state(r["stock_id"], "approved",
                                     otp_blocked=True, status="refunded")
        await credit_refund_balance(r["user_id"], float(r["amount"]))
        total += float(r["amount"])
        await notify_refund_approved(context, r)
        logger.info("Refund APPROVED %s stock=%s user=%s $%s",
                    r["refund_id"], r["stock_id"], r["user_id"], r["amount"])
    blocked_saved = 0.0
    for r, code in blocked:
        await mark_refund(r["refund_id"], "rejected", admin_id)
        await set_stock_refund_state(r["stock_id"], "rejected",
                                     otp_blocked=True, status="refunded")
        blocked_saved += float(r["amount"])
        await notify_refund_rejected(context, r, reason="otp_live")
        logger.warning("Refund BLOCKED (live OTP %s) %s stock=%s user=%s",
                       code, r["refund_id"], r["stock_id"], r["user_id"])
    for r in rejected:
        await mark_refund(r["refund_id"], "rejected", admin_id)
        await set_stock_refund_state(r["stock_id"], "rejected",
                                     otp_blocked=True, status="refunded")
        await notify_refund_rejected(context, r)
        logger.info("Refund REJECTED %s stock=%s user=%s",
                    r["refund_id"], r["stock_id"], r["user_id"])
    saved = sum(float(r["amount"]) for r in rejected)
    lines = [
        "\u2705 <b>REFUND BATCH PROCESSED</b>\n",
        DIV,
        f"\U0001F50D <b>Live check:</b> {len(matched)} URL(s) via "
        f"/api/sms/",
        f"\u2705 <b>Approved:</b> {len(approved)} \u2014 "
        f"${total:.2f} credited to users",
        f"\u26D4 <b>Blocked (OTP found!):</b> {len(blocked)} \u2014 "
        f"${blocked_saved:.2f} saved",
        f"\u274C <b>Rejected (not matched):</b> {len(rejected)} \u2014 "
        f"${saved:.2f} saved",
        DIV,
    ]
    if blocked:
        lines.append("\n\u26D4 <b>OTP seen on these \u2014 NO refund:</b>")
        for r, code in blocked:
            lines.append(
                f"\U0001F7E2 <code>{html_escape(r['phone_number'])}</code> "
                f"\u2192 OTP <code>{html_escape(str(code))}</code>"
            )
        lines.append("")
    if rejected:
        content = "\n".join(
            f"{r['phone_number']} | {r['otp_url']}" for r in rejected
        )
        fname = ("refund_rejected_%s.txt"
                 % _utcnow().strftime("%Y%m%d_%H%M%S"))
        lines.append("\U0001F4C4 Not-matched refunds attached \u2014 "
                     "these users did NOT get money back.")
        await update.message.reply_text("\n".join(lines),
                                        parse_mode=ParseMode.HTML)
        await update.message.reply_document(
            document=content.encode("utf-8"), filename=fname,
            caption="\u274C <b>Rejected refunds</b> (no refund paid)",
            parse_mode=ParseMode.HTML)
    else:
        if approved and not blocked:
            lines.append("\n\U0001F389 Every matched number passed the "
                         "live check \u2014 all approved.")
        elif blocked and not approved:
            lines.append("\n\u26D4 Every matched number showed an OTP "
                         "\u2014 nothing was paid.")
        elif not matched:
            lines.append("\n\u2139\uFE0F No pending refunds to match.")
        await update.message.reply_text("\n".join(lines),
                                        parse_mode=ParseMode.HTML)
    await clear_user_state(admin_id)


# --------------------------------------------------------------------------- #
#  INLINE NAV (Main Menu button on the receipt) + fallback for old buttons
# --------------------------------------------------------------------------- #
async def nav_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inline nav: home (fresh main menu, NOTHING deleted), dep, back, close."""
    q = update.callback_query
    await _safe_answer(q)
    uid = q.from_user.id
    action = q.data.split(":")[1]
    user = await get_user(uid)
    if user and user.get("is_banned"):
        await _send_tracked(update, context, "\U0001F512 <b>Access blocked</b>\nThis account can't use the " "bot anymore.", None)
        return
    if action == "home":
        # Send a FRESH main menu — never delete or edit the current message
        await clear_user_state(uid)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=menu_info_text(),
            parse_mode=ParseMode.HTML,
            reply_markup=_kb_dedupe(context, uid,
                                    main_menu_kb(is_admin(uid))),
        )
    elif action == "dep":
        await show_dep_menu(update, context)
    elif action == "back":
        state, sdata = await get_user_state(uid)
        await go_back(update, context, state, sdata)
    elif action == "close":
        # Remove ONLY the buttons — the message text stays
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass


async def buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inline BUY flow: buy:wa|tg|ctry|do|back_type|back_ctry"""
    q = update.callback_query
    await _safe_answer(q)
    uid = q.from_user.id
    user = await get_user(uid)
    if user and user.get("is_banned"):
        await _send_tracked(update, context, "\U0001F512 <b>Access blocked</b>\nThis account can't use the " "bot anymore.", None)
        return
    parts = q.data.split(":")
    act = parts[1]
    if act in ("wa", "tg") and len(parts) == 2:
        # type button (buy:wa / buy:tg) -> country list
        return await show_buy_country(update, context, act)
    if act in ("wa", "tg") and len(parts) >= 3:
        # country button (buy:wa:USA) -> confirm screen
        return await show_buy_confirm(update, context, act, parts[2])
    if act == "ctry" and len(parts) >= 4:
        # legacy format kept for old inline buttons
        return await show_buy_confirm(update, context, parts[2], parts[3])
    if act == "do" and len(parts) >= 4:
        return await do_purchase(update, context, uid, parts[2], parts[3])
    if act == "back_type":
        return await show_buy_type(update, context)
    if act == "back_ctry" and len(parts) >= 3:
        return await show_buy_country(update, context, parts[2])


async def dep_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inline DEPOSIT flow: dep:new|hist|back|amt|custom|mth|paid|cancel"""
    q = update.callback_query
    await _safe_answer(q)
    uid = q.from_user.id
    user = await get_user(uid)
    if user and user.get("is_banned"):
        await _send_tracked(update, context, "\U0001F512 <b>Access blocked</b>\nThis account can't use the " "bot anymore.", None)
        return
    parts = q.data.split(":")
    act = parts[1]
    if act == "new":
        return await show_dep_amount(update, context)
    if act == "hist":
        return await show_dep_history(update, context)
    if act == "back":
        return await show_dep_menu(update, context)
    if act == "amt" and len(parts) >= 3:
        # v9.15: amount picking removed - straight to methods
        return await show_dep_methods(update, context)
    if act == "custom":
        return await prompt_custom_amount(update, context, uid)
    if act == "mth" and len(parts) >= 3:
        state, sdata = await get_user_state(uid)
        if state != "dep_method":
            return await _send_tracked(
                update, context,
                "\u2139\uFE0F Session expired.\n"
                "Start a fresh deposit from the menu.",
                main_menu_kb(is_admin(uid)))
        # v9.15: no amount picked - order created with amount 0,
        # the admin types the REAL amount from the screenshot
        return await deposit_create(update, context, uid, 0.0, parts[2])
    if act == "paid" and len(parts) >= 3:
        dep_id = parts[2]
        state, sdata = await get_user_state(uid)
        if state != "awaiting_screenshot" or \
                (sdata or {}).get("deposit_id") != dep_id:
            return await _send_tracked(
                update, context,
                "\u2139\uFE0F No active deposit order found.\n"
                "Start a fresh deposit from the menu.",
                main_menu_kb(is_admin(uid)))
        dep = await get_deposit(dep_id)
        if not dep or dep.get("status") != "pending":
            await clear_user_state(uid)
            return await _send_tracked(
                update, context,
                "\u2139\uFE0F This deposit order is already closed."
                "\nStart a fresh one from the menu.",
                main_menu_kb(is_admin(uid)))
        return await _send_tracked(
            update, context,
            screenshot_prompt_text(dep_id,
                                   (sdata or {}).get("method") or "bkash"),
            screenshot_kb(dep_id))
    if act == "cancel":
        dep_id = parts[2] if len(parts) >= 3 else None
        if not dep_id:
            state, sdata = await get_user_state(uid)
            if state == "awaiting_screenshot":
                dep_id = (sdata or {}).get("deposit_id")
        if dep_id:
            await cancel_pending_deposit(uid, dep_id)
        await clear_user_state(uid)
        return await _send_tracked(update, context,
                                   "\u274c <b>Deposit cancelled.</b>\n\n"
                                   + menu_info_text(),
                                   main_menu_kb(is_admin(uid)))


async def admin_flow_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin inline flows: adst:wa|tg|back, adstc:<ntype>:<country>,
    adrt:wa|tg, adbn:ban|unban"""
    q = update.callback_query
    uid = q.from_user.id
    if not is_admin(uid):
        await q.answer("Admins only", show_alert=True)
        return
    await _safe_answer(q)
    parts = q.data.split(":")
    grp, act = parts[0], parts[1]
    if grp == "adst":
        if act in ("wa", "tg"):
            return await show_admin_add_country(update, context, act)
        if act == "back":
            return await show_admin_add_type(update, context)
    if grp == "adstc" and len(parts) >= 3:
        return await prompt_admin_add_phone(update, context, parts[1], parts[2])
    if grp == "adrt" and act in ("wa", "tg"):
        return await prompt_admin_set_rate(update, context, act)
    if grp == "adbn" and act in ("ban", "unban"):
        return await prompt_admin_ban(update, context, act)
    if grp == "admg":
        if act == "add":
            return await prompt_admin_add_admin(update, context)
        if act == "rm":
            return await prompt_admin_remove_admin(update, context)
    if grp == "admuser":
        if act == "bal" and len(parts) >= 3:
            try:
                target = int(parts[2])
            except ValueError:
                await q.answer("Invalid user", show_alert=True)
                return
            return await prompt_admin_modbal(update, context, target)
        if act == "otp" and len(parts) >= 3:
            try:
                target = int(parts[2])
            except ValueError:
                await q.answer("Invalid user", show_alert=True)
                return
            return await render_otp_history(update, context, target)
        if act == "back":
            return await show_admin_panel(update, context)


async def fallback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gracefully answer old inline buttons from previous bot versions."""
    q = update.callback_query
    await q.answer("\u274C This button expired \u2014 please retry", show_alert=True)


async def deposit_create(update, context, uid, amount, method):
    """v9.15: method -> payment details -> pay -> screenshot. Only this.
    The deposit order is created with amount 0.00; the admin reads the
    real amount from the screenshot and types it at approval."""
    if method not in PAYMENT_METHODS:
        method = "bkash"
    deposit_id, expires = await create_deposit(uid, amount, method)
    account = await payment_account(method)
    await set_user_state(uid, "awaiting_screenshot",
                         {"deposit_id": deposit_id, "method": method})
    await _send_tracked(update, context,
                        payment_card_text(method, account,
                                          deposit_id, expires),
                        deposit_wait_kb(deposit_id))


async def prompt_custom_amount(update, context, uid, error=False):
    await set_user_state(uid, "dep_custom")
    min_dep = float(await get_setting("min_deposit"))
    if error:
        head = (f"\u274C Minimum deposit is <code>${min_dep:.2f}</code>\n"
                f"\U0001F4B5 Type the USDT amount again\n"
                f"Example: <code>1.50</code>")
    else:
        head = (f"\u270f\uFE0F <b>Type Your Amount</b>\n"
                f"\U0001F4B5 Min <code>${min_dep:.2f}</code>\n"
                f"Example: <code>1.50</code>")
    await _send_tracked(update, context, head, deposit_custom_kb())


def stock_format_hint() -> str:
    return (
        f"{DIV}\n"
        "\U0001F4F1 <b>Send numbers \u2014 one per line:</b>\n"
        "<code>+14133525884 | http://otp-api-link/xyz</code>\n\n"
        "\U0001F4C4 <b>Or upload a .txt file</b> with the same format.\n"
        "\U0001F527 <i>Small format mistakes are fixed automatically "
        "(missing +, extra spaces, commas, missing http://).</i>\n"
        f"{DIV}\n"
        "\u274C <b>Cancel</b> to stop."
    )


async def process_bulk_stock(update, context, uid, sdata, text):
    """Parse a bulk stock dump (pasted text or .txt file) and add every
    valid number.  Format per line:  +14133525884 | http://otp-api-link"""
    d = sdata or {}
    ntype = d.get("ntype", "wa")
    country = d.get("country", "USA")
    db_type = "whatsapp" if ntype == "wa" else "telegram"
    label = "WhatsApp" if ntype == "wa" else "Telegram"

    entries, errors = parse_stock_lines(text)
    if not entries and not errors:
        await _send_tracked(
            update, context,
            "\u26A0\uFE0F <b>NO NUMBERS FOUND</b> \u2014 try again:\n\n"
            + stock_format_hint(),
            admin_input_kb(),
        )
        return  # stay in the add-stock state

    added = dup = no_link = readded = 0
    for phone, url in entries:
        if not url:
            no_link += 1      # v9.14.3: no OTP link -> never sellable-checkable
            continue
        if await phone_in_available_stock(phone):
            dup += 1
            continue
        if await phone_in_stock_any(phone):
            readded += 1  # sold/refunded before - warn the admin below
        await add_stock(phone, url or "", db_type, country, uid)
        added += 1

    if added == 0:
        lines = ["\u274C <b>NOTHING ADDED</b>\n\n" + DIV]
        if dup:
            lines.append(f"\U0001F501 <b>{dup}</b> number(s) already in stock")
        if errors:
            lines.append(f"\u274C <b>{len(errors)}</b> bad line(s):")
            for ln, sample, why in errors[:5]:
                lines.append(f"   \u2022 <code>{html_escape(sample)}</code> \u2014 {why}")
        lines.append("\n" + stock_format_hint())
        await _send_tracked(update, context, "\n".join(lines), admin_input_kb())
        return  # stay in the add-stock state

    await clear_user_state(uid)
    lines = [
        f"\u2705 <b>STOCK ADDED \u2014 {label.upper()} "
        f"{flag_of(country)} {country}</b>\n",
        DIV,
        f"\U0001F4F1 <b>Numbers added:</b> {added}",
    ]
    if dup:
        lines.append(f"\U0001F501 <b>Duplicates skipped:</b> {dup}")
    if errors:
        lines.append(f"\u274C <b>Bad lines skipped:</b> {len(errors)}")
        for ln, sample, why in errors[:3]:
            lines.append(f"   \u2022 <code>{html_escape(sample)}</code> \u2014 {why}")
    if no_link:
        lines.append(
            f"\n\u274C <b>{no_link}</b> number(s) SKIPPED \u2014 no OTP link. "
            "Add them again WITH their link so OTP checking works."
        )
    if readded:
        lines.append(
            f"\n\u26A0\uFE0F <b>{readded}</b> number(s) were sold/refunded "
            "before \u2014 double-check they are not live duplicates, "
            "or you may sell the same number twice!"
        )
    lines.append(DIV)
    await _send_tracked(update, context, "\n".join(lines), admin_panel_kb())


# --------------------------------------------------------------------------- #
#  STATE TEXT HANDLER  (awaiting_tx + admin input states)
# --------------------------------------------------------------------------- #
async def handle_state_text(update, context, state, sdata, text):
    uid = update.effective_user.id
    d = sdata or {}

    if state == "search_otp":
        return await handle_search_otp(update, context, uid, text)

    if state == "admin_approve_amount":
        return await handle_admin_approve_amount(update, context, uid, d, text)

    if state == "admin_add_admin":
        try:
            target = int(text.strip())
        except ValueError:
            await _send_tracked(update, context,
                                "\u274C <b>Invalid ID.</b> Send a numeric "
                                "Telegram user ID:",
                                admin_input_kb())
            return
        if target in ADMIN_IDS:
            await clear_user_state(uid)
            await _send_tracked(update, context,
                                "\u2139\uFE0F <b>Already an admin.</b>",
                                admin_admins_kb())
            return
        await add_admin(target)
        await clear_user_state(uid)
        try:
            await context.bot.send_message(
                chat_id=target,
                text="\U0001F451 <b>You are now an ADMIN!</b>\n"
                     "Open the bot and tap \U0001F6E0\uFE0F Admin Panel.",
                parse_mode=ParseMode.HTML)
        except Exception:
            pass
        await _send_tracked(update, context,
                            f"\u2705 <b>ADMIN ADDED</b>\n\n"
                            f"{DIV}\n\U0001F194 <code>{target}</code>\n{DIV}",
                            admin_admins_kb())
        return

    if state == "admin_remove_admin":
        try:
            target = int(text.strip())
        except ValueError:
            await _send_tracked(update, context,
                                "\u274C <b>Invalid ID.</b> Send a numeric "
                                "Telegram user ID:",
                                admin_input_kb())
            return
        if target == ADMIN_ID:
            await _send_tracked(update, context,
                                "\u26A0\uFE0F <b>The super admin can\'t be "
                                "removed.</b> Send another ID:",
                                admin_input_kb())
            return
        if target not in ADMIN_IDS:
            await clear_user_state(uid)
            await _send_tracked(update, context,
                                "\u2139\uFE0F <b>Not an admin.</b>",
                                admin_admins_kb())
            return
        await remove_admin(target)
        await clear_user_state(uid)
        await _send_tracked(update, context,
                            f"\u274C <b>ADMIN REMOVED</b>\n\n"
                            f"{DIV}\n\U0001F194 <code>{target}</code>\n{DIV}",
                            admin_admins_kb())
        return

    if state == "admin_otp_stats":
        try:
            target = int(text.strip())
        except ValueError:
            await _send_tracked(update, context,
                                "\u274c <b>Invalid ID.</b> Send a numeric "
                                "Telegram user ID:",
                                admin_input_kb())
            return
        return await render_otp_history(update, context, target)

    if state == "dep_custom":
        # v9.15: custom amount picking removed
        return await show_dep_methods(update, context)

    if state in ("admin_add_phone", "admin_add_url"):
        # BULK stock add: one "+1phone | otp-url" per line (or .txt content)
        await process_bulk_stock(update, context, uid, d, text)
        return

    if state == "admin_set_rate":
        try:
            val = float(text)
            if val <= 0:
                raise ValueError
        except ValueError:
            await _send_tracked(update, context,
                                "\u274C <b>Invalid number.</b> Send a price like 2.50:",
                                admin_input_kb())
            return
        ntype = d.get("ntype", "wa")
        key = "whatsapp_rate" if ntype == "wa" else "telegram_rate"
        old = float(await get_setting(key))
        await set_setting(key, f"{val:.2f}")
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO rate_history(rate_type,old_rate,new_rate,changed_by) "
                "VALUES(?,?,?,?)",
                (key, old, val, uid),
            )
            await db.commit()
        await clear_user_state(uid)
        label = "WhatsApp" if ntype == "wa" else "Telegram"
        await _send_tracked(update, context,
                            f"\u2705 <b>{label.upper()} RATE UPDATED</b>\n\n"
                            f"{DIV}\n"
                            f"\U0001F4C9 <b>${old:.2f} \u2192 ${val:.2f}</b>\n"
                            f"{DIV}",
                            admin_panel_kb())
        return

    if state == "admin_broadcast":
        users = await get_all_users()
        sent = failed = 0
        for u in users:
            if u.get("is_banned"):
                continue  # banned users never receive broadcasts
            try:
                await context.bot.send_message(
                    chat_id=u["telegram_id"], text=text, parse_mode=ParseMode.HTML
                )
                sent += 1
            except Exception:
                # HTML failed (bad tags / entities) — fall back to plain text
                try:
                    await context.bot.send_message(
                        chat_id=u["telegram_id"], text=text
                    )
                    sent += 1
                except Exception:
                    failed += 1
        await clear_user_state(uid)
        await _send_tracked(update, context,
                            f"\u2705 <b>BROADCAST DONE</b>\n\n"
                            f"{DIV}\n"
                            f"\U0001F4EC <b>Sent:</b> {sent}\n"
                            f"\u274C <b>Failed:</b> {failed}\n"
                            f"{DIV}",
                            admin_panel_kb())
        return

    if state == "admin_ban":
        try:
            target = int(text)
        except ValueError:
            await _send_tracked(update, context,
                                "\u274C <b>Invalid ID.</b> Send a numeric Telegram user ID:",
                                admin_input_kb())
            return
        if target == ADMIN_ID:
            await _send_tracked(update, context,
                                "\u26A0\uFE0F <b>You can't ban the admin "
                                "(yourself).</b> Send another ID:",
                                admin_input_kb())
            return
        action = d.get("action", "ban")
        banned = action == "ban"
        await set_ban(target, banned)
        await clear_user_state(uid)
        label = "BANNED" if banned else "UNBANNED"
        await _send_tracked(update, context,
                            f"\u2705 <b>USER {label}</b>\n\n"
                            f"{DIV}\n\U0001F194 <code>{target}</code>\n{DIV}",
                            admin_panel_kb())
        return

    if state == "admin_modify_user":
        try:
            target = int(text.strip())
        except ValueError:
            await _send_tracked(update, context,
                                "\u274c <b>Invalid ID.</b> Send a numeric chat ID:",
                                admin_input_kb())
            return
        return await admin_user_details(update, context, target)

    if state == "admin_modbal":
        target = d.get("target")
        raw = text.strip().replace("$", "").replace(",", "")
        try:
            if raw.startswith("+"):
                mode, val = "add", float(raw[1:])
            elif raw.startswith("-"):
                mode, val = "deduct", float(raw[1:])
            else:
                mode, val = "set", float(raw)
        except ValueError:
            await _send_tracked(update, context,
                                "\u274c <b>Invalid amount.</b> e.g. 10.50 / +5 / -2:",
                                admin_input_kb())
            return
        u = await get_user(target)
        if not u:
            await clear_user_state(uid)
            await _send_tracked(update, context,
                                "\u26a0\ufe0f <b>User not found.</b>",
                                admin_panel_kb())
            return
        old = u.get("balance", 0.0) or 0.0
        if mode == "add":
            new = old + val
        elif mode == "deduct":
            new = old - val
        else:
            new = val
        clamp = ""
        if new < 0:
            new = 0.0
            clamp = "\n\u26a0\ufe0f <i>Balance can't be negative \u2014 set to $0.00</i>"
        await set_balance(target, new)
        label = {"add": "ADDED", "deduct": "DEDUCTED", "set": "SET"}[mode]
        note = (f"\u2705 <b>BALANCE {label}</b>\n"
                f"\U0001F4B0 <code>${old:.2f} \u2192 ${new:.2f}</code>{clamp}")
        await clear_user_state(uid)
        return await admin_user_details(update, context, target, note=note)

    if state == "admin_set_pay":
        t = text.strip().lower()
        picked = None
        for mkey, meta in PAYMENT_METHODS.items():
            if t.startswith(mkey):
                picked = (mkey, meta)
                break
        if not picked:
            await _send_tracked(update, context,
                                "\u274C <b>Format:</b>\n"
                                "<code>bkash 01712345678</code>\n"
                                "<code>nagad 01812345678</code>\n"
                                "<code>binance 123456789</code>",
                                admin_input_kb())
            return
        mkey, meta = picked
        value = text.strip()[len(mkey):].strip()
        if len(value) < 5:
            await _send_tracked(update, context,
                                f"\u26A0\uFE0F <b>{meta['label']} number/id "
                                "looks too short.</b> Send again:",
                                admin_input_kb())
            return
        await set_setting(meta["key"], value)
        await clear_user_state(uid)
        await _send_tracked(update, context,
                            f"\u2705 <b>{meta['label'].upper()} UPDATED</b>\n\n"
                            f"{DIV}\n<code>{html_escape(value)}</code>\n{DIV}",
                            admin_panel_kb())
        return

    # Unknown state — clean up and go home
    await clear_user_state(uid)
    await _send_tracked(update, context, menu_info_text(),
                        main_menu_kb(is_admin(uid)))


# --------------------------------------------------------------------------- #
#  PHOTO / DOCUMENT  (deposit screenshots)
# --------------------------------------------------------------------------- #
async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if update.message is None or not update.message.photo:
        return          # stale/queued update guard
    state, sdata = await get_user_state(uid)
    if state != "awaiting_screenshot":
        return
    await process_deposit_screenshot(update, context, uid, sdata or {},
                                     update.message.photo[-1].file_id)


async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if update.message is None or not update.message.document:
        return          # stale/queued update guard
    state, sdata = await get_user_state(uid)

    if state == "awaiting_screenshot":
        await update.message.reply_text(
            "\u274C <b>No files \u2014 please send a photo.</b>\n"
            "Send the screenshot as a <b>photo</b> "
            "(pick it from your gallery).",
            parse_mode=ParseMode.HTML,
        )
        return

    # Admin: refund approval upload (failed-urls .txt)
    if state == "admin_refund_upload" and is_admin(uid):
        doc = update.message.document
        name = (doc.file_name or "").lower()
        mime = (doc.mime_type or "")
        ok_type = (name.endswith((".txt", ".text", ".csv"))
                   or mime.startswith("text/"))
        if not ok_type:
            await update.message.reply_text(
                "\u26A0\uFE0F <b>Please send a <code>.txt</code></b> "
                "with the failed URLs.",
                parse_mode=ParseMode.HTML,
            )
            return
        if (doc.file_size or 0) > 2_000_000:
            await update.message.reply_text(
                "\u26A0\uFE0F <b>File too big (max 2 MB).</b>",
                parse_mode=ParseMode.HTML,
            )
            return
        tg_file = await context.bot.get_file(doc.file_id)
        raw = await tg_file.download_as_bytearray()
        text = bytes(raw).decode("utf-8", errors="replace")
        await update.message.reply_text(
            "\u23F3 <b>Matching refunds...</b>", parse_mode=ParseMode.HTML
        )
        await process_refund_file(update, context, uid, text)
        return

    # Admin: bulk stock upload via .txt file
    if state in ("admin_add_phone", "admin_add_url") and is_admin(uid):
        doc = update.message.document
        name = (doc.file_name or "").lower()
        mime = (doc.mime_type or "")
        ok_type = (name.endswith((".txt", ".text", ".csv"))
                   or mime.startswith("text/"))
        if not ok_type:
            await update.message.reply_text(
                "\u26A0\uFE0F <b>Please send a <code>.txt</code> file</b> "
                "with the numbers.",
                parse_mode=ParseMode.HTML,
            )
            return
        if (doc.file_size or 0) > 2_000_000:
            await update.message.reply_text(
                "\u26A0\uFE0F <b>File too big (max 2 MB).</b>\n"
                "Split it or paste the lines directly.",
                parse_mode=ParseMode.HTML,
            )
            return
        tg_file = await context.bot.get_file(doc.file_id)
        raw = await tg_file.download_as_bytearray()
        text = bytes(raw).decode("utf-8", errors="replace")
        await update.message.reply_text(
            "\u23F3 <b>Processing file...</b>", parse_mode=ParseMode.HTML
        )
        await process_bulk_stock(update, context, uid, sdata, text)
        return


# --------------------------------------------------------------------------- #
#  ADMIN INFO SCREENS
# --------------------------------------------------------------------------- #
async def admin_stock_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    counts, total = await get_stock_counts()
    lines = [
        f"\U0001F4CA <b>STOCK STATS</b>\n",
        f"{DIV}",
        f"\U0001F4E6 <b>Total available:</b> {total}",
        f"{DIV}",
    ]
    for nt, label, icon in (("whatsapp", "WhatsApp", "\U0001F7E2"),
                            ("telegram", "Telegram", "\U0001F535")):
        c = counts.get(nt, {})
        if c:
            lines.append(f"\n{icon} <b>{label}:</b>")
            for ctry, n in c.items():
                lines.append(f"  {flag_of(ctry)} {ctry} \u2014 {n}")
        else:
            lines.append(f"\n{icon} <b>{label}:</b> 0")
    lines.append(DIV)
    await _send_tracked(update, context, "\n".join(lines), admin_panel_kb())


async def admin_pending_deposits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    deps = await get_pending_deposits()
    if not deps:
        await _send_tracked(update, context,
                            f"\u2705 <b>NO PENDING DEPOSITS</b>\n\n{DIV}\nAll caught up! \U0001F389",
                            admin_panel_kb())
        return
    await _send_tracked(update, context,
                        f"\U0001F4B0 <b>PENDING DEPOSITS</b>\n\n"
                        f"{DIV}\n\U0001F4E8 Sending {min(len(deps), 15)} request(s) below...",
                        admin_panel_kb())
    for d in deps[:15]:
        u = await get_user(d["user_id"])
        uname = f"@{u['username']}" if u and u.get("username") else "\u2014"
        txt = (
            f"\U0001F4B0 <b>PENDING DEPOSIT</b>\n\n"
            f"{DIV}\n"
            f"\U0001F464 <b>User:</b> {html_escape((u or {}).get('first_name') or '?')} {uname}\n"
            f"\U0001F194 <b>ID:</b> <code>{d['user_id']}</code>\n"
            f"\U0001F4B5 <b>Amount:</b> ${d['amount']:.2f}\n"
            f"\U0001F9FE <b>Order:</b> <code>{d['deposit_id']}</code>\n"
            f"\U0001F4B3 <b>Method:</b> "
            f"{(PAYMENT_METHODS.get(d.get('network')) or {}).get('label', '?')}\n"
            f"{DIV}"
        )
        try:
            if d.get("screenshot_file_id"):
                await update.message.reply_photo(
                    photo=d["screenshot_file_id"], caption=txt,
                    parse_mode=ParseMode.HTML,
                    reply_markup=admin_deposit_approve_kb(d["deposit_id"]),
                )
            else:
                await update.message.reply_text(
                    txt, parse_mode=ParseMode.HTML,
                    reply_markup=admin_deposit_approve_kb(d["deposit_id"]),
                )
        except Exception as e:
            logger.warning("send pending dep failed: %s", e)


async def admin_list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    users = await get_all_users()
    lines = [f"\U0001F465 <b>USERS ({len(users)})</b>\n", DIV]
    for u in users[:30]:
        bal = u.get("balance", 0.0) or 0.0
        banned = " \U0001F6AB" if u.get("is_banned") else ""
        adm = " \U0001F451" if u.get("is_admin") else ""
        lines.append(f"<code>{u['telegram_id']}</code> \u2014 ${bal:.2f}{banned}{adm}")
    if len(users) > 30:
        lines.append(f"\n<i>...and {len(users) - 30} more</i>")
    lines.append(DIV)
    await _send_tracked(update, context, "\n".join(lines), admin_panel_kb())


async def admin_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    s = await get_statistics()
    txt = (
        f"\U0001F4C8 <b>STATISTICS</b>\n\n"
        f"{DIV}\n"
        f"\U0001F465 <b>Users:</b> {s['users']}\n"
        f"\U0001F4E6 <b>Available stock:</b> {s['available']}\n"
        f"\U0001F6D2 <b>Sold:</b> {s['sold']}\n"
        f"\u23F3 <b>Pending deposits:</b> {s['pending_deposits']}\n"
        f"{DIV}\n"
        f"\U0001F3E6 <b>Total deposited:</b> ${s['total_deposit']:.2f}\n"
        f"\U0001F4B8 <b>Total spent:</b> ${s['total_spent']:.2f}\n"
        f"{DIV}"
    )
    await _send_tracked(update, context, txt, admin_panel_kb())


# --------------------------------------------------------------------------- #
#  ADMIN DEPOSIT APPROVE/REJECT  (manual payments)
#  Approve -> admin types the real amount -> credit + archive.
# --------------------------------------------------------------------------- #
async def admin_deposit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """v9.15: Approve -> admin types amount -> credit + delete SS msgs.
    Reject -> delete SS msgs (user chat + every admin chat) too."""
    q = update.callback_query
    await _safe_answer(q)
    parts = q.data.split(":")
    action = parts[1]
    dep_id = parts[2]
    admin_id = q.from_user.id
    if not is_admin(admin_id):
        await q.answer("Admins only", show_alert=True)
        return

    if action == "ok":
        dep = await get_deposit(dep_id)
        if not dep or dep.get("status") != "pending":
            await q.answer("Already processed or not found", show_alert=True)
            return
        await set_user_state(admin_id, "admin_approve_amount",
                             {"deposit_id": dep_id})
        meta = PAYMENT_METHODS.get(dep.get("network")) or {}
        approving = (
            f"\u23F3 <b>APPROVING</b>\n\n"
            f"\U0001F194 User: <code>{dep['user_id']}</code>\n"
            f"\U0001F4B3 Method: {meta.get('label', '?')}\n"
            f"\U0001F9FE Order: <code>{dep_id}</code>\n\n"
            f"\U0001F449 Send the amount to credit ($)"
        )
        try:
            if q.message and q.message.photo:
                await q.edit_message_caption(caption=approving,
                                             parse_mode=ParseMode.HTML)
            elif q.message:
                await q.edit_message_text(approving,
                                          parse_mode=ParseMode.HTML)
        except Exception:
            pass
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=(f"\U0001F4B5 <b>Send the amount to credit for "
                      f"<code>{dep_id}</code></b>\n"
                      "Read it from the screenshot. "
                      "Example: <code>5.00</code>"),
                parse_mode=ParseMode.HTML,
                reply_markup=admin_input_kb())
        except Exception:
            pass
    elif action == "no":
        dep_before = await get_deposit(dep_id)
        if not await reject_deposit(dep_id, admin_id):
            await q.answer("Already processed or not found", show_alert=True)
            return
        dep = await get_deposit(dep_id)
        uid_t = dep["user_id"] if dep else None
        if uid_t:
            try:
                await context.bot.send_message(
                    chat_id=uid_t,
                    text=(
                        "\u274C <b>DEPOSIT REJECTED</b>\n\n"
                        f"{DIV}\n"
                        f"\U0001F9FE <b>Order:</b> <code>{dep_id}</code>\n"
                        f"{DIV}\n\n"
                        "\U0001F4AC Contact Support if you think this is "
                        "an error."
                    ),
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
        # v9.15: delete the user screenshot + every admin copy
        if dep_before:
            try:
                if dep_before.get("screenshot_chat_id") and \
                        dep_before.get("screenshot_msg_id"):
                    await context.bot.delete_message(
                        chat_id=dep_before["screenshot_chat_id"],
                        message_id=dep_before["screenshot_msg_id"])
            except Exception:
                pass
            try:
                raw_ids = dep_before.get("admin_msg_ids")
                pairs = json.loads(raw_ids) if raw_ids else []
                for aid, mid in pairs:
                    try:
                        await context.bot.delete_message(chat_id=aid,
                                                          message_id=mid)
                    except Exception:
                        pass
            except Exception:
                pass
        rejected = f"\u274C <b>REJECTED</b> \u2014 <code>{dep_id}</code>"
        try:
            if q.message and q.message.photo:
                await q.edit_message_caption(caption=rejected,
                                             parse_mode=ParseMode.HTML)
            elif q.message:
                await q.edit_message_text(rejected,
                                          parse_mode=ParseMode.HTML)
        except Exception:
            pass

# --------------------------------------------------------------------------- #
#  ERROR HANDLER
# --------------------------------------------------------------------------- #
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Unhandled exception: %s", context.error, exc_info=context.error)
    # Never fail silently - tell the user something went wrong
    try:
        chat_id = None
        eff = getattr(update, "effective_chat", None)
        if eff is not None:
            chat_id = getattr(eff, "id", None)
        if chat_id:
            await context.bot.send_message(
                chat_id=chat_id,
                text="\u26a0\ufe0f <b>Something went wrong.</b>\n"
                     "Please try again \u2014 or press /start.",
                parse_mode=ParseMode.HTML,
            )
    except Exception:
        pass


# --------------------------------------------------------------------------- #
#  MAIN
# --------------------------------------------------------------------------- #
async def post_init(app: Application):
    await init_db()
    try:
        await load_admins()
        logger.info("Loaded %s admin(s) (super admin %s).",
                    len(ADMIN_IDS), ADMIN_ID)
    except Exception as e:
        logger.warning("load_admins at boot failed: %s", e)
    try:
        await app.bot.set_my_commands([
            ("start", "Open main menu"),
            ("menu", "Show menu"),
            ("admin", "Admin panel"),
            ("help", "Help"),
        ])
    except Exception as e:
        logger.warning("set_my_commands failed: %s", e)
    logger.info("Bot started as @%s", (await app.bot.get_me()).username)
    logger.info("Deposit v9.15: pick method -> pay -> send screenshot "
                "-> admin approves + types amount -> msgs deleted")
    _p = {k: await get_setting(k) for k in
          ("bkash_number", "nagad_number", "binance_id")}
    logger.info("Payments (v9.14): bkash=%s nagad=%s binance=%s",
                _p["bkash_number"], _p["nagad_number"], _p["binance_id"])


def build_app() -> Application:
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # Debug: log every incoming update (enable with LOG_UPDATES=1)
    if os.getenv("LOG_UPDATES"):
        async def _log_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
            try:
                if update.message:
                    u = update.message.from_user
                    logger.info("MSG  user=%s (%s) chat=%s text=%r",
                                u.id, u.username, update.message.chat_id,
                                (update.message.text or "")[:60])
                elif update.callback_query:
                    u = update.callback_query.from_user
                    logger.info("CALL user=%s (%s) data=%r",
                                u.id, u.username, update.callback_query.data)
            except Exception:
                pass
        app.add_handler(TypeHandler(Update, _log_update), group=-1)

    # Commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("menu", menu_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("trace", trace_cmd))

    # Text router (ALL navigation happens through the bottom keyboard)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    # Photo / Document (deposit screenshots)
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, on_document))

    # Callback queries (specific first, fallback LAST for old-version buttons)
    app.add_handler(CallbackQueryHandler(otp_callback, pattern=r"^otp:"))
    app.add_handler(CallbackQueryHandler(refund_callback, pattern=r"^refund:"))
    app.add_handler(CallbackQueryHandler(admin_deposit_callback, pattern=r"^admdep:"))
    app.add_handler(CallbackQueryHandler(buy_callback, pattern=r"^buy:"))
    app.add_handler(CallbackQueryHandler(dep_callback, pattern=r"^dep:"))
    app.add_handler(CallbackQueryHandler(admin_flow_callback,
                                         pattern=r"^(adst|adstc|adrt|adbn|admg|admuser):"))
    app.add_handler(CallbackQueryHandler(nav_callback, pattern=r"^nav:"))
    app.add_handler(CallbackQueryHandler(fallback_callback))

    app.add_error_handler(on_error)
    return app


def main():
    # Startup/runtime supervisor: transient Telegram-API or network
    # failures (proven live: TimedOut in get_me) must not leave the
    # bot dead. Restart with capped backoff; a CLEAN shutdown (SIGTERM
    # from timeout/systemd, Ctrl-C) exits without restarting.
    attempt = 0
    while True:
        attempt += 1
        try:
            logger.info("Starting bot v9.16 (super instant OTP burst, "
                        "2s fast-lane poller, SMS link on receipt)... "
                        "attempt %s", attempt)
            app = build_app()
            app.run_polling(allowed_updates=Update.ALL_TYPES)
            logger.info("Clean shutdown - supervisor exiting.")
            break
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            wait = min(30, 3 * attempt)
            logger.warning("Bot failure (%s: %s) - auto-restart in %ss",
                           type(e).__name__, str(e)[:100], wait)
            time.sleep(wait)


if __name__ == "__main__":
    main()
