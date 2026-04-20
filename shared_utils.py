import os
import json
import time
import asyncio
import datetime
import random
import string
from typing import Dict, Any, Optional, List

# =========================
# APRIL FOOLS' DAY MODE (Disabled)
# =========================

APRIL_FOOLS_MODE = False  # Enable April Fools' mode by setting to True

def should_april_fools_glitch() -> bool:
    """Determine if April Fools' glitch should occur (5% chance when mode is enabled)"""
    return APRIL_FOOLS_MODE and random.random() < 0.05

def get_april_fools_message() -> str:
    """Get a random April Fools' message"""
    messages = [
        "🎪 A cirkusz ma nyitva! 🎪",
        "🤡 A bohóc elárulta a titkát! 🤡",
        "🎭 A színházban ma előadás van! 🎭",
        "🃏 A kártyák újra keverve! 🃏",
    ]
    return random.choice(messages)

def get_funny_rank(rank: str) -> str:
    """Get a funny alternative rank name for April Fools' mode"""
    funny_ranks = {
        "Unranked": "🎪 Cirkuszban",
        "LT5": "🤡 Bohóc",
        "HT5": "🎭 Színész",
        "LT4": "🃏 Kártyás",
        "HT4": "🎪 Cirkuszos",
        "LT3": "🤡 Főbohóc",
        "HT3": "🎭 Főszínész",
        "LT2": "🃏 Főkártya",
        "HT2": "🎪 Cirkuszkapitány",
        "LT1": "🤡 Cirkuszdirigens",
        "HT1": "🎭 Színházigazgató",
    }
    return funny_ranks.get(rank, rank)


def truncate_message(text: str, max_length: int = 1900) -> str:
    """Truncate a message to fit Discord's 2000 character limit with safety margin"""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


# =========================
# ENV / CONFIG
# =========================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
STAFF_ROLE_ID = int(os.getenv("STAFF_ROLE_ID", "0"))
TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID", "0"))
# Additional role IDs that can use staff commands
EXTRA_STAFF_ROLE_IDS = [int(os.getenv("EXTRA_STAFF_ROLE_IDS", "0"))] if os.getenv("EXTRA_STAFF_ROLE_IDS") else []
# Specific user IDs that can use staff commands (comma-separated)
ALLOWED_USER_IDS = [int(x.strip()) for x in os.getenv("ALLOWED_USER_IDS", "").split(",") if x.strip()]
# DEBUG: Hardcoded user ID for testing
DEBUG_ALLOWED_USERS = []
# DEBUG: Hardcoded role IDs for testing
DEBUG_ALLOWED_ROLES = [1483822408182796418]

WEBSITE_URL = os.getenv("WEBSITE_URL", "").rstrip("/")  # e.g. https://neontiers.vercel.app
BOT_API_KEY = os.getenv("BOT_API_KEY", "")              # shared secret between bot and website

# Minecraft Verification API
MINECRAFT_API_URL = os.getenv("MINECRAFT_API_URL", "http://localhost:8080").rstrip("/")

WIPE_GLOBAL_COMMANDS = os.getenv("WIPE_GLOBAL_COMMANDS", "0") == "1"

COOLDOWN_SECONDS = 14 * 24 * 60 * 60
DATA_FILE = "data.json"

HTTP_TIMEOUT_SECONDS = 10  # hard timeout so it never "thinks forever"


# =========================
# CONSTANTS
# =========================
TICKET_TYPES = [
    ("Vanilla", "vanilla", 1469763891226480926),
    ("UHC", "uhc", 1469765994988704030),
    ("Pot", "pot", 1469763780593324032),
    ("NethPot", "nethpot", 1469763817218117697),
    ("SMP", "smp", 1469764274955223161),
    ("Sword", "sword", 1469763677141074125),
    ("Axe", "axe", 1469763738889486518),
    ("Mace", "mace", 1469763612452196375),
    ("Cart", "cart", 1469763920871952435),
    ("Creeper", "creeper", 1469764200812249180),
    ("DiaSMP", "diasmp", 1469763946968911893),
    ("OGVanilla", "ogvanilla", 1469764329460203571),
    ("ShieldlessUHC", "shieldlessuhc", 1469766017243807865),
    ("SpearMace", "spearmace", 1469968704203788425),
    ("SpearElytra", "spearelytra", 1469968762575912970),
]

# Required rounds for each gamemode (FT = First to, LT = Last to)
# Format: (default_ft, lt3_below_ft, loss_ft optional)
# If player is below LT3, they play fewer rounds
# If they lose a round against tester, they play even fewer rounds (for certain modes)
TICKET_ROUNDS = {
    "vanilla": ("FT4", "FT3", None),
    "diasmp": ("FT4", "FT3", "FT2"),  # FT2 if lose round
    "ogvanilla": ("FT4", "FT2", None),
    "nethpot": ("FT4", "FT2", None),
    "mace": ("FT4", "FT2", None),
    "smp": ("FT4", "FT3", "FT2"),  # FT2 if lose round
    "cart": ("FT4", "FT3", "FT2"),  # FT2 if lose round
    "sword": ("FT10", "FT6", None),
    "uhc": ("FT6", "FT3", None),
    "pot": ("FT10", "FT6", None),
    "creeper": ("FT6", "FT4", "FT3"),  # FT3 if lose round
    "shieldlessuhc": ("FT6", "FT4", None),
    "axe": ("FT20", "FT10", None),
    "spearmace": ("FT6", "FT3", None),
    "spearelytra": ("FT6", "FT3", None),
}


