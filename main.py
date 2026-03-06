import os
import json
import time
import asyncio
import datetime
import random
import string
from typing import Dict, Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

import aiohttp
from aiohttp import web

import asyncpg

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "")
db_pool: Optional[asyncpg.Pool] = None

async def init_db():
    """Initialize database connection and create tables if needed"""
    global db_pool
    if not DATABASE_URL:
        print("WARNING: DATABASE_URL not set, linked accounts will not be persisted!")
        return
    
    try:
        db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
        
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
# ENV / CONFIG
# =========================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
STAFF_ROLE_ID = int(os.getenv("STAFF_ROLE_ID", "0"))
TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID", "0"))

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
    "LT3": 5, "HT3": 6,
    "LT2": 7, "HT2": 8,
    "LT1": 9, "HT1": 10,
}


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
    if not db_pool:
        return None
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT minecraft_name FROM linked_accounts WHERE discord_id = $1",
                discord_id
            )
            return row['minecraft_name'] if row else None
    except Exception as e:
        print(f"Error getting linked minecraft name: {e}")
        return None


async def link_minecraft_account_async(discord_id: int, minecraft_name: str) -> bool:
    """Link a Discord user to a Minecraft name (async)"""
    if not db_pool:
        return False
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
        return True
    except Exception as e:
        print(f"Error linking minecraft account: {e}")
        return False


