import os
import json
import time
import asyncio
import datetime
import random
import string

import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import asyncpg

# =========================
# CONFIG
# =========================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
STAFF_ROLE_ID = int(os.getenv("STAFF_ROLE_ID", "0"))
TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID", "0"))
EXTRA_STAFF_ROLE_IDS = [int(os.getenv("EXTRA_STAFF_ROLE_IDS", "0"))] if os.getenv("EXTRA_STAFF_ROLE_IDS") else []
ALLOWED_USER_IDS = [int(x.strip()) for x in os.getenv("ALLOWED_USER_IDS", "").split(",") if x.strip()]
DEBUG_ALLOWED_USERS = []
DEBUG_ALLOWED_ROLES = [1483822408182796418]

WEBSITE_URL = os.getenv("WEBSITE_URL", "").rstrip("/")
BOT_API_KEY = os.getenv("BOT_API_KEY", "")
MINECRAFT_API_URL = os.getenv("MINECRAFT_API_URL", "http://localhost:8080").rstrip("/")

WIPE_GLOBAL_COMMANDS = os.getenv("WIPE_GLOBAL_COMMANDS", "0") == "1"
COOLDOWN_SECONDS = 14 * 24 * 60 * 60
DATA_FILE = "data.json"
HTTP_TIMEOUT_SECONDS = 10

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "")
SUPABASE_PG_URL = os.getenv("SUPABASE_PG_URL", "")
USE_SUPABASE_API = bool(SUPABASE_URL and SUPABASE_KEY)

LINK_CODE_LENGTH = 8
LINK_CODE_EXPIRY_MINUTES = 10

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

TICKET_ROUNDS = {
    "vanilla": ("FT4", "FT3", None),
    "diasmp": ("FT4", "FT3", "FT2"),
    "ogvanilla": ("FT4", "FT2", None),
    "nethpot": ("FT4", "FT2", None),
    "mace": ("FT4", "FT2", None),
    "smp": ("FT4", "FT3", "FT2"),
    "cart": ("FT4", "FT3", "FT2"),
    "sword": ("FT10", "FT6", None),
    "uhc": ("FT6", "FT3", None),
    "pot": ("FT10", "FT6", None),
    "creeper": ("FT6", "FT4", "FT3"),
    "shieldlessuhc": ("FT6", "FT4", None),
    "axe": ("FT20", "FT10", None),
    "spearmace": ("FT6", "FT3", None),
    "spearelytra": ("FT6", "FT3", None),
}

RANKS = ["Unranked", "LT5", "HT5", "LT4", "HT4", "LT3", "HT3", "LT2", "HT2", "LT1", "HT1"]

POINTS = {
    "Unranked": 0, "LT5": 1, "HT5": 2, "LT4": 3, "HT4": 4,
    "LT3": 6, "HT3": 8, "LT2": 10, "HT2": 12, "LT1": 14, "HT1": 18,
}

GAMEMODE_DISPLAY_NAMES = {
    "vanilla": "Vanilla", "uhc": "UHC", "pot": "Pot", "nethpot": "NethPot",
    "smp": "SMP", "sword": "Sword", "axe": "Axe", "mace": "Mace",
    "cart": "Cart", "creeper": "Creeper", "diasmp": "DiaSMP",
    "ogvanilla": "OGVanilla", "shieldlessuhc": "ShieldlessUHC",
    "spearmace": "SpearMace", "spearelytra": "SpearElytra",
}

QUEUE_CHANNELS = {
    "sword": 1495038486120632410, "axe": 1495038602751774730, "mace": 1495038625719783586,
    "uhc": 1495038706103484487, "pot": 1495038741465792553, "nethpot": 1495038766769897482,
    "smp": 1495038799800176660, "vanilla": 1495038839591534834, "creeper": 1495038857597681818,
    "cart": 1495038915453779982, "diasmp": 1495038938640027760, "spearelytra": 1495038976988545206,
    "spearmace": 1495038999876600008, "shieldlessuhc": 1495039115119296572, "ogvanilla": 1495039145330872341,
}

QUEUE_PING_ROLES = {
    "sword": 1495043729017278525, "axe": 1495043913583558758, "mace": 1495043981959237752,
    "uhc": 1495044042612805754, "pot": 1495044102730022942, "nethpot": 1495044163194847322,
    "smp": 1495044237551472893, "vanilla": 1495044315272052929, "creeper": 1495044383425171506,
    "cart": 1495044436403556443, "diasmp": 1495044514992095333, "shieldlessuhc": 1495044593211670711,
    "ogvanilla": 1495044664502386698, "spearelytra": 1495044732680667247, "spearmace": 1495044798472781944,
}

TICKET_CREATE_CATEGORY_ID = 1495038336744689674


# =========================
# HELPERS
# =========================
def get_gamemode_display_name(mode_key: str) -> str:
    if not mode_key:
        return mode_key
    return GAMEMODE_DISPLAY_NAMES.get(mode_key.lower().strip(), mode_key)


def normalize_gamemode(mode: str) -> str:
    if not mode:
        return mode
    return mode.lower().strip()