def get_ticket_rounds_display(mode_key: str) -> str:
    """Get the display string for required rounds based on gamemode"""
    rounds = TICKET_ROUNDS.get(mode_key.lower())
    if not rounds:
        return "FT4"

    default_ft, lt3_ft, loss_ft = rounds

    if loss_ft:
        return f"{default_ft}, LT3 alatt {lt3_ft}, ha nem nyersz a teszter ellen kört akkor {loss_ft}"
    else:
        return f"{default_ft}, LT3 alatt {lt3_ft}"

MODE_LIST = [t[0] for t in TICKET_TYPES]

RANKS = [
    "Unranked",
    "LT5", "HT5",
    "LT4", "HT4",
    "LT3", "HT3",
    "LT2", "HT2",
    "LT1", "HT1",
]

POINTS = {
    "Unranked": 0,
    "LT5": 1, "HT5": 2,
    "LT4": 3, "HT4": 4,
    "LT3": 6, "HT3": 8,
    "LT2": 10, "HT2": 12,
    "LT1": 14, "HT1": 18,
}

# Mapping from database gamemode names to bot code keys
# This handles differences between database naming and bot TICKET_TYPES
GAMEMODE_ALIASES = {
    # Database name variations -> TICKET_TYPES key (lowercase)
    "ogv": "ogvanilla",
    "ogvanilla": "ogvanilla",
    "nethpot": "nethpot",
    "uhc": "uhc",
    "shieldlessuhc": "shieldlessuhc",
    "spearmace": "spearmace",
    "spearelytra": "spearelytra",
}

# Reverse mapping: bot keys (lowercase) -> proper display names
GAMEMODE_DISPLAY_NAMES = {
    "vanilla": "Vanilla",
    "uhc": "UHC",
    "pot": "Pot",
    "nethpot": "NethPot",  # Note: capital P for NethPot
    "smp": "SMP",
    "sword": "Sword",
    "axe": "Axe",
    "mace": "Mace",
    "cart": "Cart",
    "creeper": "Creeper",
    "diasmp": "DiaSMP",
    "ogvanilla": "OGVanilla",
    "shieldlessuhc": "ShieldlessUHC",
    "spearmace": "SpearMace",
    "spearelytra": "SpearElytra",
}

def normalize_gamemode(mode: str) -> str:
    """Normalize gamemode name to bot's TICKET_TYPES key format"""
    if not mode:
        return mode
    normalized = mode.lower().strip()
    return GAMEMODE_ALIASES.get(normalized, normalized)

def get_gamemode_display_name(mode_key: str) -> str:
    """Get proper display name for a gamemode key"""
    if not mode_key:
        return mode_key
    # First try exact match (case-sensitive) for proper casing like "NethPot"
    if mode_key in GAMEMODE_DISPLAY_NAMES:
        return GAMEMODE_DISPLAY_NAMES[mode_key]
    # Then try lowercase lookup
    return GAMEMODE_DISPLAY_NAMES.get(mode_key.lower().strip(), mode_key)


# =========================
# DATABASE
# =========================
# Database - Supabase REST Data API (recommended)
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()

# Legacy PostgreSQL support (Railway/Supabase Direct)
DATABASE_URL = os.getenv("DATABASE_URL", "")
SUPABASE_PG_URL = os.getenv("SUPABASE_PG_URL", "")

# Use Supabase REST API if URL is set
USE_SUPABASE_API = bool(SUPABASE_URL and SUPABASE_KEY)

print(f"SUPABASE_URL present: {bool(SUPABASE_URL)}")
print(f"SUPABASE_KEY present: {bool(SUPABASE_KEY)}")
print(f"Using Supabase REST API: {USE_SUPABASE_API}")
if USE_SUPABASE_API:
    print(f"Supabase URL: {SUPABASE_URL}")
print(f"DATABASE_URL present: {bool(DATABASE_URL)}")

db_pool: Optional[any] = None  # asyncpg.Pool
supabase_headers: Dict[str, str] = {}

import aiohttp
from aiohttp import web

import asyncpg

