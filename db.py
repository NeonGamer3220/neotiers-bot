import os
import json
import time
import asyncio
import datetime
import random
import string
from typing import Dict, Any, Optional, List

import aiohttp
import asyncpg

from constants import (
    DISCORD_TOKEN,
    WEBSITE_URL,
    BOT_API_KEY,
    MINECRAFT_API_URL,
    DATA_FILE,
    LINK_CODE_LENGTH,
    LINK_CODE_EXPIRY_MINUTES,
    COOLDOWN_SECONDS,
    HTTP_TIMEOUT_SECONDS,
    APRIL_FOOLS_MODE,
    get_funny_rank,
    get_april_fools_message,
    get_gamemode_display_name,
    normalize_gamemode,
    POINTS,
    STAFF_ROLE_ID,
    EXTRA_STAFF_ROLE_IDS,
    ALLOWED_USER_IDS,
    DEBUG_ALLOWED_USERS,
    DEBUG_ALLOWED_ROLES,
    USE_SUPABASE_API,
    SUPABASE_URL,
    SUPABASE_KEY,
)


# Define http_session at module level (will be set by main)
http_session = None

SUPABASE_PG_URL = os.getenv("SUPABASE_PG_URL", "")

db_pool: Optional[asyncpg.Pool] = None
supabase_headers: Dict[str, str] = {}


async def init_db():
    global db_pool, supabase_headers

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

    DB_CONNECTION_STRING = DATABASE_URL or SUPABASE_PG_URL
    if not DB_CONNECTION_STRING:
        print("WARNING: No database configured, linked accounts will not be persisted!")
        return

    try:
        connection_str = DB_CONNECTION_STRING
        if connection_str.startswith("postgresql://"):
            connection_str = connection_str.replace("postgresql://", "postgres://", 1)

        print(f"Connecting to database: {connection_str[:50]}...")
        db_pool = await asyncpg.create_pool(connection_str, min_size=1, max_size=5)

        async with db_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS linked_accounts (
                    id SERIAL PRIMARY KEY,
                    discord_id BIGINT NOT NULL UNIQUE,
                    minecraft_name VARCHAR(255) NOT NULL,
                    linked_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

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

            await conn.execute("CREATE INDEX IF NOT EXISTS idx_linked_discord ON linked_accounts(discord_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_linked_minecraft ON linked_accounts(minecraft_name)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_pending_code ON pending_codes(code)")

        print("Database initialized successfully!")
    except Exception as e:
        print(f"Failed to initialize database: {e}")
        db_pool = None


async def close_db():
    global db_pool
    if db_pool:
        await db_pool.close()


# =========================
# Supabase REST API Helpers
# =========================

async def supabase_select(table: str, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
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
                    print(f"Supabase upsert error: {await resp.text()}")
                    return False
    except Exception as e:
        print(f"Supabase upsert exception: {e}")
        return False


async def supabase_update(table: str, data: Dict[str, Any], filters: Dict[str, Any]) -> bool:
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
                    print(f"Supabase update error: {await resp.text()}")
                    return False
    except Exception as e:
        print(f"Supabase update exception: {e}")
        return False


async def supabase_delete(table: str, filters: Dict[str, Any]) -> bool:
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
                    print(f"Supabase delete error: {await resp.text()}")
                    return False
    except Exception as e:
        print(f"Supabase delete exception: {e}")
        return False


def supabase_select_sync(table: str, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
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


# =========================
# LINK SYSTEM (Discord -> Minecraft Account Linking) - Database Version
# =========================

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
    if USE_SUPABASE_API:
        try:
            results = await supabase_select("linked_accounts", {"discord_id": str(discord_id)})
            if results:
                print(f"FOUND: Linked minecraft {results[0]['minecraft_name']} for discord {discord_id} (Supabase API)")
                return results[0]['minecraft_name']
        except Exception as e:
            print(f"Error getting from Supabase: {e}")

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

    data = _load_link_data()
    result = data.get(str(discord_id))
    if result:
        print(f"FOUND: Linked minecraft {result} for discord {discord_id} (JSON)")
    else:
        print(f"NOT FOUND: No link for discord {discord_id} (JSON)")
    return result


async def link_minecraft_account_async(discord_id: int, minecraft_name: str) -> bool:
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

    data = _load_link_data()
    data[str(discord_id)] = minecraft_name
    _save_link_data(data)
    print(f"SUCCESS: Linked discord {discord_id} to minecraft {minecraft_name} (JSON)")
    return True


async def unlink_minecraft_account_async(discord_id: int) -> bool:
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


def get_linked_minecraft_name(discord_id: int) -> Optional[str]:
    if USE_SUPABASE_API:
        try:
            results = supabase_select_sync("linked_accounts", {"discord_id": str(discord_id)})
            if results:
                return results[0]['minecraft_name']
        except Exception as e:
            print(f"Error getting from Supabase: {e}")

    if db_pool:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, get_linked_minecraft_name_async(discord_id))
                    return future.result()
            else:
                return asyncio.run(get_linked_minecraft_name_async(discord_id))
        except:
            pass
    data = _load_link_data()
    return data.get(str(discord_id))


def link_minecraft_account(discord_id: int, minecraft_name: str) -> None:
    if USE_SUPABASE_API:
        try:
            success = supabase_insert_sync("linked_accounts", {
                "discord_id": str(discord_id),
                "minecraft_name": minecraft_name
            })
            if success:
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
    data = _load_link_data()
    data[str(discord_id)] = minecraft_name
    _save_link_data(data)


def unlink_minecraft_account(discord_id: int) -> bool:
    if USE_SUPABASE_API:
        try:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, supabase_delete("linked_accounts", {"discord_id": str(discord_id)}))
                if future.result():
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
    data = _load_link_data()
    if str(discord_id) in data:
        del data[str(discord_id)]
        _save_link_data(data)
        return True
    return False


def get_discord_by_minecraft(minecraft_name: str) -> Optional[int]:
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
    data = _load_link_data()
    for discord_id, mc_name in data.items():
        if mc_name.lower() == minecraft_name.lower():
            return int(discord_id)
    return None


# =========================
# PENDING LINK CODES (Database versions)
# =========================

async def generate_link_code_async(discord_id: int) -> str:
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=LINK_CODE_LENGTH))

    if USE_SUPABASE_API:
        try:
            expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=LINK_CODE_EXPIRY_MINUTES)
            await supabase_delete("pending_codes", {"discord_id": str(discord_id)})
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
                await conn.execute(
                    "DELETE FROM pending_codes WHERE discord_id = $1",
                    discord_id
                )
                await conn.execute(
                    "INSERT INTO pending_codes (discord_id, code, created_at, expires_at, used) VALUES ($1, $2, NOW(), $3, FALSE)",
                    discord_id, code, expires_at
                )
            return code
        except Exception as e:
            print(f"Error generating link code: {e}")

    # Fallback to JSON
    data = _load_pending_link_codes()
    data = {k: v for k, v in data.items() if v.get("discord_id") != discord_id}
    data[code] = {
        "discord_id": discord_id,
        "expires_at": time.time() + (LINK_CODE_EXPIRY_MINUTES * 60)
    }
    _save_pending_link_codes(data)
    return code