async def unlink_minecraft_account_async(discord_id: int) -> bool:
    """Unlink a Discord user from their Minecraft name. Returns True if unlinked."""
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
    """Get Discord ID by linked Minecraft name"""
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
def is_staff_member(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    if STAFF_ROLE_ID and any(r.id == STAFF_ROLE_ID for r in member.roles):
        return True
    return False


# =========================
# DISCORD BOT
# =========================
intents = discord.Intents.default()
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
http_session: Optional[aiohttp.ClientSession] = None


# =========================
# HEALTH SERVER (Railway)
# =========================
async def start_health_server():
    app = web.Application()

    async def health(_request):
        return web.Response(text="ok")

    # API endpoint for Minecraft link code verification
    async def verify_link(request):
        # Skip auth check entirely for now - allow all requests
        
        # Get code from query params
        code = request.query.get("code", "")
        minecraft_name = request.query.get("minecraft", "")
        
        if not code or not minecraft_name:
            return web.json_response({"success": False, "error": "Missing code or minecraft parameter"}, status=400)
        
        # Verify the code
        discord_id = await verify_link_code_async(code.upper())
        
        if discord_id is None:
            return web.json_response({"success": False, "error": "Invalid or expired code"}, status=400)
        
        # Link the Minecraft account to the Discord account
        await link_minecraft_account_async(discord_id, minecraft_name)
        
        # Send confirmation DM to the user
        try:
            user = await bot.fetch_user(discord_id)
            if user:
                embed = discord.Embed(
                    title="✅ Összekapcsolás sikeres!",
                    description=f"A Discord fiókod össze lett kapcsolva a **Minecraft** fiókkal!\n\n"
                               f"**Minecraft név:** `{minecraft_name}`\n"
                               f"**Összekapcsolva:** Örökre!",
                    color=discord.Color.green()
                )
                embed.set_footer(text="Most már használhatod a tierlistát!")
                await user.send(embed=embed)
        except Exception as e:
            print(f"Could not send DM to user: {e}")
        
        return web.json_response({
            "success": True, 
            "discord_id": discord_id,
            "minecraft": minecraft_name
        })

    app.router.add_get("/health", health)
    app.router.add_get("/api/link/verify", verify_link)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.getenv("PORT", "8080"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Health server running on :{port}")


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

    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
    async with http_session.get(url, headers=_auth_headers(), timeout=timeout) as resp:
        try:
            data = await resp.json()
        except Exception:
            data = {"error": await resp.text()}
        return {"status": resp.status, "data": data}


async def api_post_test(username: str, mode: str, rank: str, tester: discord.Member) -> Dict[str, Any]:
    if not WEBSITE_URL:
        return {"status": 0, "data": {"error": "WEBSITE_URL not set"}}

    url = f"{WEBSITE_URL}/api/tests"
    payload = {
        "username": username,
        "mode": mode,
        "rank": rank,
        "testerId": str(tester.id),
        "testerName": tester.display_name,
        "upsert": True,
        "ts": int(time.time()),
    }

    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
    async with http_session.post(url, json=payload, headers=_auth_headers(), timeout=timeout) as resp:
        try:
            data = await resp.json()
        except Exception:
            data = {"error": await resp.text()}
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
    async with http_session.post(url, json=payload, headers=_auth_headers(), timeout=timeout) as resp:
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
    async with http_session.post(url, json=payload, headers=_auth_headers(), timeout=timeout) as resp:
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
    async with http_session.post(url, json=payload, headers=_auth_headers(), timeout=timeout) as resp:
        try:
            data = await resp.json()
        except Exception:
            data = {"error": await resp.text()}
        return {"status": resp.status, "data": data}


# =========================
# UI VIEWS
# =========================
class CloseTicketView(discord.ui.View):
    def __init__(self, owner_id: int, mode_key: str):
        super().__init__(timeout=None)
        self.owner_id = owner_id
        self.mode_key = mode_key

    @discord.ui.button(label="Ticket zárása", style=discord.ButtonStyle.danger, custom_id="neotiers_close_ticket")
    async def close(self, interaction: discord.Interaction, _button: discord.ui.Button):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("Hiba: ez nem szövegcsatorna.", ephemeral=True)
            return

        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("Hiba: member not found.", ephemeral=True)
            return

        # Get owner_id from channel topic (stored when ticket was created)
        topic = channel.topic or ""
        owner_id = 0
        if "owner=" in topic:
            try:
                owner_id = int(topic.split("owner=")[1].split("|")[0].strip())
            except (ValueError, IndexError):
                owner_id = 0

        # Allow both ticket owner AND staff to close
        if member.id != owner_id and not is_staff_member(member):
            await interaction.response.send_message("Nincs jogosultságod a ticket zárásához.", ephemeral=True)
            return

        await interaction.response.send_message("✅ Ticket zárása... 3 mp múlva törlöm a csatornát.", ephemeral=True)

        # Get owner_id and mode_key from channel topic
        topic = channel.topic or ""
        owner_id = 0
        mode_key = ""
        if "owner=" in topic:
            try:
                owner_id = int(topic.split("owner=")[1].split("|")[0].strip())
            except (ValueError, IndexError):
                owner_id = 0
        if "mode=" in topic:
            try:
                mode_key = topic.split("mode=")[1].strip()
            except IndexError:
                mode_key = ""

        set_last_closed(owner_id, mode_key, time.time())
        set_open_ticket_channel_id(owner_id, mode_key, None)

        await asyncio.sleep(3)
        try:
            await channel.delete(reason="NeoTiers ticket closed")
        except discord.Forbidden:
            try:
                await channel.send("❌ Nem tudom törölni a csatornát (Missing Permissions). Add a botnak **Csatornák kezelése** jogot + a kategórián is.")
            except Exception:
                pass
        except Exception:
            pass


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for label, mode_key, _rid in TICKET_TYPES:
            self.add_item(TicketButton(label=label, mode_key=mode_key))


class TicketButton(discord.ui.Button):
    def __init__(self, label: str, mode_key: str):
        super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id=f"neotiers_ticket_{mode_key}")
        self.mode_key = mode_key

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        member = interaction.user

        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message("Hiba: guild/member nem elérhető.", ephemeral=True)
            return

        # Check if user has a linked Minecraft account
        linked_minecraft = get_linked_minecraft_name(member.id)
        if not linked_minecraft:
            await interaction.response.send_message(
                "❌ **Nincs összekapcsolva a Minecraft fiókod!**\n\n"
                "Használd a `/link` parancsot a Discordban, majd `/link <kód>` a Minecraftban, "
                "hogy összekapcsold a fiókodat. Csak azok hozhatnak létre ticketet, akik összekapcsolták a fiókjukat!",
                ephemeral=True
            )
            return

        # Check if player is banned from testing
        # We need to check using the Discord username as the tierlist name
        # The tierlist name is the Minecraft name, not Discord name
        # We'll check both: first try Minecraft name from nickname/display name, then Discord name
        
        # For now, check the website for ban status using the Discord name as fallback
        # The user should ideally set their Minecraft name in their Discord nickname
        player_name = member.display_name
        if member.nick:
            player_name = member.nick
            
        # Try to get ban status from website
        if WEBSITE_URL:
            try:
                url = f"{WEBSITE_URL}/api/tests/ban?username={player_name}"
                timeout = aiohttp.ClientTimeout(total=5)
                async with http_session.get(url, headers=_auth_headers(), timeout=timeout) as resp:
                    if resp.status == 200:
                        ban_data = await resp.json()
                        if ban_data.get("banned"):
                            reason = ban_data.get("reason", "")
                            await interaction.response.send_message(
                                f"❌ Ki vagy tiltva a tesztelésből!\n" +
                                (f"**Ok:** {reason}" if reason else ""),
                                ephemeral=True
                            )
                            return
            except Exception:
                pass  # If ban check fails, continue (fail open)

        left = cooldown_left(member.id, self.mode_key)
        if left > 0:
            days = left // (24 * 3600)
            hours = (left % (24 * 3600)) // 3600
            await interaction.response.send_message(
                f"⏳ **Cooldown**: ebből a játékmódból ({self.mode_key}) csak **{days} nap {hours} óra** múlva nyithatsz új ticketet.",
                ephemeral=True
            )
            return

        existing_channel_id = get_open_ticket_channel_id(member.id, self.mode_key)
        if existing_channel_id:
            ch = guild.get_channel(existing_channel_id)
            if ch:
                await interaction.response.send_message("Van már ticketed ebből a játékmódból. 🔒", ephemeral=True)
                return
            else:
                set_open_ticket_channel_id(member.id, self.mode_key, None)

        category = guild.get_channel(TICKET_CATEGORY_ID) if TICKET_CATEGORY_ID else None
        if TICKET_CATEGORY_ID and not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(
                "❌ Ticket kategória rossz / nem kategória. Állítsd be jól a TICKET_CATEGORY_ID-t.",
                ephemeral=True
            )
            return

        staff_role = guild.get_role(STAFF_ROLE_ID) if STAFF_ROLE_ID else None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True, manage_channels=True
            )

        safe_name = member.name.lower().replace(" ", "-")
        channel_name = f"{self.mode_key}-{safe_name}"

        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category if isinstance(category, discord.CategoryChannel) else None,
                overwrites=overwrites,
                topic=f"NeoTiers ticket | owner={member.id} | mode={self.mode_key}",
                reason="NeoTiers ticket created"
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Nincs jogom csatornát létrehozni. Add a botnak **Csatornák kezelése** jogot (és a kategórián is).",
                ephemeral=True
            )
            return

        set_open_ticket_channel_id(member.id, self.mode_key, channel.id)

        ping_role_id = None
        for _label, mk, rid in TICKET_TYPES:
            if mk == self.mode_key:
                ping_role_id = rid
                break

        ping_text = f"<@&{ping_role_id}>" if ping_role_id else ""

        embed = discord.Embed(
            title="Teszt kérés",
            description="Kattints egy alábbi gombra, hogy tudd tesztelni a gombon feltüntetett játékmódból.",
            color=discord.Color.blurple()
        )
        embed.add_field(name="Játékmód", value=self.mode_key, inline=True)
        embed.add_field(name="Játékos", value=member.mention, inline=True)

        await channel.send(content=ping_text, embed=embed, view=CloseTicketView(owner_id=member.id, mode_key=self.mode_key))
        await interaction.response.send_message(f"✅ Ticket létrehozva: {channel.mention}", ephemeral=True)


# =========================
# COMMANDS
# =========================
def _choices_from_list(values):
    return [app_commands.Choice(name=v, value=v) for v in values]