async def init_db():
    """Initialize database connection - either Supabase REST API or PostgreSQL"""
    global db_pool, supabase_headers

    # Try Supabase REST API first
    if USE_SUPABASE_API:
        supabase_headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        }
        print(f"Using Supabase REST API: {SUPABASE_URL}/rest/v1/")
        print("Database initialized successfully!")
        return

    # Fallback to PostgreSQL
    DB_CONNECTION_STRING = DATABASE_URL or SUPABASE_PG_URL
    if not DB_CONNECTION_STRING:
        print("WARNING: No database configured, linked accounts will not be persisted!")
        return

    try:
        # Supabase uses postgresql://, convert to postgres:// if needed
        connection_str = DB_CONNECTION_STRING
        if connection_str.startswith("postgresql://"):
            connection_str = connection_str.replace("postgresql://", "postgres://", 1)

        print(f"Connecting to database: {connection_str[:50]}...")
        db_pool = await asyncpg.create_pool(connection_str, min_size=1, max_size=5)

        # Create tables if they don't exist
        async with db_pool.acquire() as conn:
            # Create linked_accounts table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS linked_accounts (
                    id SERIAL PRIMARY KEY,
                    discord_id BIGINT NOT NULL UNIQUE,
                    minecraft_name VARCHAR(255) NOT NULL,
                    linked_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            # Create pending_codes table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS pending_codes (
                    id SERIAL PRIMARY KEY,
                    discord_id BIGINT NOT NULL,
                    code VARCHAR(8) NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    used BOOLEAN DEFAULT FALSE
                )
            """)

            # Create indexes
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_linked_discord ON linked_accounts(discord_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_linked_minecraft ON linked_accounts(minecraft_name)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_pending_code ON pending_codes(code)")

        print("Database initialized successfully!")
    except Exception as e:
        print(f"Failed to initialize database: {e}")
        db_pool = None

async def close_db():
    """Close database connection"""
    global db_pool
    if db_pool:
        await db_pool.close()


# =========================
# Supabase REST API Helpers
# =========================

async def supabase_select(table: str, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """Select rows from a table using Supabase REST API"""
    if not USE_SUPABASE_API:
        return []

    url = f"{SUPABASE_URL}/rest/v1/{table}"
    params = {}
    if filters:
        for key, value in filters.items():
            params[key] = f"eq.{value}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=supabase_headers, params=params) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    print(f"Supabase select error: {resp.status} - {await resp.text()}")
                    return []
    except Exception as e:
        print(f"Supabase select exception: {e}")
        return []

async def supabase_insert(table: str, data: Dict[str, Any]) -> bool:
    """Insert a row into a table using Supabase REST API"""
    if not USE_SUPABASE_API:
        return False

    url = f"{SUPABASE_URL}/rest/v1/{table}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=supabase_headers, json=data) as resp:
                if resp.status in (200, 201):
                    return True
                else:
                    text = await resp.text()
                    print(f"Supabase insert error: {resp.status} - {text}")
                    if "duplicate" in text.lower() or "unique" in text.lower():
                        return await supabase_upsert(table, data)
                    return False
    except Exception as e:
        print(f"Supabase insert exception: {e}")
        return False

async def supabase_upsert(table: str, data: Dict[str, Any]) -> bool:
    """Upsert a row into a table using Supabase REST API"""
    if not USE_SUPABASE_API:
        return False

    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = supabase_headers.copy()
    headers["Prefer"] = "resolution=merge-duplicates"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as resp:
                if resp.status in (200, 201):
                    return True
                else:
                    print(f"Supabase upsert error: {resp.status} - {await resp.text()}")
                    return False
    except Exception as e:
        print(f"Supabase upsert exception: {e}")
        return False

async def supabase_update(table: str, data: Dict[str, Any], filters: Dict[str, Any]) -> bool:
    """Update rows in a table using Supabase REST API"""
    if not USE_SUPABASE_API:
        return False

    url = f"{SUPABASE_URL}/rest/v1/{table}"
    params = {}
    for key, value in filters.items():
        params[key] = f"eq.{value}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.patch(url, headers=supabase_headers, json=data, params=params) as resp:
                if resp.status in (200, 204):
                    return True
                else:
                    print(f"Supabase update error: {resp.status} - {await resp.text()}")
                    return False
    except Exception as e:
        print(f"Supabase update exception: {e}")
        return False

async def supabase_delete(table: str, filters: Dict[str, Any]) -> bool:
    """Delete rows from a table using Supabase REST API"""
    if not USE_SUPABASE_API:
        return False

    url = f"{SUPABASE_URL}/rest/v1/{table}"
    params = {}
    for key, value in filters.items():
        params[key] = f"eq.{value}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.delete(url, headers=supabase_headers, params=params) as resp:
                if resp.status in (200, 204):
                    return True
                else:
                    print(f"Supabase delete error: {resp.status} - {await resp.text()}")
                    return False
    except Exception as e:
        print(f"Supabase delete exception: {e}")
        return False

def supabase_select_sync(table: str, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """Synchronous wrapper for select"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, supabase_select(table, filters))
                return future.result()
        else:
            return asyncio.run(supabase_select(table, filters))
    except Exception as e:
        print(f"supabase_select_sync error: {e}")
        return []