async def verify_link_code_async(code: str) -> Optional[int]:
    if USE_SUPABASE_API:
        try:
            results = await supabase_select("pending_codes", {"code": code.upper(), "used": "false"})
            if results:
                expires_at = datetime.datetime.fromisoformat(results[0]['expires_at'].replace('Z', '+00:00'))
                if expires_at > datetime.datetime.now(datetime.timezone.utc):
                    discord_id = int(results[0]['discord_id'])
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
                    await conn.execute(
                        "UPDATE pending_codes SET used = TRUE WHERE UPPER(code) = UPPER($1)",
                        code
                    )
                    return row['discord_id']
                return None
        except Exception as e:
            print(f"Error verifying link code: {e}")

    return verify_link_code(code)


async def get_pending_link_code_async(discord_id: int) -> Optional[str]:
    if USE_SUPABASE_API:
        try:
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
    return None


async def validate_link_code_for_user(discord_id: int, code: str) -> bool:
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

    return get_pending_link_code(discord_id)


# =========================
# Synchronous fallbacks
# =========================

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
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=LINK_CODE_LENGTH))
    data = _load_pending_link_codes()
    data[code] = {
        "discord_id": discord_id,
        "expires_at": time.time() + (LINK_CODE_EXPIRY_MINUTES * 60)
    }
    _save_pending_link_codes(data)
    return code


def verify_link_code(code: str) -> Optional[int]:
    data = _load_pending_link_codes()
    code_info = data.get(code.upper())
    if not code_info:
        return None

    if time.time() > code_info.get("expires_at", 0):
        data.pop(code.upper(), None)
        _save_pending_link_codes(data)
        return None

    discord_id = code_info.get("discord_id")
    data.pop(code.upper(), None)
    _save_pending_link_codes(data)

    return discord_id


