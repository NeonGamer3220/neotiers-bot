# main.py
import os
import json
import asyncio
import time
from typing import Dict, Any, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands

# discord.py already depends on aiohttp, so we can use it without installing "requests"
import aiohttp
from aiohttp import web

# =========================================================
# CONFIG (ENV)
# =========================================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("TOKEN") or ""
BOT_API_KEY = os.getenv("BOT_API_KEY", "")  # same key as Vercel env BOT_API_KEY
WEBSITE_URL = os.getenv("WEBSITE_URL", "https://neontiers.vercel.app").rstrip("/")

# Your NeoTiers ticket bot config (you said these are correct)
GUILD_ID = int(os.getenv("GUILD_ID", "1469740655520780631"))
STAFF_ROLE_ID = int(os.getenv("STAFF_ROLE_ID", "1469755118634270864"))
TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID", "1469766438238687496"))

# 14 day cooldown per user per gamemode
COOLDOWN_SECONDS = 14 * 24 * 60 * 60

# Data storage
DATA_DIR = "./data"
TESTS_FILE = os.path.join(DATA_DIR, "tests.json")
COOLDOWNS_FILE = os.path.join(DATA_DIR, "cooldowns.json")

# =========================================================
# GAME MODES + TICKET PING ROLES
# (Your list, incl. SpearMace and SpearElytra)
# =========================================================
MODE_LIST = [
    "Vanilla", "UHC", "Pot", "NethPot", "SMP",
    "Sword", "Axe", "Mace", "Cart", "Creeper",
    "DiaSMP", "OGVanilla", "ShieldlessUHC",
    "SpearMace", "SpearElytra",
]

# Ping role IDs per mode (you gave these)
MODE_PING_ROLE: Dict[str, int] = {
    "Mace": 1469763612452196375,
    "Sword": 1469763677141074125,
    "Axe": 1469763738889486518,
    "Pot": 1469763780593324032,
    "NethPot": 1469763817218117697,
    "SMP": 1469764274955223161,
    "UHC": 1469765994988704030,
    "Vanilla": 1469763891226480926,
    "OGVanilla": 1469764329460203571,
    "ShieldlessUHC": 1469766017243807865,
    "SpearElytra": 1469968762575912970,
    "SpearMace": 1469968704203788425,
    "Cart": 1469763920871952435,
    "DiaSMP": 1469763946968911893,
    "Creeper": 1469764200812249180,
}

# =========================================================
# RANKS (short codes only, as you requested)
# =========================================================
RANK_LIST = ["Unranked", "LT5", "HT5", "LT4", "HT4", "LT3", "HT3", "LT2", "HT2", "LT1", "HT1"]

# Points for ranks (edit if you want)
RANK_POINTS = {
    "Unranked": 0,
    "LT5": 1, "HT5": 2,
    "LT4": 3, "HT4": 4,
    "LT3": 5, "HT3": 6,
    "LT2": 7, "HT2": 8,
    "LT1": 9, "HT1": 10,
}

# =========================================================
# UTIL: JSON storage
# =========================================================
def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)

def load_json(path: str, default: Any) -> Any:
    ensure_data_dir()
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path: str, data: Any):
    ensure_data_dir()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

# tests structure:
# {
#   "players": {
#       "<mc_username_lower>": {
#           "username": "NeonGamer322",
#           "results": {
#               "Mace": {"rank": "HT3", "tester_id": 123, "tester_tag": "Name#0001", "ts": 123456},
#               ...
#           }
#       }
#   }
# }
def get_tests() -> Dict[str, Any]:
    return load_json(TESTS_FILE, {"players": {}})

def set_tests(data: Dict[str, Any]):
    save_json(TESTS_FILE, data)

# cooldowns structure:
# {
#   "<discord_user_id>": {
#       "Mace": <unix_ts_last_closed>,
#       ...
#   }
# }
def get_cooldowns() -> Dict[str, Dict[str, int]]:
    return load_json(COOLDOWNS_FILE, {})