def format_cooldown(seconds: int) -> str:
    if seconds <= 0:
        return "0"
    days = seconds // (24 * 60 * 60)
    hours = (seconds % (24 * 60 * 60)) // (60 * 60)
    minutes = (seconds % (60 * 60)) // 60
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}o")
    if minutes > 0:
        parts.append(f"{minutes}p")
    return " ".join(parts) if parts else "<1p"


def is_staff_member(member) -> bool:
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
# STORAGE
# =========================
def _load_data():
    if not os.path.exists(DATA_FILE):
        return {"ticket_state": {}, "cooldowns": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"ticket_state": {}, "cooldowns": {}}


def _save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_open_ticket_channel_id(user_id: int, mode_key: str):
    data = _load_data()
    return data.get("ticket_state", {}).get(str(user_id), {}).get(mode_key)


def set_open_ticket_channel_id(user_id: int, mode_key: str, channel_id):
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


def set_last_closed(user_id: int, mode_key: str, ts: float):
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
# BAN SYSTEM
# =========================
def _load_ban_data():
    if not os.path.exists("bans.json"):
        return {}
    try:
        with open("bans.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_ban_data(data):
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


def get_ban_info(username: str):
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


def ban_player(username: str, days: int, reason: str = ""):
    data = _load_ban_data()
    expires_at = 0 if days == 0 else time.time() + (days * 24 * 60 * 60)
    data[username.lower()] = {"username": username, "reason": reason, "banned_at": time.time(), "expires_at": expires_at, "permanent": days == 0}
    _save_ban_data(data)


def unban_player(username: str) -> bool:
    data = _load_ban_data()
    if username.lower() in data:
        data.pop(username.lower(), None)
        _save_ban_data(data)
        return True
    return False


# =========================
# LINK SYSTEM
# =========================
def _load_link_data():
    if not os.path.exists("links.json"):
        return {}
    try:
        with open("links.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_link_data(data):
    with open("links.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def get_linked_minecraft_name_async(discord_id: int):
    if USE_SUPABASE_API:
        try:
            url = f"{SUPABASE_URL}/rest/v1/linked_accounts"
            params = {"discord_id": f"eq.{discord_id}"}
            headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
            async with http_session.get(url, headers=headers, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data:
                        return data[0]['minecraft_name']
        except Exception as e:
            print(f"Error getting from Supabase: {e}")
    data = _load_link_data()
    return data.get(str(discord_id))


async def link_minecraft_account_async(discord_id: int, minecraft_name: str):
    if USE_SUPABASE_API:
        try:
            url = f"{SUPABASE_URL}/rest/v1/linked_accounts"
            headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Prefer": "resolution=merge-duplicates", "Content-Type": "application/json"}
            async with http_session.post(url, headers=headers, json={"discord_id": str(discord_id), "minecraft_name": minecraft_name}) as resp:
                if resp.status in (200, 201):
                    return True
        except Exception as e:
            print(f"Error linking to Supabase: {e}")
    data = _load_link_data()
    data[str(discord_id)] = minecraft_name
    _save_link_data(data)
    return True


async def unlink_minecraft_account_async(discord_id: int):
    if USE_SUPABASE_API:
        try:
            url = f"{SUPABASE_URL}/rest/v1/linked_accounts"
            params = {"discord_id": f"eq.{discord_id}"}
            headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
            async with http_session.delete(url, headers=headers, params=params):
                return True
        except Exception as e:
            print(f"Error unlinking from Supabase: {e}")
    data = _load_link_data()
    if str(discord_id) in data:
        del data[str(discord_id)]
        _save_link_data(data)
        return True
    return False


async def get_discord_by_minecraft_async(minecraft_name: str):
    if USE_SUPABASE_API:
        try:
            url = f"{SUPABASE_URL}/rest/v1/linked_accounts"
            params = {"minecraft_name": f"eq.{minecraft_name}"}
            headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
            async with http_session.get(url, headers=headers, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data:
                        return int(data[0]['discord_id'])
        except Exception as e:
            print(f"Error getting discord by minecraft: {e}")
    return None


def get_linked_minecraft_name(discord_id: int):
    data = _load_link_data()
    return data.get(str(discord_id))


# =========================
# LINK CODES
# =========================
def _load_pending_link_codes():
    if not os.path.exists("pending_links.json"):
        return {}
    try:
        with open("pending_links.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_pending_link_codes(data):
    with open("pending_links.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def generate_link_code_async(discord_id: int) -> str:
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=LINK_CODE_LENGTH))
    if USE_SUPABASE_API:
        try:
            expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=LINK_CODE_EXPIRY_MINUTES)
            url = f"{SUPABASE_URL}/rest/v1/pending_codes"
            headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Prefer": "resolution=merge-duplicates", "Content-Type": "application/json"}
            async with http_session.post(url, headers=headers, json={"discord_id": str(discord_id), "code": code.upper(), "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "expires_at": expires_at.isoformat(), "used": False}) as resp:
                if resp.status in (200, 201):
                    return code
        except Exception as e:
            print(f"Error generating link code: {e}")
    data = _load_pending_link_codes()
    data = {k: v for k, v in data.items() if v.get("discord_id") != discord_id}
    data[code] = {"discord_id": discord_id, "expires_at": time.time() + (LINK_CODE_EXPIRY_MINUTES * 60)}
    _save_pending_link_codes(data)
    return code


async def verify_link_code_async(code: str):
    if USE_SUPABASE_API:
        try:
            url = f"{SUPABASE_URL}/rest/v1/pending_codes"
            params = {"code": f"eq.{code.upper()}", "used": "eq.false"}
            headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
            async with http_session.get(url, headers=headers, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data:
                        expires_at = datetime.datetime.fromisoformat(data[0]['expires_at'].replace('Z', '+00:00'))
                        if expires_at > datetime.datetime.now(datetime.timezone.utc):
                            discord_id = int(data[0]['discord_id'])
                            await http_session.patch(f"{SUPABASE_URL}/rest/v1/pending_codes", headers=headers, json={"used": True}, params={"code": f"eq.{code.upper()}"})
                            return discord_id
        except Exception as e:
            print(f"Error verifying link code: {e}")
    return None


# =========================
# WEBSITE API
# =========================
def _auth_headers():
    if not BOT_API_KEY:
        return {}
    return {"Authorization": f"Bearer {BOT_API_KEY}"}


async def api_get_tests(username: str, mode: str):
    if not WEBSITE_URL:
        return {"status": 0, "data": {"tests": []}}
    url = f"{WEBSITE_URL}/api/tests?username={username}&gamemode={mode}"
    try:
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        async with http_session.get(url, headers=_auth_headers(), timeout=timeout) as resp:
            return {"status": resp.status, "data": (await resp.json()) if resp.status == 200 else {}}
    except Exception as e:
        print(f"API error: {e}")
        return {"status": 0, "data": {"error": str(e)}}


async def api_get_all_tests():
    if not WEBSITE_URL:
        return {"status": 0, "data": {"tests": []}}
    url = f"{WEBSITE_URL}/api/tests"
    try:
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        async with http_session.get(url, headers=_auth_headers(), timeout=timeout) as resp:
            return {"status": resp.status, "data": (await resp.json()) if resp.status == 200 else {}}
    except Exception as e:
        return {"status": 0, "data": {"error": str(e)}}


async def api_post_test(username: str, mode: str, rank: str, tester):
    if not WEBSITE_URL:
        return {"status": 0}
    url = f"{WEBSITE_URL}/api/tests"
    payload = {"username": username, "mode": get_gamemode_display_name(mode), "rank": rank, "testerId": str(tester.id), "testerName": tester.display_name, "upsert": True, "ts": int(time.time())}
    try:
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        async with http_session.post(url, json=payload, headers=_auth_headers(), timeout=timeout) as resp:
            return {"status": resp.status, "data": (await resp.json()) if resp.status in (200, 201) else {}}
    except Exception as e:
        return {"status": 0, "data": {"error": str(e)}}


async def api_rename_player(old_name: str, new_name: str):
    if not WEBSITE_URL:
        return {"status": 0}
    url = f"{WEBSITE_URL}/api/tests/rename"
    payload = {"oldName": old_name, "newName": new_name}
    try:
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        async with http_session.post(url, json=payload, headers=_auth_headers(), timeout=timeout) as resp:
            return {"status": resp.status, "data": (await resp.json()) if resp.status == 200 else {}}
    except Exception as e:
        return {"status": 0, "data": {"error": str(e)}}


async def api_set_ban(username: str, banned: bool, reason: str = ""):
    if not WEBSITE_URL:
        return {"status": 0}
    url = f"{WEBSITE_URL}/api/tests/ban"
    payload = {"username": username, "banned": banned, "reason": reason}
    try:
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        async with http_session.post(url, json=payload, headers=_auth_headers(), timeout=timeout) as resp:
            return {"status": resp.status, "data": (await resp.json()) if resp.status == 200 else {}}
    except Exception as e:
        return {"status": 0, "data": {"error": str(e)}}


async def api_remove_player(username: str, gamemode: str = None):
    if not WEBSITE_URL:
        return {"status": 0}
    url = f"{WEBSITE_URL}/api/tests/remove"
    payload = {"username": username}
    if gamemode:
        payload["gamemode"] = gamemode
    try:
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        async with http_session.post(url, json=payload, headers=_auth_headers(), timeout=timeout) as resp:
            return {"status": resp.status, "data": (await resp.json()) if resp.status == 200 else {}}
    except Exception as e:
        return {"status": 0, "data": {"error": str(e)}}


# =========================
# BOT SETUP
# =========================
intents = discord.Intents.default()
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
http_session = None

# =========================
# UI VIEWS
# =========================
class CloseTicketView(discord.ui.View):
    def __init__(self, owner_id: int, mode_key: str):
        super().__init__(timeout=None)
        self.owner_id = owner_id
        self.mode_key = mode_key

    @discord.ui.button(label="Ticket zarasa", style=discord.ButtonStyle.danger, custom_id="neotiers_close_ticket")
    async def close(self, interaction: discord.Interaction, _button: discord.ui.Button):
        try:
            channel = interaction.channel
            if not isinstance(channel, discord.TextChannel):
                await interaction.response.send_message("Hiba", ephemeral=True)
                return

            topic = channel.topic or ""
            owner_id = 0
            if "owner=" in topic:
                try:
                    owner_id = int(topic.split("owner=")[1].split("|")[0].strip())
                except:
                    owner_id = 0

            if interaction.user.id != owner_id and not is_staff_member(interaction.user):
                await interaction.response.send_message("Nincs jogod", ephemeral=True)
                return

            await interaction.response.send_message("Ticket zarva!", ephemeral=True)
            set_last_closed(owner_id, self.mode_key, time.time())
            set_open_ticket_channel_id(owner_id, self.mode_key, None)

            await asyncio.sleep(2)
            try:
                await channel.delete(reason="Ticket closed")
            except:
                pass
        except Exception as e:
            print(f"close ticket error: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Hiba: {e}", ephemeral=True)


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
            await interaction.response.send_message("Hiba: guild/member nem elerheto.", ephemeral=True)
            return

        linked_minecraft = get_linked_minecraft_name(member.id)
        if not linked_minecraft:
            await interaction.response.send_message("Nincs osszekapcsolva a Minecraft fiókod! Hasznald a `/link` parancsot.", ephemeral=True)
            return

        cd = cooldown_left(member.id, self.mode_key)
        if cd > 0:
            cd_display = format_cooldown(cd)
            await interaction.response.send_message(f"Meg nem tesztelhetsz! Varj: **{cd_display}**", ephemeral=True)
            return

        existing_channel_id = get_open_ticket_channel_id(member.id, self.mode_key)
        if existing_channel_id:
            ch = guild.get_channel(existing_channel_id)
            if ch:
                await interaction.response.send_message("Van mar ticketed ebből a jatekmodbol.", ephemeral=True)
                return

        category = guild.get_channel(TICKET_CATEGORY_ID) if TICKET_CATEGORY_ID else None
        if TICKET_CATEGORY_ID and not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message("Ticket kategoria rossz.", ephemeral=True)
            return

        staff_role = guild.get_role(STAFF_ROLE_ID) if STAFF_ROLE_ID else None
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True)

        safe_name = member.name.lower().replace(" ", "-")
        channel_name = f"{self.mode_key}-{safe_name}"

        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"NeoTiers ticket | owner={member.id} | mode={self.mode_key} | mc={linked_minecraft}",
                reason="NeoTiers ticket created"
            )
        except discord.Forbidden:
            await interaction.response.send_message("Nincs jogom csatornat letrehozni.", ephemeral=True)
            return

        set_open_ticket_channel_id(member.id, self.mode_key, channel.id)

        ping_role_id = None
        for _label, mk, rid in TICKET_TYPES:
            if mk == self.mode_key:
                ping_role_id = rid
                break

        ping_text = f"<@&{ping_role_id}>" if ping_role_id else ""

        embed = discord.Embed(title="Teszt keres", description="Kattints egy alabbi gombra, hogy tudd tesztelni a gombon feltuntetett jatekmodbol.", color=discord.Color.blurple())
        embed.add_field(name="Jatekmod", value=get_gamemode_display_name(self.mode_key), inline=True)
        embed.add_field(name="Minecraftnev", value=f"`{linked_minecraft}`", inline=True)
        embed.add_field(name="Jatekos", value=member.mention, inline=True)

        await channel.send(content=ping_text, embed=embed, view=CloseTicketView(owner_id=member.id, mode_key=self.mode_key))
        await interaction.response.send_message(f"Ticket letrehozva: {channel.mention}", ephemeral=True)


# =========================
# QUEUE SYSTEM
# =========================
ACTIVE_QUEUES = {}
QUEUE_MESSAGE_IDS = {}


class QueuePlayer:
    def __init__(self, discord_id: int, minecraft_name: str):
        self.discord_id = discord_id
        self.minecraft_name = minecraft_name
        self.joined_at = time.time()


class QueueUserView(discord.ui.View):
    def __init__(self, gamemode: str):
        super().__init__(timeout=None)
        self.gamemode = gamemode

    @discord.ui.button(label="Belepes a queue-ba", style=discord.ButtonStyle.success)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("Hiba: nem tag", ephemeral=True)
            return
        queue = ACTIVE_QUEUES.get(self.gamemode)
        if not queue:
            await interaction.response.send_message("Nincs queue", ephemeral=True)
            return
        if any(p.discord_id == member.id for p in queue["players"]):
            await interaction.response.send_message("Mar benne vagy!", ephemeral=True)
            return
        if is_staff_member(member):
            queue["players"].append(QueuePlayer(member.id, "TESZTER"))
            await update_queue_message(self.gamemode)
            await interaction.response.send_message("Beleptel teszterkent!", ephemeral=True)
            return
        linked_mc = await get_linked_minecraft_name_async(member.id)
        if not linked_mc:
            await interaction.response.send_message("Nincs linked MC! `/link`", ephemeral=True)
            return
        queue["players"].append(QueuePlayer(member.id, linked_mc))
        await update_queue_message(self.gamemode)
        await interaction.response.send_message("Beleptel a queue-ba!", ephemeral=True)

    @discord.ui.button(label="Kilepes a queue-bol", style=discord.ButtonStyle.danger)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("Hiba: nem tag", ephemeral=True)
            return
        queue = ACTIVE_QUEUES.get(self.gamemode)
        if not queue:
            await interaction.response.send_message("Nincs queue", ephemeral=True)
            return
        for i, p in enumerate(queue["players"]):
            if p.discord_id == member.id:
                queue["players"].pop(i)
                await update_queue_message(self.gamemode)
                await interaction.response.send_message("Kileptel a queue-bol!", ephemeral=True)
                return
        await interaction.response.send_message("Nem vagy a queue-ban", ephemeral=True)

    @discord.ui.button(label="Queue zarasa", style=discord.ButtonStyle.secondary)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("Hiba: nem tag", ephemeral=True)
            return
        queue = ACTIVE_QUEUES.get(self.gamemode)
        if not queue:
            await interaction.response.send_message("Nincs queue", ephemeral=True)
            return
        if not is_staff_member(member) and queue["opened_by"] != member.id:
            await interaction.response.send_message("Nincs jogod", ephemeral=True)
            return
        del ACTIVE_QUEUES[self.gamemode]
        await update_queue_message(self.gamemode)
        await interaction.response.send_message("Queue zarva!", ephemeral=True)

    @discord.ui.button(label="Kovetkezo jatekos", style=discord.ButtonStyle.primary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("Hiba: nem tag", ephemeral=True)
            return
        queue = ACTIVE_QUEUES.get(self.gamemode)
        if not queue or not queue["players"]:
            await interaction.response.send_message("Nincs jatekos a queue-ban", ephemeral=True)
            return
        if not is_staff_member(member) and queue["opened_by"] != member.id:
            await interaction.response.send_message("Nincs jogod", ephemeral=True)
            return
        next_player_obj = queue["players"].pop(0)
        queue["called_players"].append(next_player_obj.discord_id)
        await update_queue_message(self.gamemode)
        guild = interaction.guild
        category = guild.get_channel(TICKET_CREATE_CATEGORY_ID)
        if not category or not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message("Nincs kategoria", ephemeral=True)
            return
        channel_name = f"{self.gamemode}-{next_player_obj.minecraft_name}"[:50].lower()
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.get_member(next_player_obj.discord_id): discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        if STAFF_ROLE_ID:
            overwrites[guild.get_role(STAFF_ROLE_ID)] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True)
        channel = await guild.create_text_channel(name=channel_name, category=category, overwrites=overwrites, topic=f"owner={next_player_obj.discord_id} | mode={self.gamemode}")
        embed = discord.Embed(title="Teszt keres", color=discord.Color.blurple())
        embed.add_field(name="Jatekos", value=f"<@{next_player_obj.discord_id}>", inline=True)
        embed.add_field(name="Minecraft", value=next_player_obj.minecraft_name, inline=True)
        embed.set_thumbnail(url=f"https://minotar.net/helm/{next_player_obj.minecraft_name}/128.png")
        view = CloseTicketView(owner_id=next_player_obj.discord_id, mode_key=self.gamemode)
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"Ticket letrehozva: {channel.mention}", ephemeral=True)


async def update_queue_message(gamemode: str):
    channel_id = QUEUE_CHANNELS.get(gamemode)
    if not channel_id:
        return
    channel = bot.get_channel(channel_id)
    if not channel or not isinstance(channel, discord.TextChannel):
        return
    msg_id = None
    for mid, gm in QUEUE_MESSAGE_IDS.items():
        if gm == gamemode:
            msg_id = mid
            break
    if not msg_id:
        return
    try:
        message = await channel.fetch_message(msg_id)
    except Exception:
        return

    queue = ACTIVE_QUEUES.get(gamemode)
    if not queue:
        embed = discord.Embed(title=f"{get_gamemode_display_name(gamemode)} Queue", description="A queue zarva van.", color=discord.Color.red())
        try:
            await message.edit(embed=embed, view=None)
        except Exception:
            pass
        return

    player_lines = []
    for player in queue["players"]:
        member = channel.guild.get_member(player.discord_id)
        name = member.display_name if member else player.minecraft_name
        if is_staff_member(member):
            name = f"* {name}"
        player_lines.append(f"{name} ({player.minecraft_name})")

    player_text = "\n".join(player_lines) if player_lines else "Meg senki nincs a queue-ban."

    embed = discord.Embed(title=f"{get_gamemode_display_name(gamemode)} Queue", description=player_text, color=discord.Color.green())
    embed.set_footer(text=f"Jatekosok: {len(queue['players'])}")
    view = QueueUserView(gamemode)
    try:
        await message.edit(embed=embed, view=view)
    except Exception:
        pass


# =========================
# COMMANDS
# =========================

@app_commands.command(name="queuepanel", description="Queue panel uzenet kirakasa (teszteloknek)")
async def queuepanel(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        await interaction.followup.send("Hiba.", ephemeral=True)
        return
    if not is_staff_member(interaction.user):
        await interaction.followup.send("Nincs jogod.", ephemeral=True)
        return

    lines = []
    for label, key, _rid in TICKET_TYPES:
        status = "ZARVA" if key in ACTIVE_QUEUES else "NYITVA"
        lines.append(f"**{label}**: {status}")

    embed = discord.Embed(title="Queue panel", description="\n".join(lines), color=discord.Color.blurple())
    await interaction.followup.send(embed=embed, ephemeral=True)


@app_commands.command(name="closequeue", description="Queue zarasa")
async def closequeue(interaction: discord.Interaction, jatekmod: str):
    await interaction.response.defer(ephemeral=True)
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        await interaction.followup.send("Hiba.", ephemeral=True)
        return
    if not is_staff_member(interaction.user):
        await interaction.followup.send("Nincs jogod.", ephemeral=True)
        return

    mode_key = jatekmod.lower()
    if mode_key not in ACTIVE_QUEUES:
        await interaction.followup.send(f"A {jatekmod} queue nincs nyitva.", ephemeral=True)
        return

    del ACTIVE_QUEUES[mode_key]
    await interaction.followup.send(f"A {jatekmod} queue zarva.", ephemeral=True)


@app_commands.command(name="tests", description="Teszteloi statisztikak")
async def tests(interaction: discord.Interaction):
    await interaction.response.defer()
    if not WEBSITE_URL:
        await interaction.followup.send("WEBSITE_URL nincs beallitva.", ephemeral=True)
        return

    res = await api_get_all_tests()
    if res.get("status") != 200:
        await interaction.followup.send("Hiba a statisztikak betoltesekor.", ephemeral=True)
        return

    data = res.get("data", {})
    tests = data.get("tests", [])

    if not tests:
        await interaction.followup.send("Nincs meg teszt.", ephemeral=True)
        return

    tester_stats = {}
    for t in tests:
        tester_name = t.get("testerName", "Unknown")
        tester_stats[tester_name] = tester_stats.get(tester_name, 0) + 1

    sorted_testers = sorted(tester_stats.items(), key=lambda x: x[1], reverse=True)[:10]
    lines = [f"**{name}**: {count} teszt" for name, count in sorted_testers]

    embed = discord.Embed(title="Teszteloi statisztikak", description="\n".join(lines), color=discord.Color.blurple())
    await interaction.followup.send(embed=embed)


@app_commands.command(name="testresult", description="Minecraft tier teszt eredmeny")
async def testresult(interaction: discord.Interaction, jatekos: str, jatekmod: str, tier: str):
    await interaction.response.defer()
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        await interaction.followup.send("Hiba.", ephemeral=True)
        return
    if not is_staff_member(interaction.user):
        await interaction.followup.send("Nincs jogod.", ephemeral=True)
        return

    if tier not in RANKS:
        await interaction.followup.send(f"Ervenytelen tier: {tier}", ephemeral=True)
        return

    linked_mc = await get_linked_minecraft_name_async(interaction.user.id)
    if not linked_mc:
        await interaction.followup.send("Nincs osszekapcsolva a Minecraft fiókod!", ephemeral=True)
        return

    mode_key = normalize_gamemode(jatekmod)
    if not mode_key:
        await interaction.followup.send("Ervenytelen jatekmod.", ephemeral=True)
        return

    prev_rank = "Unranked"
    if WEBSITE_URL:
        try:
            res = await api_get_tests(username=linked_mc, mode=mode_key)
            if res.get("status") == 200:
                data = res.get("data", {})
                test = data.get("test")
                tests = data.get("tests", [])
                target = test or (tests[0] if tests else None)
                if target:
                    prev_rank = str(target.get("rank", "Unranked"))
        except Exception as e:
            print(f"Error fetching tier: {e}")

    new_points = POINTS.get(tier, 0)
    prev_points = POINTS.get(prev_rank, 0)
    diff = new_points - prev_points
    points_str = f"+{diff}" if diff > 0 else str(diff)
    if diff == 0:
        points_str = "+-0"

    skin_url = f"https://minotar.net/helm/{linked_mc}/128.png"
    embed = discord.Embed(title=f"{linked_mc} teszt eredmenye", color=discord.Color.dark_grey())
    embed.set_thumbnail(url=skin_url)
    embed.add_field(name="Tesztelo:", value=interaction.user.mention, inline=False)
    embed.add_field(name="Jatekmod:", value=get_gamemode_display_name(mode_key), inline=False)
    embed.add_field(name="Minecraftnev:", value=linked_mc, inline=False)
    embed.add_field(name="Elozorang:", value=f"{prev_rank} ({prev_points} pont)", inline=False)
    embed.add_field(name="Erett rang:", value=f"{tier} ({new_points} pont)", inline=False)
    embed.add_field(name="Pontok:", value=points_str, inline=False)

    tier_channel_id_str = os.getenv("TIER_RESULTS_CHANNEL_ID", "0")
    tier_channel_id = 0
    try:
        tier_channel_id = int(tier_channel_id_str)
    except ValueError:
        pass

    if tier_channel_id:
        tier_channel = interaction.guild.get_channel(tier_channel_id)
        if tier_channel:
            await tier_channel.send(embed=embed)

    if WEBSITE_URL:
        save = await api_post_test(username=linked_mc, mode=mode_key, rank=tier, tester=interaction.user)
        save_ok = (save.get("status") == 200 or save.get("status") == 201)
        if save_ok:
            set_last_closed(interaction.user.id, mode_key, time.time())
            await interaction.followup.send(f"Rang beallitva: **{tier}** es mentve a weboldalra!", ephemeral=True)
        else:
            await interaction.followup.send(f"Rang beallitva: **{tier}** (weboldalmentes sikertelen)", ephemeral=True)
    else:
        await interaction.followup.send(f"Rang beallitva: **{tier}**", ephemeral=True)
        set_last_closed(interaction.user.id, mode_key, time.time())


@app_commands.command(name="cooldown", description="Megnezed a cooldownidat egy jatekmodban")
async def cooldown(interaction: discord.Interaction, jatekmod: str = None, jatekos: discord.Member = None):
    await interaction.response.defer(ephemeral=True)
    target = jatekos or interaction.user

    if jatekmod:
        mode_key = normalize_gamemode(jatekmod)
        cd = cooldown_left(target.id, mode_key)
        if cd > 0:
            await interaction.followup.send(f"Cooldown **{get_gamemode_display_name(mode_key)}**: {format_cooldown(cd)}", ephemeral=True)
        else:
            await interaction.followup.send(f"Nincs cooldown **{get_gamemode_display_name(mode_key)}**-ban.", ephemeral=True)
    else:
        lines = []
        for label, key, _rid in TICKET_TYPES:
            cd = cooldown_left(target.id, key)
            if cd > 0:
                lines.append(f"**{label}**: {format_cooldown(cd)}")
        if lines:
            await interaction.followup.send("\n".join(lines), ephemeral=True)
        else:
            await interaction.followup.send("Nincs cooldownod sehol.", ephemeral=True)


@app_commands.command(name="profile", description="Megnezed egy jatekos tierjeit a tierlistarol")
async def profile(interaction: discord.Interaction, jatekos: str = None):
    await interaction.response.defer()
    if not WEBSITE_URL:
        await interaction.followup.send("WEBSITE_URL nincs beallitva.", ephemeral=True)
        return

    target = jatekos or (await get_linked_minecraft_name_async(interaction.user.id))
    if not target:
        await interaction.followup.send("Nincs megadva jatekos.", ephemeral=True)
        return

    res = await api_get_all_tests()
    if res.get("status") != 200:
        await interaction.followup.send("Hiba a profile betoltesekor.", ephemeral=True)
        return

    data = res.get("data", {})
    tests = data.get("tests", [])

    user_tests = [t for t in tests if t.get("username", "").lower() == target.lower()]

    if not user_tests:
        await interaction.followup.send(f"Nincs tesztje a {target} jatekosnak.", ephemeral=True)
        return

    lines = []
    for t in user_tests:
        rank = t.get("rank", "Unranked")
        mode = t.get("gamemode", "?")
        lines.append(f"**{mode}**: {rank}")

    skin_url = f"https://minotar.net/helm/{target}/128.png"
    embed = discord.Embed(title=f"{target} profilja", description="\n".join(lines), color=discord.Color.blurple())
    embed.set_thumbnail(url=skin_url)
    await interaction.followup.send(embed=embed)


@app_commands.command(name="link", description="Osszekapcsolod a Minecraft fiokodat a Discord fiokoddal")
async def link(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    code = await generate_link_code_async(interaction.user.id)
    await interaction.followup.send(
        f"**Linkelesi kod:** `{code}`\n\n"
        "Ezt a kodot kell beirnod a Minecraft szerveren a `/link <kod>` parancsba.",
        ephemeral=True
    )


@app_commands.command(name="unlink", description="Levallasztod a Minecraft fiokodat a Discord fiokodrol")
async def unlink(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    success = await unlink_minecraft_account_async(interaction.user.id)
    if success:
        await interaction.followup.send("Sikeresen levallasztottad a Minecraft fiokodat.", ephemeral=True)
    else:
        await interaction.followup.send("Hiba tortent.", ephemeral=True)


@app_commands.command(name="mylink", description="Megnezed az osszekapcsolt Minecraft fiokodat")
async def mylink(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    mc = await get_linked_minecraft_name_async(interaction.user.id)
    if mc:
        await interaction.followup.send(f"Osszekapcsolt Minecraft: **{mc}**", ephemeral=True)
    else:
        await interaction.followup.send("Nincs osszekapcsolva a Minecraft fiokod. Hasznald a `/link` parancsot.", ephemeral=True)


@app_commands.command(name="tierlistban", description="Jatekos kitiltasa a tesztelesbol (admin)")
async def tierlistban(interaction: discord.Interaction, jatekos: str, indok: str = ""):
    await interaction.response.defer(ephemeral=True)
    if not is_staff_member(interaction.user):
        await interaction.followup.send("Nincs jogod.", ephemeral=True)
        return

    if not WEBSITE_URL:
        await interaction.followup.send("WEBSITE_URL nincs beallitva.", ephemeral=True)
        return

    res = await api_set_ban(username=jatekos, banned=True, reason=indok)
    if res.get("status") == 200:
        await interaction.followup.send(f"**{jatekos}** ki lett tiltva a tesztelesbol.{' Indok: ' + indok if indok else ''}", ephemeral=True)
    else:
        await interaction.followup.send("Hiba tortent.", ephemeral=True)


@app_commands.command(name="tierlistunban", description="Jatekos visszavetele a tesztelesbe (admin)")
async def tierlistunban(interaction: discord.Interaction, jatekos: str):
    await interaction.response.defer(ephemeral=True)
    if not is_staff_member(interaction.user):
        await interaction.followup.send("Nincs jogod.", ephemeral=True)
        return

    if not WEBSITE_URL:
        await interaction.followup.send("WEBSITE_URL nincs beallitva.", ephemeral=True)
        return

    res = await api_set_ban(username=jatekos, banned=False)
    if res.get("status") == 200:
        await interaction.followup.send(f"**{jatekos}** vissza lett engedve a tesztelesbe.", ephemeral=True)
    else:
        await interaction.followup.send("Hiba tortent.", ephemeral=True)


@app_commands.command(name="removetierlist", description="Jatekos eltavolitasa a tierlistarol (admin)")
async def removetierlist(interaction: discord.Interaction, jatekos: str, jatekmod: str = None):
    await interaction.response.defer(ephemeral=True)
    if not is_staff_member(interaction.user):
        await interaction.followup.send("Nincs jogod.", ephemeral=True)
        return

    if not WEBSITE_URL:
        await interaction.followup.send("WEBSITE_URL nincs beallitva.", ephemeral=True)
        return

    res = await api_remove_player(username=jatekos, gamemode=jatekmod)
    if res.get("status") == 200:
        await interaction.followup.send(f"**{jatekos}** eltavolitva a tierlistarol.{' (' + jatekmod + ')' if jatekmod else ''}", ephemeral=True)
    else:
        await interaction.followup.send("Hiba tortent.", ephemeral=True)


# =========================
# COMMAND AUTOCOMPLETE
# =========================
async def gamemode_autocomplete(interaction: discord.Interaction, current: str):
    matches = [key for key in GAMEMODE_DISPLAY_NAMES.keys() if current.lower() in key.lower()]
    return [app_commands.Choice(name=GAMEMODE_DISPLAY_NAMES[k], value=k) for k in matches[:25]]


async def tier_autocomplete(interaction: discord.Interaction, current: str):
    matches = [r for r in RANKS if current.lower() in r.lower()]
    return [app_commands.Choice(name=r, value=r) for r in matches[:25]]


testresult._params["jatekmod"].autocomplete = gamemode_autocomplete
testresult._params["tier"].autocomplete = tier_autocomplete
cooldown._params["jatekmod"].autocomplete = gamemode_autocomplete


# =========================
# HEALTH SERVER
# =========================
from aiohttp import web

async def start_health_server():
    app = web.Application()

    async def health(_request):
        return web.Response(text="ok")

    async def verify_link(request):
        code = request.query.get("code", "")
        minecraft_name = request.query.get("minecraft", "")

        if not code or not minecraft_name:
            return web.json_response({"success": False, "error": "Missing code or minecraft parameter"}, status=400)

        discord_id = await verify_link_code_async(code.upper())
        if discord_id is None:
            return web.json_response({"success": False, "error": "Invalid or expired code"}, status=400)

        await link_minecraft_account_async(discord_id, minecraft_name)

        try:
            user = await bot.fetch_user(discord_id)
            if user:
                embed = discord.Embed(title="Osszekapcsolas sikeres!", description=f"A Discord fiokod ossze lett kapcsolva a **Minecraft** fiokoval!\n\n**Minecraftnev:** `{minecraft_name}`", color=discord.Color.green())
                await user.send(embed=embed)
        except Exception as e:
            print(f"Could not send DM: {e}")

        return web.json_response({"success": True, "discord_id": discord_id, "minecraft": minecraft_name})

    app.router.add_get("/health", health)
    app.router.add_get("/api/link/verify", verify_link)

    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "8080"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Health server running on :{port}")


# =========================
# BOT EVENTS
# =========================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id={bot.user.id})")

    bot.add_view(TicketPanelView())
    bot.add_view(CloseTicketView(owner_id=0, mode_key=""))

    # DEBUG: Print all registered commands
    print(f"DEBUG: Registered commands: {len(bot.tree._global_commands)} global, {len(bot.tree._guild_commands)} guild")
    for cmd in bot.tree._global_commands:
        print(f"  - /{cmd.name} (global)")
    for guild_id, cmds in bot.tree._guild_commands.items():
        for cmd in cmds:
            print(f"  - /{cmd.name} (guild {guild_id})")

    guild = discord.Object(id=GUILD_ID) if GUILD_ID else None

    try:
        if guild:
            await bot.tree.sync(guild=guild)
            print(f"Slash commands synced to guild {GUILD_ID}")
        else:
            await bot.tree.sync()
            print("Slash commands synced globally")
    except Exception as e:
        import traceback
        print(f"Sync failed: {e}")
        traceback.print_exc()


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    error_msg = f"Parancs hiba: {type(error).__name__}: {error}"
    if interaction.response.is_done():
        await interaction.followup.send(error_msg, ephemeral=True)
    else:
        await interaction.response.send_message(error_msg, ephemeral=True)


# =========================
# MAIN
# =========================
async def main():
    global http_session

    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN is missing")

    http_session = aiohttp.ClientSession()
    asyncio.create_task(start_health_server())

    try:
        await bot.start(DISCORD_TOKEN)
    finally:
        await http_session.close()


if __name__ == "__main__":
    asyncio.run(main())
