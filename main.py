import os
import json
import time
import asyncio
from typing import Dict, Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

import aiohttp
from aiohttp import web

# =========================
# ENV / CONFIG
# =========================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
STAFF_ROLE_ID = int(os.getenv("STAFF_ROLE_ID", "0"))
TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID", "0"))

WEBSITE_URL = os.getenv("WEBSITE_URL", "").rstrip("/")  # e.g. https://neontiers.vercel.app
BOT_API_KEY = os.getenv("BOT_API_KEY", "")              # shared secret between bot and website

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

    app.router.add_get("/health", health)

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

        if member.id != self.owner_id and not is_staff_member(member):
            await interaction.response.send_message("Nincs jogosultságod a ticket zárásához.", ephemeral=True)
            return

        await interaction.response.send_message("✅ Ticket zárása... 3 mp múlva törlöm a csatornát.", ephemeral=True)

        set_last_closed(self.owner_id, self.mode_key, time.time())
        set_open_ticket_channel_id(self.owner_id, self.mode_key, None)

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

            # Build embed
            embed = discord.Embed(
                title=f"{name} profilja",
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
            embed.add_field(name="Összes pont", value=str(total_points), inline=False)

            # Skin
            skin_url = f"https://minotar.net/helm/{name}/128.png"
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

        # First, check if the player exists in the tierlist
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
                await interaction.followup.send(
                    f"❌ **{name}** nincs a tierlistán.",
                    ephemeral=True
                )
                return

            # Check for case mismatch warning
            actual_username = tests[0].get("username", "")
            case_warning = ""
            if actual_username.lower() == name.lower() and actual_username != name:
                case_warning = f"\n⚠️ **Figyelem:** A tierlistán **`{actual_username}`** van (nagy G), nem `{name}`!\n"

            # Show info about the player
            modes_info = "\n".join([f"• **{t.get('gamemode', '?')}**: {t.get('rank', '?')} ({t.get('points', 0)}pt)" for t in tests])

        # Create confirmation embed
        embed = discord.Embed(
            title="⚠️ FIGYELMEZTETÉS - Törlés előtt!",
            description=f"Biztosan eltávolítod **{name}**-t a tierlistáról?\n\n"
                       f"**Jelenlegi tierlist bejegyzések:**\n{modes_info}" + 
                       (case_warning if case_warning else "") + "\n\n"
                       f"❗ **EZ EGY VÉGÉGES MŰVELET!** A játékos minden gamemód-beli eredménye törlésre kerül.",
            color=discord.Color.red()
        )
        embed.set_footer(text=f"Kéri: {interaction.user.display_name}")

        # Send confirmation view
        view = ConfirmRemoveView(username=name, actual_username=actual_username, moderator=interaction.user)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    except aiohttp.ClientError as e:
        await interaction.followup.send(f"⚠️ Web hiba: {type(e).__name__}: {e}", ephemeral=True)
    except asyncio.TimeoutError:
        await interaction.followup.send("⚠️ Web timeout (nem válaszolt 10 mp-en belül).", ephemeral=True)
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

    try:
        await bot.start(DISCORD_TOKEN)
    finally:
        if http_session:
            await http_session.close()


if __name__ == "__main__":
    asyncio.run(main())