def get_pending_link_code(discord_id: int) -> Optional[str]:
    data = _load_pending_link_codes()
    for code, info in data.items():
        if info.get("discord_id") == discord_id:
            if time.time() < info.get("expires_at", 0):
                return code
    return None


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
    data = _load_ban_data()
    ban_info = data.get(username.lower())
    if not ban_info:
        return False

    expires_at = ban_info.get("expires_at", 0)
    if expires_at > 0 and time.time() > expires_at:
        data.pop(username.lower(), None)
        _save_ban_data(data)
        return False

    return True


def get_ban_info(username: str) -> Optional[Dict[str, Any]]:
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
    data = _load_ban_data()
    if username.lower() in data:
        data.pop(username.lower(), None)
        _save_ban_data(data)
        return True
    return False


# =========================
# PERMISSIONS
# =========================

def is_staff_member(member: discord.Member) -> bool:
    if DEBUG_ALLOWED_USERS and member.id in DEBUG_ALLOWED_USERS:
        return True
    if DEBUG_ALLOWED_ROLES:
        for role_id in DEBUG_ALLOWED_ROLES:
            if any(r.id == role_id for r in member.roles):
                return True
    if ALLOWED_USER_IDS and member.id in ALLOWED_USER_IDS:
        return True
    if member.guild_permissions.administrator:
        return True
    if STAFF_ROLE_ID and any(r.id == STAFF_ROLE_ID for r in member.roles):
        return True
    for role_id in EXTRA_STAFF_ROLE_IDS:
        if role_id and any(r.id == role_id for r in member.roles):
            return True
    return False


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

    try:
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        async with http_session.get(url, headers=_auth_headers(), timeout=timeout) as resp:
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
    if not WEBSITE_URL:
        return {"status": 0, "data": {"tests": []}}

    url = f"{WEBSITE_URL}/api/tests"

    try:
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        async with http_session.get(url, headers=_auth_headers(), timeout=timeout) as resp:
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


async def api_post_test(username: str, mode: str, rank: str, tester: discord.Member) -> Dict[str, Any]:
    if not WEBSITE_URL:
        return {"status": 0, "data": {"error": "WEBSITE_URL not set"}}

    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
    mode_for_api = get_gamemode_display_name(mode)

    url = f"{WEBSITE_URL}/api/tests"

    payload = {
        "username": username,
        "mode": mode_for_api,
        "rank": rank,
        "testerId": str(tester.id),
        "testerName": tester.display_name,
        "upsert": True,
        "ts": int(time.time()),
    }

    async with http_session.post(url, json=payload, headers=_auth_headers(), timeout=timeout) as resp:
        try:
            data = await resp.json()
        except Exception:
            data = {"error": await resp.text()}
        return {"status": resp.status, "data": data}


async def api_rename_player(old_name: str, new_name: str) -> Dict[str, Any]:
    if not WEBSITE_URL:
        return {"status": 0, "data": {"error": "WEBSITE_URL not set"}}

    url = f"{WEBSITE_URL}/api/tests/rename"
    payload = {
        "oldName": old_name,
        "newName": new_name,
    }

    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
    async with http_session.post(url, json=payload, headers=_auth_headers(), timeout=timeout) as resp:
        try:
            data = await resp.json()
        except Exception:
            data = {"error": await resp.text()}
        return {"status": resp.status, "data": data}


async def api_set_ban(username: str, banned: bool, expires_at: Optional[int] = None, reason: str = "") -> Dict[str, Any]:
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
    async with http_session.post(url, json=payload, headers=_auth_headers(), timeout=timeout) as resp:
        try:
            data = await resp.json()
        except Exception:
            data = {"error": await resp.text()}
        return {"status": resp.status, "data": data}


async def api_remove_player(username: str, gamemode: Optional[str] = None) -> Dict[str, Any]:
    if not WEBSITE_URL:
        return {"status": 0, "data": {"error": "WEBSITE_URL not set"}}

    url = f"{WEBSITE_URL}/api/tests/remove"
    payload = {
        "username": username,
    }

    if gamemode:
        payload["gamemode"] = gamemode

    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
    async with http_session.post(url, json=payload, headers=_auth_headers(), timeout=timeout) as resp:
        try:
            data = await resp.json()
        except Exception:
            data = {"error": await resp.text()}
        return {"status": resp.status, "data": data}


# =========================
# TIER LOOKUP
# =========================

async def get_player_tier_for_mode(discord_id: int, mode_key: str) -> str:
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
    try:
        data = _load_data()
        last = data.get("cooldowns", {}).get(str(discord_id), {}).get(mode_key, 0)
        return last > 0
    except Exception:
        return False