def supabase_insert_sync(table: str, data: Dict[str, Any]) -> bool:
    """Synchronous wrapper for insert"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, supabase_insert(table, data))
                return future.result()
        else:
            return asyncio.run(supabase_insert(table, data))
    except Exception as e:
        print(f"supabase_insert_sync error: {e}")
        return False


# =========================
# STORAGE
# =========================
def _load_data() -> Dict[str, Any]:
    if not os.path.exists(DATA_FILE):
        return {"ticket_state": {}, "cooldowns": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"ticket_state": {}, "cooldowns": {}}


def _save_data(data: Dict[str, Any]) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_open_ticket_channel_id(user_id: int, mode_key: str) -> Optional[int]:
    data = _load_data()
    return data.get("ticket_state", {}).get(str(user_id), {}).get(mode_key)


def set_open_ticket_channel_id(user_id: int, mode_key: str, channel_id: Optional[int]) -> None:
    data = _load_data()
    ticket_state = data.setdefault("ticket_state", {})
    user_state = ticket_state.setdefault(str(user_id), {})
    if channel_id is None:
        user_state.pop(mode_key, None)
    else:
        user_state[mode_key] = channel_id
    _save_data(data)


def get_last_closed(user_id: int, mode_key: str) -> float:
    data = _load_data()
    return float(data.get("cooldowns", {}).get(str(user_id), {}).get(mode_key, 0))


def set_last_closed(user_id: int, mode_key: str, ts: float) -> None:
    data = _load_data()
    cds = data.setdefault("cooldowns", {})
    u = cds.setdefault(str(user_id), {})
    u[mode_key] = ts
    _save_data(data)


def cooldown_left(user_id: int, mode_key: str) -> int:
    last = get_last_closed(user_id, mode_key)
    if last <= 0:
        return 0
    left = int((last + COOLDOWN_SECONDS) - time.time())
    return max(0, left)


def format_cooldown(seconds: int) -> str:
    """Format cooldown time nicely"""
    if seconds <= 0:
        return "0"
    days = seconds // (24 * 60 * 60)
    hours = (seconds % (24 * 60 * 60)) // (60 * 60)
    minutes = (seconds % (60 * 60)) // 60

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}ó")
    if minutes > 0:
        parts.append(f"{minutes}p")
    return " ".join(parts) if parts else "<1p"


async def get_player_tier_for_mode(discord_id: int, mode_key: str) -> str:
    """Get player's tier for a specific gamemode - returns 'Unranked' if none"""
    linked_mc = await get_linked_minecraft_name_async(discord_id)
    if not linked_mc or not WEBSITE_URL:
        return "Unranked"

    try:
        mode_param = normalize_gamemode(mode_key)
        res = await api_get_tests(username=linked_mc, mode=mode_param)
        if res.get("status") == 200:
            data = res.get("data", {})
            test = data.get("test")
            tests = data.get("tests", [])
            target = test or (tests[0] if tests else None)
            if target:
                return str(target.get("rank", "Unranked")) or "Unranked"
    except Exception as e:
        print(f"Error getting tier: {e}")
    return "Unranked"


def quick_check_player_tier(discord_id: int, mode_key: str) -> bool:
    """Quick check if player is likely LT3+ for this mode (no async)"""
    try:
        data = _load_data()
        # Check cooldowns - if no cooldown entry, likely hasn't been tested
        last = data.get("cooldowns", {}).get(str(discord_id), {}).get(mode_key, 0)
        return last > 0
    except Exception:
        return False


def is_lt3_or_above(rank: str) -> bool:
    """Check if rank is LT3 or above"""
    rank_points = POINTS.get(rank, 0)
    return rank_points >= 6  # LT3 = 6 points


def is_under_lt3(rank: str) -> bool:
    """Check if rank is under LT3"""
    rank_points = POINTS.get(rank, 0)
    return rank_points < 6


# =========================
# WEBSITE API
# =========================
def _auth_headers() -> Dict[str, str]:
    if not BOT_API_KEY:
        return {}
    return {"Authorization": f"Bearer {BOT_API_KEY}"}


async def api_get_tests(username: str, mode: str) -> Dict[str, Any]:
    if not WEBSITE_URL:
        return {"status": 0, "data": {"tests": []}}

    url = f"{WEBSITE_URL}/api/tests?username={username}&gamemode={mode}"
    print(f"[API_GET_TESTS] Requesting: {url}")

    try:
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=_auth_headers(), timeout=timeout) as resp:
                print(f"[API_GET_TESTS] Response status: {resp.status}")
                try:
                    data = await resp.json()
                except Exception:
                    data = {"error": await resp.text()}
                return {"status": resp.status, "data": data}
    except asyncio.TimeoutError:
        print(f"[API_GET_TESTS] Timeout fetching tests for {username}")
        return {"status": 0, "data": {"error": "timeout"}}
    except Exception as e:
        print(f"[API_GET_TESTS] Error: {e}")
        return {"status": 0, "data": {"error": str(e)}}


async def api_get_all_tests() -> Dict[str, Any]:
    """Get all tests from the website"""
    if not WEBSITE_URL:
        return {"status": 0, "data": {"tests": []}}

    url = f"{WEBSITE_URL}/api/tests"
    print(f"[API_GET_ALL_TESTS] Requesting: {url}")

    try:
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=_auth_headers(), timeout=timeout) as resp:
                print(f"[API_GET_ALL_TESTS] Response status: {resp.status}")
                try:
                    data = await resp.json()
                except Exception:
                    data = {"error": await resp.text()}
                return {"status": resp.status, "data": data}
    except asyncio.TimeoutError:
        print(f"[API_GET_ALL_TESTS] Timeout fetching tests")
        return {"status": 0, "data": {"error": "timeout"}}
    except Exception as e:
        print(f"[API_GET_ALL_TESTS] Error: {e}")
        return {"status": 0, "data": {"error": str(e)}}