@app_commands.command(name="ticketpanel", description="Ticket panel üzenet kirakása.")
async def ticketpanel(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    try:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("Hiba.", ephemeral=True)
            return
        if not is_staff_member(interaction.user):
            await interaction.followup.send("Nincs jogosultságod ehhez a parancshoz.", ephemeral=True)
            return
        if interaction.channel is None:
            await interaction.followup.send("Hiba: nincs csatorna.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Teszt kérés",
            description="Kattints egy alábbi gombra, hogy tudd tesztelni a gombon feltüntetett játékmódból.",
            color=discord.Color.blurple()
        )

        await interaction.channel.send(embed=embed, view=TicketPanelView())
        await interaction.followup.send("✅ Ticket panel kirakva.", ephemeral=True)

    except discord.Forbidden:
        await interaction.followup.send("❌ Nem tudok ide írni (Missing Permissions). Adj írás jogot a botnak ebben a csatornában.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


async def autocomplete_testresult_username(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    if not WEBSITE_URL:
        return []

    try:
        url = f"{WEBSITE_URL}/api/tests"
        timeout = aiohttp.ClientTimeout(total=5)
        async with http_session.get(url, headers=_auth_headers(), timeout=timeout) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            tests = data.get("tests", [])

            # Extract unique usernames
            usernames = set()
            for t in tests:
                u = t.get("username")
                if u:
                    usernames.add(u)

            # Filter by current input
            matches = [u for u in usernames if current.lower() in u.lower()]
            return [app_commands.Choice(name=u, value=u) for u in matches[:25]]
    except Exception:
        return []


@app_commands.command(name="testresult", description="Minecraft tier teszt eredmény embed + weboldal mentés.")
@app_commands.describe(
    username="Minecraft név (ebből lesz a skin a weboldalon)",
    tester="Tesztelő (Discord user)",
    gamemode="Játékmód",
    rank="Elért rank (pl. LT3 / HT3)"
)
@app_commands.autocomplete(username=autocomplete_testresult_username)
@app_commands.choices(
    gamemode=_choices_from_list(MODE_LIST),
    rank=_choices_from_list(RANKS)
)
async def testresult(
    interaction: discord.Interaction,
    username: str,
    tester: discord.Member,
    gamemode: app_commands.Choice[str],
    rank: app_commands.Choice[str],
):
    await interaction.response.defer(ephemeral=True)

    try:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("Hiba.", ephemeral=True)
            return
        if not is_staff_member(interaction.user):
            await interaction.followup.send("Nincs jogosultságod ehhez a parancshoz.", ephemeral=True)
            return
        if interaction.channel is None:
            await interaction.followup.send("Hiba: nincs csatorna.", ephemeral=True)
            return

        mode_val = gamemode.value
        rank_val = rank.value

        # Previous rank from website (best-effort)
        prev_rank = "Unranked"
        if WEBSITE_URL:
            try:
                res = await api_get_tests(username=username, mode=mode_val)
                if res.get("status") == 200:
                    data = res.get("data", {})
                    # Handle single result (test) or list (tests)
                    test = data.get("test")
                    tests = data.get("tests", [])

                    target = test if test else (tests[0] if tests else None)

                    if target:
                        prev_rank = str(target.get("rank", "Unranked")) or "Unranked"
            except Exception:
                pass

        prev_points = POINTS.get(prev_rank, 0)
        new_points = POINTS.get(rank_val, 0)
        diff = new_points - prev_points

        # PUBLIC EMBED (everyone sees)
        skin_url = f"https://minotar.net/helm/{username}/128.png"
        embed = discord.Embed(
            title=f"{username} teszt eredménye 🏆",
            color=discord.Color.dark_grey()
        )
        embed.set_thumbnail(url=skin_url)
        embed.add_field(name="Tesztelő:", value=tester.mention, inline=False)
        embed.add_field(name="Játékmód:", value=mode_val, inline=False)
        embed.add_field(name="Minecraft név:", value=username, inline=False)
        embed.add_field(name="Előző rang:", value=prev_rank, inline=False)
        embed.add_field(name="Elért rang:", value=rank_val, inline=False)

        await interaction.channel.send(embed=embed)

        # SAVE TO WEBSITE (UPsert)
        if not WEBSITE_URL:
            await interaction.followup.send("⚠️ WEBSITE_URL nincs beállítva, nem mentem webre.", ephemeral=True)
            return

        save = await api_post_test(username=username, mode=mode_val, rank=rank_val, tester=tester)
        save_status = save.get("status")
        save_data = save.get("data")
        save_ok = (save_status == 200 or save_status == 201)

        if save_ok:
            # Set cooldown for the tested player (username)
            # We need the user ID for this. The bot doesn't know the Discord ID of the Minecraft player.
            # We can store cooldown by username instead of Discord ID.
            # BUT: we need a function to set cooldown by username.
            # Currently get_last_closed takes user_id (discord).
            # We should change the cooldown system to use Minecraft names if we can't map them to Discord IDs easily.
            # OR we can assume the ticket creator is the one being tested? No, tickets are created by players requesting tests.
            # The flow is: Player opens ticket -> Staff tests them -> Staff runs /testresult.
            # The command is run by staff. We don't know who the player is in Discord terms (unless they are in the guild).
            # Wait, we can try to find the member who created the ticket?
            # The ticket channel has a topic: topic=f"NeoTiers ticket | owner={member.id} | mode={self.mode_key}"
            # We can get the channel topic to find the owner ID!

            channel = interaction.channel
            owner_id = None
            if channel and channel.topic:
                try:
                    # Parse "owner=123456789"
                    for part in channel.topic.split(" | "):
                        if part.startswith("owner="):
                            owner_id = int(part.split("=")[1])
                            break
                except Exception:
                    pass

            if owner_id:
                set_last_closed(owner_id, mode_val, time.time())
            else:
                # Fallback: if we can't find owner, maybe it's a DM or something went wrong.
                # We can't set cooldown then.
                pass

            await interaction.followup.send(
                f"✅ Mentve + weboldal frissítve.\nElőző: **{prev_rank}** → Elért: **{rank_val}** | "
                f"{'+' if diff>=0 else ''}{diff} pont",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"⚠️ Mentés hiba a weboldal felé (status {save_status}) | {save_data}",
                ephemeral=True
            )

    except aiohttp.ClientError as e:
        await interaction.followup.send(f"⚠️ Web hiba: {type(e).__name__}: {e}", ephemeral=True)
    except asyncio.TimeoutError:
        await interaction.followup.send("⚠️ Web timeout (nem válaszolt 10 mp-en belül).", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ Nem tudok ide írni / embedet küldeni (Missing Permissions).", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


@app_commands.command(name="tierlistnamechange", description="Játékos nevének megváltoztatása a tierlistán (admin csak)")
@app_commands.describe(
    oldname="A jelenlegi név a tierlistán",
    newname="Az új név ami megjelenik a tierlistán"
)
async def tierlistnamechange(interaction: discord.Interaction, oldname: str, newname: str):
    await interaction.response.defer(ephemeral=True)

    try:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("Hiba.", ephemeral=True)
            return
        if not is_staff_member(interaction.user):
            await interaction.followup.send("Nincs jogosultságod ehhez a parancshoz.", ephemeral=True)
            return

        # Call the website API to rename the player
        if not WEBSITE_URL:
            await interaction.followup.send("⚠️ WEBSITE_URL nincs beállítva.", ephemeral=True)
            return

        result = await api_rename_player(old_name=oldname, new_name=newname)
        status = result.get("status")
        data = result.get("data", {})

        if status == 200:
            updated_count = data.get("updatedCount", 0)
            await interaction.followup.send(
                f"✅ Sikeresen átnevezve: **{oldname}** → **{newname}**\n"
                f"Frissítve: {updated_count} db bejegyzés (összes gamemód)",
                ephemeral=True
            )
        elif status == 404:
            await interaction.followup.send(
                f"❌ Játékos nem találva: **{oldname}**",
                ephemeral=True
            )
        elif status == 401 or status == 403:
            await interaction.followup.send(
                "❌ Nincs jogosultságod ehhez a parancshoz.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"⚠️ Hiba (status {status}): {data}",
                ephemeral=True
            )

    except aiohttp.ClientError as e:
        await interaction.followup.send(f"⚠️ Web hiba: {type(e).__name__}: {e}", ephemeral=True)
    except asyncio.TimeoutError:
        await interaction.followup.send("⚠️ Web timeout (nem válaszolt 10 mp-en belül).", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


@app_commands.command(name="profile", description="Megnézed egy játékos tierjeit a tierlistáról.")
@app_commands.describe(
    name="A játékos neve a tierlistán"
)
async def profile(interaction: discord.Interaction, name: str):
    await interaction.response.defer(ephemeral=False)

    try:
        if not WEBSITE_URL:
            await interaction.followup.send("⚠️ WEBSITE_URL nincs beállítva.", ephemeral=True)
            return

        # Use the new API endpoint that supports filtering by username only
        url = f"{WEBSITE_URL}/api/tests?username={name}"
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        async with http_session.get(url, headers=_auth_headers(), timeout=timeout) as resp:
            try:
                data = await resp.json()
            except Exception:
                data = {}

            if resp.status != 200:
                await interaction.followup.send(f"⚠️ Hiba a weboldal lekérésekor: {resp.status}", ephemeral=True)
                return

            tests = data.get("tests", [])

            if not tests:
                await interaction.followup.send(f"❌ Nincs találat erre a névre: **{name}**", ephemeral=False)
                return

            # Get global rank by fetching all tests and sorting
            all_url = f"{WEBSITE_URL}/api/tests"
            async with http_session.get(all_url, headers=_auth_headers(), timeout=timeout) as all_resp:
                try:
                    all_data = await all_resp.json()
                except Exception:
                    all_data = {}

            all_tests = all_data.get("tests", [])
            global_rank = None
            if all_tests:
                # Group by username and sum points
                player_totals = {}
                for t in all_tests:
                    username = t.get("username", "")
                    points = t.get("points", 0)
                    if username in player_totals:
                        player_totals[username] += points
                    else:
                        player_totals[username] = points
                
                # Sort by total points descending
                sorted_players = sorted(player_totals.items(), key=lambda x: x[1], reverse=True)
                
                # Find the player's position
                player_username = tests[0].get("username", "")
                player_total_points = player_totals.get(player_username, 0)
                
                for idx, (name, pts) in enumerate(sorted_players, 1):
                    if name == player_username:
                        global_rank = idx
                        break

            # Build embed
            embed = discord.Embed(
                title=f"{tests[0].get('username', name)} profilja",
                color=discord.Color.blurple()
            )

            # Sort by points (desc)
            tests.sort(key=lambda x: x.get("points", 0), reverse=True)

            # List modes
            mode_strs = []
            total_points = 0
            for t in tests:
                m = t.get("gamemode", "?")
                r = t.get("rank", "?")
                p = t.get("points", 0)
                total_points += p
                mode_strs.append(f"**{m}**: {r} ({p}pt)")

            embed.description = "\n".join(mode_strs)
            
            # Add rank info
            rank_info = f"**Összes pont:** {total_points}"
            if global_rank:
                rank_info += f"\n**Globális rank:** #{global_rank}"
            
            embed.add_field(name="Statisztika", value=rank_info, inline=False)

            # Skin
            skin_url = f"https://minotar.net/helm/{tests[0].get('username', name)}/128.png"
            embed.set_thumbnail(url=skin_url)

            await interaction.followup.send(embed=embed)

    except aiohttp.ClientError as e:
        await interaction.followup.send(f"⚠️ Web hiba: {type(e).__name__}: {e}", ephemeral=True)
    except asyncio.TimeoutError:
        await interaction.followup.send("⚠️ Web timeout (nem válaszolt 10 mp-en belül).", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


@app_commands.command(name="porog", description="Kiválaszt egy véletlenszerű játékost a megadott gamemodból és tierből.")
@app_commands.describe(
    gamemode="A játékmód (pl. sword, pot, smp)",
    tier="A tier (pl. ht3, lt1)"
)
@app_commands.choices(
    gamemode=_choices_from_list(MODE_LIST),
    tier=_choices_from_list(RANKS)
)
async def porog(interaction: discord.Interaction, gamemode: app_commands.Choice[str], tier: app_commands.Choice[str]):
    await interaction.response.defer(ephemeral=False)

    try:
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("Nincs jogosultságod ehhez a parancshoz.", ephemeral=True)
            return

        if not WEBSITE_URL:
            await interaction.followup.send("⚠️ WEBSITE_URL nincs beállítva.", ephemeral=True)
            return

        # Try to exclude the ticket owner
        exclude_user = None
        channel = interaction.channel
        if channel and channel.name:
            # Channel name is like "sword-username" where username is discord name
            # We can try to use this to exclude
            parts = channel.name.split("-")
            if len(parts) > 1:
                exclude_user = parts[1] # The part after the mode

        # Build URL with exclusion if we found someone
        url = f"{WEBSITE_URL}/api/tests?mode={gamemode.value}&tier={tier.value}"
        if exclude_user:
            url += f"&exclude={exclude_user}"

        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        async with http_session.get(url, headers=_auth_headers(), timeout=timeout) as resp:
            try:
                data = await resp.json()
            except Exception:
                data = {}

            if resp.status != 200:
                await interaction.followup.send(f"⚠️ Hiba a weboldal lekérésekor: {resp.status}", ephemeral=True)
                return

            player = data.get("player")

            if not player:
                await interaction.followup.send("❌ Nincs találat erre a gamemódra és tier-re.", ephemeral=False)
                return

            username = player.get("username")
            rank = player.get("rank")

            embed = discord.Embed(
                title="🎲 Sorsolt játékos",
                description=f"**{username}** ({rank})",
                color=discord.Color.gold()
            )

            skin_url = f"https://minotar.net/helm/{username}/128.png"
            embed.set_thumbnail(url=skin_url)

            await interaction.followup.send(embed=embed)

    except aiohttp.ClientError as e:
        await interaction.followup.send(f"⚠️ Web hiba: {type(e).__name__}: {e}", ephemeral=True)
    except asyncio.TimeoutError:
        await interaction.followup.send("⚠️ Web timeout (nem válaszolt 10 mp-en belül).", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


# =========================
# GLOBAL APP COMMAND ERROR HANDLER
# =========================

@app_commands.command(name="retire", description="Játékos nyugdíjazása egy gamemódban (admin csak, csak Tier 2).")
@app_commands.describe(
    name="A játékos neve a tierlistán",
    gamemode="A játékmód"
)
@app_commands.choices(
    gamemode=_choices_from_list(MODE_LIST)
)
async def retire(interaction: discord.Interaction, name: str, gamemode: app_commands.Choice[str]):
    await interaction.response.defer(ephemeral=True)

    try:
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("Nincs jogosultságod ehhez a parancshoz.", ephemeral=True)
            return

        if not WEBSITE_URL:
            await interaction.followup.send("⚠️ WEBSITE_URL nincs beállítva.", ephemeral=True)
            return

        # First, check the player's current rank to ensure they are Tier 2
        url = f"{WEBSITE_URL}/api/tests?username={name}&gamemode={gamemode.value}"
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        async with http_session.get(url, headers=_auth_headers(), timeout=timeout) as resp:
            try:
                data = await resp.json()
            except Exception:
                data = {}

            if resp.status != 200:
                await interaction.followup.send(f"⚠️ Hiba a weboldal lekérésekor: {resp.status}", ephemeral=True)
                return

            test = data.get("test")
            if not test:
                await interaction.followup.send(
                    f"❌ Játékos nem találva: **{name}** ezen a gamemódon ({gamemode.value}).",
                    ephemeral=True
                )
                return

            current_rank = test.get("rank", "")
            # Check if Tier 2
            if current_rank not in ["LT2", "HT2"]:
                await interaction.followup.send(
                    f"❌ Csak Tier 2 (LT2/HT2) játékosok nyugdíjazhatók. **{name}** jelenleg: **{current_rank}**.",
                    ephemeral=True
                )
                return

        # Call the website API to retire (upsert with R prefix)
        retire_url = f"{WEBSITE_URL}/api/tests"
        payload = {
            "username": name,
            "gamemode": gamemode.value,
            "rank": f"R{current_rank}",
            "points": POINTS.get(current_rank, 0), # Keep same points
            "retired": True
        }

        async with http_session.post(retire_url, json=payload, headers=_auth_headers(), timeout=timeout) as retire_resp:
            try:
                retire_data = await retire_resp.json()
            except Exception:
                retire_data = {}

            if retire_resp.status == 200:
                await interaction.followup.send(
                    f"✅ Sikeres nyugdíjazás! **{name}** ({gamemode.value}) most **R{current_rank}**.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"⚠️ Hiba: {retire_resp.status} - {retire_data}",
                    ephemeral=True
                )

    except aiohttp.ClientError as e:
        await interaction.followup.send(f"⚠️ Web hiba: {type(e).__name__}: {e}", ephemeral=True)
    except asyncio.TimeoutError:
        await interaction.followup.send("⚠️ Web timeout.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


@app_commands.command(name="unretire", description="Játékos visszahozása nyugdíjból (admin csak).")
@app_commands.describe(
    name="A játékos neve a tierlistán",
    gamemode="A játékmód"
)
@app_commands.choices(
    gamemode=_choices_from_list(MODE_LIST)
)
async def unretire(interaction: discord.Interaction, name: str, gamemode: app_commands.Choice[str]):
    await interaction.response.defer(ephemeral=True)

    try:
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("Nincs jogosultságod ehhez a parancshoz.", ephemeral=True)
            return

        if not WEBSITE_URL:
            await interaction.followup.send("⚠️ WEBSITE_URL nincs beállítva.", ephemeral=True)
            return

        # First, get current rank to remove R prefix
        url = f"{WEBSITE_URL}/api/tests?username={name}&gamemode={gamemode.value}"
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        async with http_session.get(url, headers=_auth_headers(), timeout=timeout) as resp:
            try:
                data = await resp.json()
            except Exception:
                data = {}

            if resp.status != 200:
                await interaction.followup.send(f"⚠️ Hiba a weboldal lekérésekor: {resp.status}", ephemeral=True)
                return

            test = data.get("test")
            if not test:
                await interaction.followup.send(
                    f"❌ Játékos nem találva: **{name}** ezen a gamemódon ({gamemode.value}).",
                    ephemeral=True
                )
                return

            current_rank = test.get("rank", "")
            if not current_rank.startswith("R"):
                await interaction.followup.send(
                    f"❌ A játékos nincs nyugdíjazva ebben a gamemódban.",
                    ephemeral=True
                )
                return

            original_rank = current_rank[1:] # Remove R prefix

        # Upsert back to original rank
        post_url = f"{WEBSITE_URL}/api/tests"
        payload = {
            "username": name,
            "gamemode": gamemode.value,
            "rank": original_rank,
            "points": POINTS.get(original_rank, 0)
        }

        async with http_session.post(post_url, json=payload, headers=_auth_headers(), timeout=timeout) as post_resp:
            try:
                post_data = await post_resp.json()
            except Exception:
                post_data = {}

            if post_resp.status == 200:
                await interaction.followup.send(
                    f"✅ Sikeres visszahozatal! **{name}** ({gamemode.value}) visszatért a tierlistára ({original_rank}).",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"⚠️ Hiba: {post_resp.status} - {post_data}",
                    ephemeral=True
                )

    except aiohttp.ClientError as e:
        await interaction.followup.send(f"⚠️ Web hiba: {type(e).__name__}: {e}", ephemeral=True)
    except asyncio.TimeoutError:
        await interaction.followup.send("⚠️ Web timeout.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


@app_commands.command(name="tierlistban", description="Játékos kitiltása a tesztelésből (admin csak).")
@app_commands.describe(
    name="A játékos neve a tierlistán",
    days="Kitiltás időtartama napokban (0 = örök ban)",
    reason="Kitiltás oka (opcionális)"
)
async def tierlistban(interaction: discord.Interaction, name: str, days: int, reason: str = ""):
    await interaction.response.defer(ephemeral=True)

    try:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("Hiba.", ephemeral=True)
            return
        if not is_staff_member(interaction.user):
            await interaction.followup.send("Nincs jogosultságod ehhez a parancshoz.", ephemeral=True)
            return

        # Check if already banned
        if is_player_banned(name):
            ban_info = get_ban_info(name)
            if ban_info:
                expires_at = ban_info.get("expires_at", 0)
                if expires_at == 0:
                    await interaction.followup.send(
                        f"❌ **{name}** már örökkitiltás alatt áll.",
                        ephemeral=True
                    )
                else:
                    from datetime import datetime
                    exp_date = datetime.fromtimestamp(expires_at)
                    await interaction.followup.send(
                        f"❌ **{name}** már kitiltva. Lejárat: {exp_date.strftime('%Y-%m-%d %H:%M')}",
                        ephemeral=True
                    )
            return

        # Ban the player in bot
        ban_player(name, days, reason)

        # Sync ban to website
        expires_at = 0 if days == 0 else int(time.time() + (days * 24 * 60 * 60))
        if WEBSITE_URL:
            await api_set_ban(username=name, banned=True, expires_at=expires_at, reason=reason)

        # Build response message
        if days == 0:
            msg = f"✅ **{name}** örökre ki lett tiltva a tesztelésből."
        else:
            msg = f"✅ **{name}** ki lett tiltva {days} napra a tesztelésből."
        
        if reason:
            msg += f"\n**Ok:** {reason}"

        await interaction.followup.send(msg, ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


@app_commands.command(name="tierlistunban", description="Játékos visszavétele a tesztelésbe (admin csak).")
@app_commands.describe(
    name="A játékos neve a tierlistán"
)
async def tierlistunban(interaction: discord.Interaction, name: str):
    await interaction.response.defer(ephemeral=True)

    try:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("Hiba.", ephemeral=True)
            return
        if not is_staff_member(interaction.user):
            await interaction.followup.send("Nincs jogosultságod ehhez a parancshoz.", ephemeral=True)
            return

        # Check if actually banned
        if not is_player_banned(name):
            await interaction.followup.send(
                f"❌ **{name}** nincs kitiltva.",
                ephemeral=True
            )
            return

        # Unban from bot
        unban_player(name)

        # Sync unban to website
        if WEBSITE_URL:
            await api_set_ban(username=name, banned=False)

        await interaction.followup.send(
            f"✅ **{name}** vissza lett engedve a tesztelésbe.",
            ephemeral=True
        )

    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


# Confirmation view for remove tierlist
class ConfirmRemoveView(discord.ui.View):
    def __init__(self, username: str, actual_username: str, moderator: discord.Member):
        super().__init__(timeout=60)
        self.username = username  # What the user typed
        self.actual_username = actual_username  # What's in the database
        self.moderator = moderator
        self.confirmed = False

    @discord.ui.button(label="Igen, törlöm", style=discord.ButtonStyle.danger, custom_id="confirm_remove_yes")
    async def confirm_yes(self, interaction: discord.Interaction, _button: discord.ui.Button):
        # Only the moderator who started the command can confirm
        if interaction.user.id != self.moderator.id:
            await interaction.response.send_message("❌ Csak a parancs indítója erősítheti meg.", ephemeral=True)
            return

        self.confirmed = True
        await interaction.response.defer()
        
        try:
            # Call the API to remove the player - use actual username from DB
            result = await api_remove_player(username=self.actual_username)
            status = result.get("status")
            data = result.get("data", {})

            if status == 200:
                removed_count = data.get("removedCount", 1)
                modes = data.get("modes", "")
                details = data.get("details", "")
                
                embed = discord.Embed(
                    title="✅ Játékos eltávolítva a tierlistáról",
                    description=f"**{self.username}** sikeresen törölve lett a tierlistáról.\n"
                               f"Mód: {modes}" + (f"\n{details}" if details else ""),
                    color=discord.Color.green()
                )
                embed.set_footer(text=f"Moderátor: {self.moderator.display_name}")
                
                await interaction.followup.send(embed=embed)
            else:
                error_msg = data.get("error", "Ismeretlen hiba")
                await interaction.followup.send(
                    f"❌ Hiba a törléskor: {error_msg}",
                    ephemeral=True
                )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Hiba: {type(e).__name__}: {e}",
                ephemeral=True
            )

        self.stop()

    @discord.ui.button(label="Mégse", style=discord.ButtonStyle.secondary, custom_id="confirm_remove_no")
    async def confirm_no(self, interaction: discord.Interaction, _button: discord.ui.Button):
        # Only the moderator who started the command can cancel
        if interaction.user.id != self.moderator.id:
            await interaction.response.send_message("❌ Csak a parancs indítója mondhat le.", ephemeral=True)
            return

        await interaction.response.send_message("❌ Törlés megszüntetve.", ephemeral=True)
        self.stop()


@app_commands.command(name="removetierlist", description="Játékos eltávolítása a tierlistáról (admin csak, DANGER!)")
@app_commands.describe(
    name="A játékos neve a tierlistán (Minecraft név)"
)
async def removetierlist(interaction: discord.Interaction, name: str):
    await interaction.response.defer(ephemeral=True)

    try:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("Hiba.", ephemeral=True)
            return
        if not is_staff_member(interaction.user):
            await interaction.followup.send("Nincs jogosultságod ehhez a parancshoz.", ephemeral=True)
            return

        if not WEBSITE_URL:
            await interaction.followup.send("⚠️ WEBSITE_URL nincs beállítva.", ephemeral=True)
            return

        # First, check if the player exists in the tierlist (case-sensitive)
        url = f"{WEBSITE_URL}/api/tests?username={name}"
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        async with http_session.get(url, headers=_auth_headers(), timeout=timeout) as resp:
            try:
                data = await resp.json()
            except Exception:
                data = {}

            if resp.status != 200:
                await interaction.followup.send(f"⚠️ Hiba a weboldal lekérésekor: {resp.status}", ephemeral=True)
                return

            tests = data.get("tests", [])
            
            # Filter for exact case-sensitive match
            exact_match_tests = [t for t in tests if t.get("username", "") == name]
            
            # If no exact match, check if there's a similar name with different case
            if not exact_match_tests:
                similar = [t for t in tests if t.get("username", "").lower() == name.lower()]
                if similar:
                    similar_names = ", ".join([f"`{t.get('username')}`" for t in similar])
                    await interaction.followup.send(
                        f"❌ **{name}** nincs a tierlistán.\n\n"
                        f"Hasonló név(ek) talált: {similar_names}\n"
                        f"Kérlek írd be a pontos nevet (a nagybetűk számítanak)!",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        f"❌ **{name}** nincs a tierlistán.",
                        ephemeral=True
                    )
                return
            
            # Use exact match
            tests = exact_match_tests
            actual_username = tests[0].get("username", "")

            # Show info about the player
            modes_info = "\n".join([f"• **{t.get('gamemode', '?')}**: {t.get('rank', '?')} ({t.get('points', 0)}pt)" for t in tests])

        # Create confirmation embed
        embed = discord.Embed(
            title="⚠️ FIGYELMEZTETÉS - Törlés előtt!",
            description=f"Biztosan eltávolítod **{name}**-t a tierlistáról?\n\n"
                       f"**Jelenlegi tierlist bejegyzések:**\n{modes_info}\n\n"
                       f"❗ **EZ EGY VÉGÉGES MŰVELET!** A játékos minden gamemód-beli eredménye törlésre kerül.",
            color=discord.Color.red()
        )
        embed.set_footer(text=f"Kéri: {interaction.user.display_name}")

        # Send confirmation view
        view = ConfirmRemoveView(username=name, actual_username=name, moderator=interaction.user)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    except aiohttp.ClientError as e:
        await interaction.followup.send(f"⚠️ Web hiba: {type(e).__name__}: {e}", ephemeral=True)
    except asyncio.TimeoutError:
        await interaction.followup.send("⚠️ Web timeout (nem válaszolt 10 mp-en belül).", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


@app_commands.command(name="cooldown", description="Megnézed a cooldownidat egy játékmódban, vagy egy másik játékos cooldownját (staff).")
@app_commands.describe(
    user="Játékos (ha üres, a sajátodat nézed meg)"
)
async def cooldown(interaction: discord.Interaction, user: discord.User = None):
    await interaction.response.defer(ephemeral=True)

    try:
        member = interaction.user
        is_staff = False
        
        # Check if user is staff (for viewing others' cooldowns)
        if user is not None:
            if not interaction.guild or not isinstance(interaction.user, discord.Member):
                await interaction.followup.send("Hiba: Guild context szükséges más játékos cooldownjának megtekintéséhez.", ephemeral=True)
                return
            is_staff = is_staff_member(interaction.user)
            
            if not is_staff:
                await interaction.followup.send("Nincs jogosultságod más játékos cooldownjának megtekintéséhez.", ephemeral=True)
                return
            
            target_member = user
        else:
            # Check own cooldown - check if banned first
            target_member = member
        
        # Check if player is banned from testing
        if WEBSITE_URL:
            try:
                player_name = target_member.display_name
                if hasattr(target_member, 'nick') and target_member.nick:
                    player_name = target_member.nick
                    
                url = f"{WEBSITE_URL}/api/tests/ban?username={player_name}"
                timeout = aiohttp.ClientTimeout(total=5)
                async with http_session.get(url, headers=_auth_headers(), timeout=timeout) as resp:
                    if resp.status == 200:
                        ban_data = await resp.json()
                        if ban_data.get("banned"):
                            reason = ban_data.get("reason", "")
                            await interaction.followup.send(
                                f"❌ **{player_name}** ki van tiltva a tesztelésből!\n" +
                                (f"**Ok:** {reason}" if reason else "Nincs megadva ok."),
                                ephemeral=True
                            )
                            return
            except Exception:
                pass  # If ban check fails, continue
        
        # Check local ban (bot-side)
        if is_player_banned(target_member.display_name):
            ban_info = get_ban_info(target_member.display_name)
            if ban_info:
                expires_at = ban_info.get("expires_at", 0)
                if expires_at == 0:
                    await interaction.followup.send(
                        f"❌ **{target_member.display_name}** örökre ki van tiltva a tesztelésből!\n"
                        f"**Ok:** {ban_info.get('reason', 'Nincs megadva')}",
                        ephemeral=True
                    )
                else:
                    from datetime import datetime
                    exp_date = datetime.fromtimestamp(expires_at)
                    await interaction.followup.send(
                        f"❌ **{target_member.display_name}** ki van tiltva!\n"
                        f"**Lejárat:** {exp_date.strftime('%Y-%m-%d %H:%M')}\n"
                        f"**Ok:** {ban_info.get('reason', 'Nincs megadva')}",
                        ephemeral=True
                    )
                return
        
        # Build cooldown info for all modes
        data = _load_data()
        cooldowns = data.get("cooldowns", {}).get(str(target_member.id), {})
        
        embed = discord.Embed(
            title=f"⏳ Cooldown info - {target_member.display_name}",
            color=discord.Color.blurple()
        )
        
        mode_cooldowns = []
        for label, mode_key, _ in TICKET_TYPES:
            last_closed = float(cooldowns.get(mode_key, 0))
            if last_closed <= 0:
                mode_cooldowns.append(f"✅ **{label}**: Nincs cooldown")
            else:
                left = int((last_closed + COOLDOWN_SECONDS) - time.time())
                if left <= 0:
                    mode_cooldowns.append(f"✅ **{label}**: Kész vagy, már nyithatsz ticketet!")
                else:
                    days = left // (24 * 3600)
                    hours = (left % (24 * 3600)) // 3600
                    minutes = (left % 3600) // 60
                    
                    if days > 0:
                        time_str = f"{days} nap {hours} óra"
                    elif hours > 0:
                        time_str = f"{hours} óra {minutes} perc"
                    else:
                        time_str = f"{minutes} perc"
                    
                    mode_cooldowns.append(f"⏳ **{label}**: {time_str}")
        
        # Add global cooldown info
        global_last = data.get("cooldowns", {}).get(str(target_member.id), {}).get("_global", 0)
        if global_last > 0:
            left = int((global_last + COOLDOWN_SECONDS) - time.time())
            if left > 0:
                days = left // (24 * 3600)
                hours = (left % (24 * 3600)) // 3600
                mode_cooldowns.append(f"\n🌐 **Globális cooldown**: {days} nap {hours} óra")
        
        embed.description = "\n".join(mode_cooldowns)
        embed.set_footer(text=f"Cooldown időtartam: 14 nap")
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


@app_commands.command(name="link", description="Összekapcsolod a Minecraft fiókodat a Discord fiókoddal.")
@app_commands.describe(
    code="A Minecraftban kapott összekapcsolási kód (opcionális, ha még nincs kódod)"
)
async def link(interaction: discord.Interaction, code: str = None):
    await interaction.response.defer(ephemeral=True)

    # If no code provided, generate a new one
    if code is None:
        try:
            # Check if user is already linked
            existing_link = get_linked_minecraft_name(interaction.user.id)
            if existing_link:
                embed = discord.Embed(
                    title="⚠️ Már össze van kapcsolva!",
                    description=f"**Minecraft:** `{existing_link}`\n"
                               f"**Discord:** {interaction.user.mention}\n\n"
                               f"A kettős fiók már össze van kapcsolva!",
                    color=discord.Color.orange()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Check if user already has a pending code - if so, remove it and generate new one
            existing_code = await get_pending_link_code_async(interaction.user.id)
            if existing_code:
                # Remove old code and generate new one
                pass  # Will regenerate below
            
            # Generate new code
            new_code = await generate_link_code_async(interaction.user.id)
            
            # Send code via DM
            try:
                await interaction.user.send(
                    f"🎮 **Összekapcsolási kód:** `{new_code}`\n\n"
                    f"Írd be a Minecraftban: `/link {new_code}`\n"
                    f"A kód {LINK_CODE_EXPIRY_MINUTES} percig érvényes."
                )
                dm_sent = True
            except:
                dm_sent = False
            
            embed = discord.Embed(
                title="✅ Kód generálva!",
                description=f"```\n{new_code}\n```\n"
                           f"Írd be a Minecraftban: `/link {new_code}`\n"
                           f"A kód **{LINK_CODE_EXPIRY_MINUTES} percig** érvényes.",
                color=discord.Color.green()
            )
            if dm_sent:
                embed.add_field(
                    name="📬 DM elküldve!",
                    value="A kódot elküldtem privát üzenetben is!",
                    inline=False
                )
            else:
                embed.add_field(
                    name="⚠️ DM nem sikerült",
                    value="A kód itt látható, másold ki!",
                    inline=False
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
            
        except Exception as e:
            await interaction.followup.send(f"❌ Hiba a kód generálásakor: {type(e).__name__}: {e}", ephemeral=True)
            return
    
    # If code IS provided - this is handled via Minecraft /link command API call now
    # This branch is kept for backward compatibility but will show a message to use in-game
    await interaction.followup.send(
        "❌ A kódot a Minecraftban kell használnod!\n"
        "Írd be a Minecraft chatbe: `/link <kód>`",
        ephemeral=True
    )


@app_commands.command(name="unlink", description="Leválasztod a Minecraft fiókodat a Discord fiókodról.")
async def unlink(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    try:
        # Check if linked
        existing = get_linked_minecraft_name(interaction.user.id)
        if not existing:
            await interaction.followup.send(
                "❌ Nincs összekapcsolva Minecraft fiók!\n"
                "Használd: `/link <név>` hogy összekapcsold.",
                ephemeral=True
            )
            return
        
        # Unlink
        unlink_minecraft_account(interaction.user.id)
        
        embed = discord.Embed(
            title="✅ Sikeres leválasztás!",
            description=f"A Minecraft fiókod (**{existing}**) le lett választva a Discord fiókodról.",
            color=discord.Color.green()
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


@app_commands.command(name="mylink", description="Megnézed az összekapcsolt Minecraft fiókodat.")
async def mylink(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    try:
        linked = get_linked_minecraft_name(interaction.user.id)
        
        if not linked:
            await interaction.followup.send(
                "❌ Nincs összekapcsolva Minecraft fiók!\n"
                "Használd: `/link <név>` hogy összekapcsold.",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="📋 Összekapcsolt fiók",
            description=f"**Discord:** {interaction.user.mention}\n"
                       f"**Minecraft:** {linked}",
            color=discord.Color.blurple()
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    try:
        # If already responded, use followup, else normal response
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ Parancs hiba: {type(error).__name__}: {error}", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Parancs hiba: {type(error).__name__}: {error}", ephemeral=True)
    except Exception:
        pass


# =========================
# SETUP / EVENTS
# =========================
async def wipe_global_commands_once():
    try:
        bot.tree.clear_commands(guild=None)
        await bot.tree.sync()
        print("Global commands wiped.")
    except Exception as e:
        print("Failed to wipe global commands:", e)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id={bot.user.id})")

    # persistent views
    bot.add_view(TicketPanelView())
    bot.add_view(CloseTicketView(owner_id=0, mode_key=""))

    guild = discord.Object(id=GUILD_ID) if GUILD_ID else None

    if WIPE_GLOBAL_COMMANDS:
        await wipe_global_commands_once()

    try:
        if guild:
            await bot.tree.sync(guild=guild)
            print(f"Slash commands synced to guild {GUILD_ID}")
        else:
            await bot.tree.sync()
            print("Slash commands synced globally (no GUILD_ID set).")
    except Exception as e:
        print("Sync failed:", e)


async def main():
    global http_session

    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN is missing")

    # Initialize database
    await init_db()

    http_session = aiohttp.ClientSession()

    # health server
    asyncio.create_task(start_health_server())

    # register commands (guild-scoped for instant updates)
    if GUILD_ID:
        g = discord.Object(id=GUILD_ID)
        bot.tree.add_command(ticketpanel, guild=g)
        bot.tree.add_command(testresult, guild=g)
        bot.tree.add_command(tierlistnamechange, guild=g)
        bot.tree.add_command(profile, guild=g)
        bot.tree.add_command(porog, guild=g)
        bot.tree.add_command(retire, guild=g)
        bot.tree.add_command(unretire, guild=g)
        bot.tree.add_command(tierlistban, guild=g)
        bot.tree.add_command(tierlistunban, guild=g)
        bot.tree.add_command(removetierlist, guild=g)
        bot.tree.add_command(cooldown, guild=g)
        bot.tree.add_command(link, guild=g)
        bot.tree.add_command(unlink, guild=g)
        bot.tree.add_command(mylink, guild=g)
    else:
        bot.tree.add_command(ticketpanel)
        bot.tree.add_command(testresult)
        bot.tree.add_command(tierlistnamechange)
        bot.tree.add_command(profile)
        bot.tree.add_command(porog)
        bot.tree.add_command(retire)
        bot.tree.add_command(unretire)
        bot.tree.add_command(tierlistban)
        bot.tree.add_command(tierlistunban)
        bot.tree.add_command(removetierlist)
        bot.tree.add_command(cooldown)
        bot.tree.add_command(link)
        bot.tree.add_command(unlink)
        bot.tree.add_command(mylink)

    try:
        await bot.start(DISCORD_TOKEN)
    finally:
        if http_session:
            await http_session.close()
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