def set_cooldowns(data: Dict[str, Dict[str, int]]):
    save_json(COOLDOWNS_FILE, data)

# =========================================================
# DISCORD BOT
# =========================================================
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = False  # not needed

bot = commands.Bot(command_prefix="!", intents=intents)

# =========================================================
# PERMISSIONS
# =========================================================
def is_staff_or_admin(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    staff_role = member.guild.get_role(STAFF_ROLE_ID)
    return bool(staff_role and staff_role in member.roles)

# =========================================================
# WEBSITE POST (FIX: MUST SEND username + mode)
# =========================================================
async def post_test_to_website(payload: Dict[str, Any]) -> Tuple[bool, int, str]:
    """
    Returns: (ok, status, text)
    """
    if not BOT_API_KEY:
        return False, 0, "BOT_API_KEY missing"

    url = f"{WEBSITE_URL}/api/tests"
    headers = {
        "Authorization": f"Bearer {BOT_API_KEY}",
        "x-api-key": BOT_API_KEY,
        "Content-Type": "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=15) as resp:
                text = await resp.text()
                return (200 <= resp.status < 300), resp.status, text
    except Exception as e:
        return False, 0, str(e)

# =========================================================
# EMBED BUILDER
# =========================================================
def skin_url(username: str) -> str:
    # Crafatar renders (no API key needed)
    # 128px cube head
    return f"https://crafatar.com/renders/head/{username}?overlay&size=128"

def make_test_embed(mc_username: str, tester: discord.Member, mode: str, prev_rank: str, new_rank: str) -> discord.Embed:
    e = discord.Embed(
        title=f"{mc_username} teszt eredménye 🏆",
        color=discord.Color.dark_theme(),
    )
    e.add_field(name="Tesztelő:", value=tester.mention, inline=False)
    e.add_field(name="Játékmód:", value=mode, inline=False)
    e.add_field(name="Minecraft név:", value=mc_username, inline=False)
    e.add_field(name="Előző rang:", value=prev_rank, inline=False)
    e.add_field(name="Elért rang:", value=new_rank, inline=False)
    e.set_thumbnail(url=skin_url(mc_username))
    return e

# =========================================================
# TESTRESULT COMMAND (MC name + tester + mode + rank)
# - prev rank auto from saved results
# - overwrite per mode (only latest per mode counts)
# =========================================================
@app_commands.command(name="testresult", description="Teszt eredmény mentése + weboldal frissítése.")
@app_commands.describe(
    username="Minecraft név (ebből lesz a skin is)",
    tester="Tesztelő (Discord tag)",
    gamemode="Játékmód",
    rank="Elért rang",
)
@app_commands.choices(
    gamemode=[app_commands.Choice(name=m, value=m) for m in MODE_LIST],
    rank=[app_commands.Choice(name=r, value=r) for r in RANK_LIST],
)
async def testresult(
    interaction: discord.Interaction,
    username: str,
    tester: discord.Member,
    gamemode: app_commands.Choice[str],
    rank: app_commands.Choice[str],
):
    if not interaction.guild or interaction.guild.id != GUILD_ID:
        await interaction.response.send_message("Ez a parancs csak a beállított szerveren használható.", ephemeral=True)
        return

    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("Hiba: Member nem elérhető.", ephemeral=True)
        return

    if not is_staff_or_admin(interaction.user):
        await interaction.response.send_message("Nincs jogosultságod ehhez.", ephemeral=True)
        return

    mc_username = username.strip()
    if not mc_username:
        await interaction.response.send_message("Adj meg Minecraft nevet.", ephemeral=True)
        return

    mode = gamemode.value
    new_rank = rank.value

    # Load tests
    data = get_tests()
    players = data.setdefault("players", {})
    key = mc_username.lower()

    player = players.get(key, {"username": mc_username, "results": {}})
    # keep latest casing
    player["username"] = mc_username
    results = player.setdefault("results", {})

    prev_rank = "Unranked"
    if mode in results and isinstance(results[mode], dict):
        prev_rank = results[mode].get("rank", "Unranked") or "Unranked"

    # Overwrite this mode with latest test (IMPORTANT FIX: only one per mode)
    results[mode] = {
        "rank": new_rank,
        "tester_id": tester.id,
        "tester_tag": str(tester),
        "ts": int(time.time()),
    }
    players[key] = player
    set_tests(data)

    # points delta based on old vs new (you can change if you want)
    delta = RANK_POINTS.get(new_rank, 0) - RANK_POINTS.get(prev_rank, 0)

    # Send the public embed (THIS is the visible message you wanted)
    embed = make_test_embed(mc_username, tester, mode, prev_rank, new_rank)

    # Prepare website payload (CRITICAL FIX: username + mode keys must exist)
    website_payload = {
        "username": mc_username,     # REQUIRED by your website
        "mode": mode,               # REQUIRED by your website
        "rank": new_rank,           # current rank
        "previousRank": prev_rank,  # extra info
        "testerId": tester.id,
        "testerTag": str(tester),
        "sourceGuildId": interaction.guild.id,
        "timestamp": int(time.time()),
        "pointsDelta": delta,
    }

    await interaction.response.send_message(embed=embed)

    ok, status, text = await post_test_to_website(website_payload)
    if ok:
        await interaction.followup.send(f"✅ Mentve + weboldal frissítve.\nElőző: `{prev_rank}` → Elért: `{new_rank}` | {delta:+d} pont", ephemeral=True)
    else:
        await interaction.followup.send(f"⚠️ Mentés hiba a weboldal felé (status {status}) {text}", ephemeral=True)

bot.tree.add_command(testresult)

# =========================================================
# TICKET SYSTEM
# - Can open different mode tickets
# - Cannot open same mode ticket if already exists
# - 14 day cooldown per mode after closing
# - Creates channel in category, pings mode role (NOT tester)
# - Close button deletes channel after 3s and sets cooldown
# =========================================================
def make_ticket_channel_name(mode: str, user: discord.Member) -> str:
    safe_mode = mode.lower().replace(" ", "").replace("-", "")
    return f"ticket-{safe_mode}-{user.id}"

async def find_existing_ticket_channel(guild: discord.Guild, mode: str, user_id: int) -> Optional[discord.TextChannel]:
    prefix = f"ticket-{mode.lower().replace(' ', '').replace('-', '')}-{user_id}"
    for ch in guild.text_channels:
        if ch.name == prefix:
            return ch
    return None

def cooldown_left(user_id: int, mode: str) -> int:
    cds = get_cooldowns()
    last = cds.get(str(user_id), {}).get(mode, 0)
    now = int(time.time())
    left = (last + COOLDOWN_SECONDS) - now
    return left if left > 0 else 0

def set_cooldown_now(user_id: int, mode: str):
    cds = get_cooldowns()
    u = cds.setdefault(str(user_id), {})
    u[mode] = int(time.time())
    set_cooldowns(cds)

class CloseTicketView(discord.ui.View):
    def __init__(self, mode: str, opener_id: int):
        super().__init__(timeout=None)
        self.mode = mode
        self.opener_id = opener_id

    @discord.ui.button(label="Ticket zárása", style=discord.ButtonStyle.danger, emoji="🔒")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        # allow staff/admin or the opener
        if not (is_staff_or_admin(interaction.user) or interaction.user.id == self.opener_id):
            await interaction.response.send_message("Nincs jogosultságod bezárni.", ephemeral=True)
            return

        await interaction.response.send_message("✅ Ticket zárása... 3 mp és törlöm a csatornát.", ephemeral=True)

        # set cooldown when closing (14 days)
        set_cooldown_now(self.opener_id, self.mode)

        ch = interaction.channel
        await asyncio.sleep(3)

        # try delete
        try:
            if isinstance(ch, discord.TextChannel):
                await ch.delete(reason="Ticket closed")
        except Exception:
            # if missing perms, tell staff
            try:
                await interaction.followup.send("⚠️ Nem tudtam törölni a csatornát (hiányzó jogosultság?).", ephemeral=True)
            except Exception:
                pass

class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketModeSelect())

class TicketModeSelect(discord.ui.Select):
    def __init__(self):
        options = []
        for m in MODE_LIST:
            options.append(discord.SelectOption(label=m, value=m))
        super().__init__(
            placeholder="Válassz játékmódot...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        guild = interaction.guild
        user = interaction.user
        mode = self.values[0]

        # cooldown check (per mode)
        left = cooldown_left(user.id, mode)
        if left > 0:
            days = left // 86400
            hours = (left % 86400) // 3600
            await interaction.response.send_message(
                f"⏳ `{mode}` ticketre még cooldown van: {days} nap {hours} óra.",
                ephemeral=True,
            )
            return

        # cannot open same mode ticket twice
        existing = await find_existing_ticket_channel(guild, mode, user.id)
        if existing:
            await interaction.response.send_message("Van már ilyen ticketed.", ephemeral=True)
            return

        category = guild.get_channel(TICKET_CATEGORY_ID)
        if not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message("Ticket kategória hibásan van beállítva.", ephemeral=True)
            return

        staff_role = guild.get_role(STAFF_ROLE_ID)
        ping_role = guild.get_role(MODE_PING_ROLE.get(mode, STAFF_ROLE_ID))

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True)
        if ping_role and ping_role != staff_role:
            overwrites[ping_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        try:
            channel = await guild.create_text_channel(
                name=make_ticket_channel_name(mode, user),
                category=category,
                overwrites=overwrites,
                reason="Ticket created",
            )
        except discord.Forbidden:
            await interaction.response.send_message("⚠️ Nincs jogom csatornát létrehozni (Manage Channels kell).", ephemeral=True)
            return

        # ping the mode role (NOT the tester)
        ping_text = ping_role.mention if ping_role else (staff_role.mention if staff_role else "@here")

        await channel.send(
            content=f"{ping_text}\n**Teszt kérés**\nKattints egy alábbi gombra, hogy tudj tesztelni a gombon feltüntetett játékmódból.",
            view=CloseTicketView(mode=mode, opener_id=user.id),
        )

        await interaction.response.send_message(f"✅ Ticket létrehozva: {channel.mention}", ephemeral=True)

@app_commands.command(name="ticketpanel", description="Teszt ticket panel küldése.")
async def ticketpanel(interaction: discord.Interaction):
    if not interaction.guild or interaction.guild.id != GUILD_ID:
        await interaction.response.send_message("Ez a parancs csak a beállított szerveren használható.", ephemeral=True)
        return
    if not isinstance(interaction.user, discord.Member) or not is_staff_or_admin(interaction.user):
        await interaction.response.send_message("Nincs jogosultságod ehhez.", ephemeral=True)
        return

    embed = discord.Embed(
        title="Teszt kérés",
        description="Kattints egy alábbi gombra, hogy tudj tesztelni a gombon feltüntetett játékmódból.",
        color=discord.Color.blurple(),
    )
    await interaction.response.send_message(embed=embed, view=TicketPanelView())

bot.tree.add_command(ticketpanel)

# =========================================================
# SIMPLE HEALTH SERVER (Railway / uptime)
# =========================================================
async def start_health_server():
    async def handle(request):
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "8080"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Health server running on :{port}")

# =========================================================
# BOT EVENTS
# =========================================================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id={bot.user.id})")
    try:
        guild = discord.Object(id=GUILD_ID)
        await bot.tree.sync(guild=guild)
        print(f"Slash commands synced to guild {GUILD_ID}")
    except Exception as e:
        print("Sync error:", e)

async def main():
    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN env is missing")
    await start_health_server()
    await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