async def api_post_test(username: str, mode: str, rank: str, tester: any) -> Dict[str, Any]:
    if not WEBSITE_URL:
        return {"status": 0, "data": {"error": "WEBSITE_URL not set"}}

    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)

    # First, check for and delete any duplicates for this mode
    # Use proper display name for checking
    mode_for_api = get_gamemode_display_name(mode)
    try:
        # Get all tests for this user
        check_url = f"{WEBSITE_URL}/api/tests?username={username}"
        async with aiohttp.ClientSession() as session:
            async with session.get(check_url, headers=_auth_headers(), timeout=timeout) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    tests = data.get("data", {}).get("tests", [])
                    # Find duplicates for this mode (case-insensitive)
                    normalized_mode = mode_for_api.lower()
                    for test in tests:
                        test_mode = str(test.get("gamemode", "")).lower()
                        if test_mode == normalized_mode:
                            # Found existing entry - will be updated by upsert
                            test_id = test.get("id")
                            print(f"Found existing entry for {username}/{test_mode}: id={test_id}, rank={test.get('rank')}")
    except Exception as e:
        print(f"Error checking duplicates: {e}")

    url = f"{WEBSITE_URL}/api/tests"
    # Use proper display name for mode (not lowercase)
    mode_for_api = get_gamemode_display_name(mode)

    payload = {
        "username": username,
        "mode": mode_for_api,  # Use proper casing like "Sword", "NethPot", etc.
        "rank": rank,
        "testerId": str(tester.id),
        "testerName": tester.display_name,
        "upsert": True,
        "ts": int(time.time()),
    }
    print(f"[API_POST_TEST] Sending: username={username}, mode={mode.lower()}, rank={rank}, upsert=True")

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=_auth_headers(), timeout=timeout) as resp:
            try:
                data = await resp.json()
            except Exception:
                data = {"error": await resp.text()}
            print(f"[API_POST_TEST] Save response: status={resp.status}, data={data}")
            return {"status": resp.status, "data": data}


async def api_rename_player(old_name: str, new_name: str) -> Dict[str, Any]:
    """Rename a player on the tierlist (admin only)"""
    if not WEBSITE_URL:
        return {"status": 0, "data": {"error": "WEBSITE_URL not set"}}

    # Use /api/tests/rename endpoint with POST method
    url = f"{WEBSITE_URL}/api/tests/rename"
    payload = {
        "oldName": old_name,
        "newName": new_name,
    }

    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=_auth_headers(), timeout=timeout) as resp:
            try:
                data = await resp.json()
            except Exception:
                data = {"error": await resp.text()}
            return {"status": resp.status, "data": data}


async def api_set_ban(username: str, banned: bool, expires_at: Optional[int] = None, reason: str = "") -> Dict[str, Any]:
    """Set ban status on the website"""
    if not WEBSITE_URL:
        return {"status": 0, "data": {"error": "WEBSITE_URL not set"}}

    url = f"{WEBSITE_URL}/api/tests/ban"
    payload = {
        "username": username,
        "banned": banned,
    }

    if expires_at is not None:
        payload["expiresAt"] = expires_at
    if reason:
        payload["reason"] = reason

    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=_auth_headers(), timeout=timeout) as resp:
            try:
                data = await resp.json()
            except Exception:
                data = {"error": await resp.text()}
            return {"status": resp.status, "data": data}


async def api_remove_player(username: str, gamemode: Optional[str] = None) -> Dict[str, Any]:
    """Remove a player from the tierlist (admin only)"""
    if not WEBSITE_URL:
        return {"status": 0, "data": {"error": "WEBSITE_URL not set"}}

    url = f"{WEBSITE_URL}/api/tests/remove"
    payload = {
        "username": username,
    }

    if gamemode:
        payload["gamemode"] = gamemode

    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=_auth_headers(), timeout=timeout) as resp:
            try:
                data = await resp.json()
            except Exception:
                data = {"error": await resp.text()}
            return {"status": resp.status, "data": data}


# =========================
# BAN SYSTEM
# =========================
def _load_ban_data() -> Dict[str, Any]:
    if not os.path.exists("bans.json"):
        return {}
    try:
        with open("bans.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_ban_data(data: Dict[str, Any]) -> None:
    with open("bans.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_player_banned(username: str) -> bool:
    """Check if a player is banned and if the ban has expired."""
    data = _load_ban_data()
    ban_info = data.get(username.lower())
    if not ban_info:
        return False

    # Check if ban has expired
    expires_at = ban_info.get("expires_at", 0)
    if expires_at > 0 and time.time() > expires_at:
        # Ban expired, remove it
        data.pop(username.lower(), None)
        _save_ban_data(data)
        return False

    return True


def get_ban_info(username: str) -> Optional[Dict[str, Any]]:
    """Get ban info for a player. Returns None if not banned or ban expired."""
    data = _load_ban_data()
    ban_info = data.get(username.lower())
    if not ban_info:
        return None

    expires_at = ban_info.get("expires_at", 0)
    if expires_at > 0 and time.time() > expires_at:
        data.pop(username.lower(), None)
        _save_ban_data(data)
        return None

    return ban_info


def ban_player(username: str, days: int, reason: str = "") -> None:
    """Ban a player for a specified number of days. Use days=0 for permanent ban."""
    data = _load_ban_data()
    expires_at = 0 if days == 0 else time.time() + (days * 24 * 60 * 60)
    data[username.lower()] = {
        "username": username,
        "reason": reason,
        "banned_at": time.time(),
        "expires_at": expires_at,
        "permanent": days == 0
    }
    _save_ban_data(data)


def unban_player(username: str) -> bool:
    """Unban a player. Returns True if they were banned and are now unbanned."""
    data = _load_ban_data()
    if username.lower() in data:
        data.pop(username.lower(), None)
        _save_ban_data(data)
        return True
    return False


# =========================
# PERMISSIONS
# =========================
def is_staff_member(member: any) -> bool:
    # Check debug allowed users first (hardcoded for testing)
    if DEBUG_ALLOWED_USERS and member.id in DEBUG_ALLOWED_USERS:
        return True
    # Check debug allowed roles (hardcoded for testing)
    if DEBUG_ALLOWED_ROLES:
        for role_id in DEBUG_ALLOWED_ROLES:
            if any(r.id == role_id for r in member.roles):
                return True
    # Check specific user IDs first
    if ALLOWED_USER_IDS and member.id in ALLOWED_USER_IDS:
        return True
    if member.guild_permissions.administrator:
        return True
    if STAFF_ROLE_ID and any(r.id == STAFF_ROLE_ID for r in member.roles):
        return True
    # Check extra staff role IDs
    for role_id in EXTRA_STAFF_ROLE_IDS:
        if role_id and any(r.id == role_id for r in member.roles):
            return True
    return False


# =========================
# LINK SYSTEM (Discord -> Minecraft Account Linking) - Database Version
# =========================

# JSON fallback functions for linked accounts
def _load_link_data() -> Dict[str, Any]:
    if not os.path.exists("links.json"):
        return {}
    try:
        with open("links.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_link_data(data: Dict[str, Any]) -> None:
    with open("links.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def get_linked_minecraft_name_async(discord_id: int) -> Optional[str]:
    """Get the Minecraft name linked to a Discord user (async)"""
    # Try Supabase REST API first
    if USE_SUPABASE_API:
        try:
            results = await supabase_select("linked_accounts", {"discord_id": str(discord_id)})
            if results:
                print(f"FOUND: Linked minecraft {results[0]['minecraft_name']} for discord {discord_id} (Supabase API)")
                return results[0]['minecraft_name']
            else:
                print(f"NOT FOUND in Supabase: No link for discord {discord_id}")
        except Exception as e:
            print(f"Error getting from Supabase: {e}")

    # Try PostgreSQL pool
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT minecraft_name FROM linked_accounts WHERE discord_id = $1",
                    discord_id
                )
                if row:
                    print(f"FOUND: Linked minecraft {row['minecraft_name']} for discord {discord_id} (DB)")
                else:
                    print(f"NOT FOUND in DB: No link for discord {discord_id}")
                return row['minecraft_name'] if row else None
        except Exception as e:
            print(f"Error getting from database: {e}")

    # Fallback to JSON
    print(f"FALLBACK: Checking JSON for discord {discord_id}")
    data = _load_link_data()
    result = data.get(str(discord_id))
    if result:
        print(f"FOUND: Linked minecraft {result} for discord {discord_id} (JSON)")
    else:
        print(f"NOT FOUND: No link for discord {discord_id} (JSON)")
    return result


async def link_minecraft_account_async(discord_id: int, minecraft_name: str) -> bool:
    """Link a Discord user to a Minecraft name (async)"""
    # Try Supabase REST API first
    if USE_SUPABASE_API:
        try:
            success = await supabase_upsert("linked_accounts", {
                "discord_id": str(discord_id),
                "minecraft_name": minecraft_name
            })
            if success:
                print(f"SUCCESS: Linked discord {discord_id} to minecraft {minecraft_name} (Supabase API)")
                return True
        except Exception as e:
            print(f"Error linking to Supabase: {e}")

    # Try PostgreSQL pool
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO linked_accounts (discord_id, minecraft_name, linked_at)
                    VALUES ($1, $2, NOW())
                    ON CONFLICT (discord_id) DO UPDATE SET
                        minecraft_name = EXCLUDED.minecraft_name,
                        linked_at = NOW()
                    """,
                    discord_id, minecraft_name
                )
            print(f"SUCCESS: Linked discord {discord_id} to minecraft {minecraft_name} (DB)")
            return True
        except Exception as e:
            print(f"Error linking to database: {e}")

    # Fallback to JSON
    print(f"FALLBACK: Saving to JSON for discord {discord_id}")
    data = _load_link_data()
    data[str(discord_id)] = minecraft_name
    _save_link_data(data)
    print(f"SUCCESS: Linked discord {discord_id} to minecraft {minecraft_name} (JSON)")
    return True


async def unlink_minecraft_account_async(discord_id: int) -> bool:
    """Unlink a Discord user from their Minecraft name. Returns True if unlinked."""
    # Try Supabase REST API first
    if USE_SUPABASE_API:
        try:
            success = await supabase_delete("linked_accounts", {"discord_id": str(discord_id)})
            if success:
                print(f"SUCCESS: Unlinked discord {discord_id} (Supabase API)")
                return True
        except Exception as e:
            print(f"Error unlinking from Supabase: {e}")

    if not db_pool:
        return False
    try:
        async with db_pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM linked_accounts WHERE discord_id = $1",
                discord_id
            )
        return result == "DELETE 1"
    except Exception as e:
        print(f"Error unlinking minecraft account: {e}")
        return False


async def get_discord_by_minecraft_async(minecraft_name: str) -> Optional[int]:
    """Get Discord ID by linked Minecraft name (async)"""
    # Try Supabase REST API first
    if USE_SUPABASE_API:
        try:
            results = await supabase_select("linked_accounts", {"minecraft_name": minecraft_name})
            if results:
                return int(results[0]['discord_id'])
        except Exception as e:
            print(f"Error getting discord by minecraft from Supabase: {e}")

    if not db_pool:
        return None
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT discord_id FROM linked_accounts WHERE LOWER(minecraft_name) = LOWER($1)",
                minecraft_name
            )
            return row['discord_id'] if row else None
    except Exception as e:
        print(f"Error getting discord by minecraft: {e}")
        return None


# Synchronous versions that fall back to JSON if DB not available
def get_linked_minecraft_name(discord_id: int) -> Optional[str]:
    """Get the Minecraft name linked to a Discord user (sync wrapper)"""
    # Try Supabase REST API
    if USE_SUPABASE_API:
        try:
            results = supabase_select_sync("linked_accounts", {"discord_id": str(discord_id)})
            if results:
                print(f"FOUND: Linked minecraft {results[0]['minecraft_name']} for discord {discord_id} (Supabase API)")
                return results[0]['minecraft_name']
        except Exception as e:
            print(f"Error getting from Supabase: {e}")

    if db_pool:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're in an async context, we need to schedule this
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, get_linked_minecraft_name_async(discord_id))
                    return future.result()
            else:
                return asyncio.run(get_linked_minecraft_name_async(discord_id))
        except:
            pass
    # Fallback to JSON
    data = _load_link_data()
    return data.get(str(discord_id))


def link_minecraft_account(discord_id: int, minecraft_name: str) -> None:
    """Link a Discord user to a Minecraft name (sync wrapper)"""
    # Try Supabase REST API
    if USE_SUPABASE_API:
        try:
            success = supabase_insert_sync("linked_accounts", {
                "discord_id": str(discord_id),
                "minecraft_name": minecraft_name
            })
            if success:
                print(f"SUCCESS: Linked discord {discord_id} to minecraft {minecraft_name} (Supabase API)")
                return
        except Exception as e:
            print(f"Error linking to Supabase: {e}")

    if db_pool:
        try:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, link_minecraft_account_async(discord_id, minecraft_name))
                if future.result():
                    return
        except:
            pass
    # Fallback to JSON
    data = _load_link_data()
    data[str(discord_id)] = minecraft_name
    _save_link_data(data)


def unlink_minecraft_account(discord_id: int) -> bool:
    """Unlink a Discord user from their Minecraft name. Returns True if unlinked."""
    # Try Supabase REST API
    if USE_SUPABASE_API:
        try:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, supabase_delete("linked_accounts", {"discord_id": str(discord_id)}))
                if future.result():
                    print(f"SUCCESS: Unlinked discord {discord_id} (Supabase API)")
                    return True
        except Exception as e:
            print(f"Error unlinking from Supabase: {e}")

    if db_pool:
        try:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, unlink_minecraft_account_async(discord_id))
                if future.result():
                    return True
        except:
            pass
    # Fallback to JSON
    data = _load_link_data()
    if str(discord_id) in data:
        del data[str(discord_id)]
        _save_link_data(data)
        return True
    return False


def get_discord_by_minecraft(minecraft_name: str) -> Optional[int]:
    """Get Discord ID by linked Minecraft name (sync wrapper)"""
    # Try Supabase REST API
    if USE_SUPABASE_API:
        try:
            results = supabase_select_sync("linked_accounts", {"minecraft_name": minecraft_name})
            if results:
                return int(results[0]['discord_id'])
        except Exception as e:
            print(f"Error getting discord by minecraft from Supabase: {e}")

    if db_pool:
        try:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, get_discord_by_minecraft_async(minecraft_name))
                return future.result()
        except:
            pass
    # Fallback to JSON
    data = _load_link_data()
    for discord_id, mc_name in data.items():
        if mc_name.lower() == minecraft_name.lower():
            return int(discord_id)
    return None


# =========================
# PENDING LINK CODES (Discord -> Minecraft linking with code)
# =========================

LINK_CODE_LENGTH = 8  # 6-8 characters
LINK_CODE_EXPIRY_MINUTES = 10


# =========================
# PENDING CODES - Database versions
# =========================

async def generate_link_code_async(discord_id: int) -> str:
    """Generate a new link code for a Discord user (async)"""
    # Generate random alphanumeric code
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=LINK_CODE_LENGTH))

    # Try Supabase REST API first
    if USE_SUPABASE_API:
        try:
            expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=LINK_CODE_EXPIRY_MINUTES)
            # Delete any existing pending codes for this user
            await supabase_delete("pending_codes", {"discord_id": str(discord_id)})
            # Insert new code
            success = await supabase_insert("pending_codes", {
                "discord_id": str(discord_id),
                "code": code.upper(),
                "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "expires_at": expires_at.isoformat(),
                "used": False
            })
            if success:
                print(f"Generated link code {code} for discord {discord_id} (Supabase API)")
                return code
        except Exception as e:
            print(f"Error generating link code in Supabase: {e}")

    if db_pool:
        try:
            expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=LINK_CODE_EXPIRY_MINUTES)
            async with db_pool.acquire() as conn:
                # Delete any existing pending codes for this user
                await conn.execute(
                    "DELETE FROM pending_codes WHERE discord_id = $1",
                    discord_id
                )
                # Insert new code
                await conn.execute(
                    "INSERT INTO pending_codes (discord_id, code, created_at, expires_at, used) VALUES ($1, $2, NOW(), $3, FALSE)",
                    discord_id, code, expires_at
                )
            return code
        except Exception as e:
            print(f"Error generating link code: {e}")

    # Fallback to JSON
    data = _load_pending_link_codes()
    # Remove any existing codes for this user
    data = {k: v for k, v in data.items() if v.get("discord_id") != discord_id}
    data[code] = {
        "discord_id": discord_id,
        "expires_at": time.time() + (LINK_CODE_EXPIRY_MINUTES * 60)
    }
    _save_pending_link_codes(data)
    return code


async def verify_link_code_async(code: str) -> Optional[int]:
    """Verify a link code and return Discord ID if valid, None if invalid/expired (async)"""
    # Try Supabase REST API first
    if USE_SUPABASE_API:
        try:
            # First, get the code and check if valid
            results = await supabase_select("pending_codes", {"code": code.upper(), "used": "false"})
            if results:
                # Check if not expired
                expires_at = datetime.datetime.fromisoformat(results[0]['expires_at'].replace('Z', '+00:00'))
                if expires_at > datetime.datetime.now(datetime.timezone.utc):
                    discord_id = int(results[0]['discord_id'])
                    # Mark code as used
                    await supabase_update("pending_codes", {"used": True}, {"code": code.upper()})
                    print(f"Verified link code {code} for discord {discord_id} (Supabase API)")
                    return discord_id
                else:
                    print(f"Link code {code} expired")
            return None
        except Exception as e:
            print(f"Error verifying link code in Supabase: {e}")

    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT discord_id FROM pending_codes WHERE UPPER(code) = UPPER($1) AND used = FALSE AND expires_at > NOW()",
                    code
                )
                if row:
                    # Mark code as used
                    await conn.execute(
                        "UPDATE pending_codes SET used = TRUE WHERE UPPER(code) = UPPER($1)",
                        code
                    )
                    return row['discord_id']
                return None
        except Exception as e:
            print(f"Error verifying link code: {e}")

    # Fallback to JSON
    return verify_link_code(code)


async def get_pending_link_code_async(discord_id: int) -> Optional[str]:
    """Get existing pending code for a Discord user if any (async)"""
    # Try Supabase REST API first
    if USE_SUPABASE_API:
        try:
            # Get codes for this discord_id that are not used and not expired
            results = await supabase_select("pending_codes", {"discord_id": str(discord_id)})
            if results:
                for row in results:
                    if not row.get('used', False):
                        expires_at = datetime.datetime.fromisoformat(row['expires_at'].replace('Z', '+00:00'))
                        if expires_at > datetime.datetime.now(datetime.timezone.utc):
                            return row['code']
            return None
        except Exception as e:
            print(f"Error getting pending link code from Supabase: {e}")


async def validate_link_code_for_user(discord_id: int, code: str) -> bool:
    """Check if a code belongs to the specified user (async)"""
    if USE_SUPABASE_API:
        try:
            results = await supabase_select("pending_codes", {"discord_id": str(discord_id), "code": code})
            if results:
                for row in results:
                    if not row.get('used', False):
                        expires_at = datetime.datetime.fromisoformat(row['expires_at'].replace('Z', '+00:00'))
                        if expires_at > datetime.datetime.now(datetime.timezone.utc):
                            return True
            return False
        except Exception as e:
            print(f"Error validating link code from Supabase: {e}")
            return False
    return False

    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT code FROM pending_codes WHERE discord_id = $1 AND used = FALSE AND expires_at > NOW()",
                    discord_id
                )
                return row['code'] if row else None
        except Exception as e:
            print(f"Error getting pending link code: {e}")

    # Fallback to JSON
    return get_pending_link_code(discord_id)


# Synchronous fallbacks
def _load_pending_link_codes() -> Dict[str, Any]:
    if not os.path.exists("pending_links.json"):
        return {}
    try:
        with open("pending_links.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_pending_link_codes(data: Dict[str, Any]) -> None:
    with open("pending_links.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def generate_link_code(discord_id: int) -> str:
    """Generate a new link code for a Discord user"""
    # Generate random alphanumeric code
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=LINK_CODE_LENGTH))

    # Store with expiry time
    data = _load_pending_link_codes()
    data[code] = {
        "discord_id": discord_id,
        "expires_at": time.time() + (LINK_CODE_EXPIRY_MINUTES * 60)
    }
    _save_pending_link_codes(data)

    return code


def verify_link_code(code: str) -> Optional[int]:
    """Verify a link code and return Discord ID if valid, None if invalid/expired"""
    data = _load_pending_link_codes()

    code_info = data.get(code.upper())
    if not code_info:
        return None

    # Check if expired
    if time.time() > code_info.get("expires_at", 0):
        # Remove expired code
        data.pop(code.upper(), None)
        _save_pending_link_codes(data)
        return None

    discord_id = code_info.get("discord_id")
    # Remove used code
    data.pop(code.upper(), None)
    _save_pending_link_codes(data)

    return discord_id


def get_pending_link_code(discord_id: int) -> Optional[str]:
    """Get existing pending code for a Discord user if any"""
    data = _load_pending_link_codes()
    for code, info in data.items():
        if info.get("discord_id") == discord_id:
            # Check if not expired
            if time.time() < info.get("expires_at", 0):
                return code
    return None


# =========================
# MINECRAFT VERIFICATION API
# =========================
async def check_minecraft_verification(discord_id: int) -> Dict[str, Any]:
    """Check if a Discord user is verified on the Minecraft server"""
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{MINECRAFT_API_URL}/api/verify/minecraft/{discord_id}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {"verified": False, "error": f"API returned {response.status}"}
    except Exception as e:
        return {"verified": False, "error": str(e)}


async def is_minecraft_verified(discord_id: int) -> bool:
    """Quick check if a Discord user is verified on Minecraft"""
    try:
        result = await check_minecraft_verification(discord_id)
        return result.get("verified", False)
    except Exception:
        return False