# main.py
import os
import json
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Any, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands

# aiohttp is installed with discord.py, so this is safe
import aiohttp

# =========================================================
# ENV / CONFIG
# =========================================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("TOKEN") or ""
BOT_API_KEY = os.getenv("BOT_API_KEY", "")  # must match Vercel BOT_API_KEY
WEBSITE_URL = (os.getenv("WEBSITE_URL", "https://neontiers.vercel.app") or "").rstrip("/")

# Your server config (defaults you said are correct)
GUILD_ID = int(os.getenv("GUILD_ID", "1469740655520780631"))
STAFF_ROLE_ID = int(os.getenv("STAFF_ROLE_ID", "1469755118634270864"))
TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID", "1469766438238687496"))

# 14 day cooldown per user per mode
COOLDOWN_SECONDS = 14 * 24 * 60 * 60

# persistent data
DATA_DIR = "./data"
TESTS_FILE = os.path.join(DATA_DIR, "tests.json")
COOLDOWNS_FILE = os.path.join(DATA_DIR, "cooldowns.json")

# =========================================================
# MODES + ROLE PINGS
# =========================================================
MODE_LIST = [
    "Vanilla", "UHC", "Pot", "NethPot", "SMP",
    "Sword", "Axe", "Mace", "Cart", "Creeper",
    "DiaSMP", "OGVanilla", "ShieldlessUHC",
    "SpearMace", "SpearElytra",
]

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

# ranks (short codes only)
RANK_LIST = ["Unranked", "LT5", "HT5", "LT4", "HT4", "LT3", "HT3", "LT2", "HT2", "LT1", "HT1"]
RANK_POINTS = {
    "Unranked": 0,
    "LT5": 1, "HT5": 2,
    "LT4": 3, "HT4": 4,
    "LT3": 5, "HT3": 6,
    "LT2": 7, "HT2": 8,
    "LT1": 9, "HT1": 10,
}

# =========================================================
# JSON STORAGE
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

def get_tests() -> Dict[str, Any]:
    return load_json(TESTS_FILE, {"players": {}})

def set_tests(data: Dict[str, Any]):
    save_json(TESTS_FILE, data)

def get_cooldowns() -> Dict[str, Dict[str, int]]:
    return load_json(COOLDOWNS_FILE, {})

def set_cooldowns(data: Dict[str, Dict[str, int]]):
    save_json(COOLDOWNS_FILE, data)

# =========================================================
# HEALTH SERVER (thread) - prevents host from killing process
# =========================================================
class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):
        return  # silence

def start_health_server_thread():
    port = int(os.getenv("PORT", "8080"))
    def run():
        httpd = HTTPServer(("0.0.0.0", port), _HealthHandler)
        print(f"Health server running on :{port}")
        httpd.serve_forever()

    t = threading.Thread(target=run, daemon=True)
    t.start()

# =========================================================
# DISCORD BOT
# =========================================================
intents = discord.Intents.default()
intents.guilds = True
intents.members = True

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
# WEBSITE POST (must send username + mode)
# =========================================================
async def post_test_to_website(payload: Dict[str, Any]) -> Tuple[bool, int, str]:
    if not BOT_API_KEY:
        return False, 0, "BOT_API_KEY missing (set it on Vercel and Railway)."

    url = f"{WEBSITE_URL}/api/tests"
    headers = {
        "Authorization": f"Bearer {BOT_API_KEY}",
        "x-api-key": BOT_API_KEY,
        "Content-Type": "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=20) as resp:
                text = await resp.text()
                return (200 <= resp.status < 300), resp.status, text
    except Exception as e:
        return False, 0, str(e)

# =========================================================
# EMBED
# =========================================================
def skin_url(username: str) -> str:
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
# /testresult (MC name + tester + gamemode + tier)
# - previous rank auto
# - ONLY ONE entry per mode (overwrite)
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
        await interaction.response.send_message("Ez a parancs csak a NeoTiers szerveren használható.", ephemeral=True)
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

    data = get_tests()
    players = data.setdefault("players", {})
    key = mc_username.lower()

    player = players.get(key, {"username": mc_username, "results": {}})
    player["username"] = mc_username
    results = player.setdefault("results", {})

    prev_rank = "Unranked"
    if mode in results and isinstance(results[mode], dict):
        prev_rank = results[mode].get("rank", "Unranked") or "Unranked"

    # overwrite mode -> ONLY LATEST COUNTS
    results[mode] = {
        "rank": new_rank,
        "tester_id": tester.id,
        "tester_tag": str(tester),
        "ts": int(time.time()),
    }
    players[key] = player
    set_tests(data)

    delta = RANK_POINTS.get(new_rank, 0) - RANK_POINTS.get(prev_rank, 0)

    embed = make_test_embed(mc_username, tester, mode, prev_rank, new_rank)
    await interaction.response.send_message(embed=embed)

    # IMPORTANT: website expects username + mode keys
    website_payload = {
        "username": mc_username,
        "mode": mode,
        "rank": new_rank,

        # extra info
        "previousRank": prev_rank,
        "testerId": tester.id,
        "testerTag": str(tester),
        "sourceGuildId": interaction.guild.id,
        "timestamp": int(time.time()),
        "pointsDelta": delta,
    }

    ok, status, text = await post_test_to_website(website_payload)
    if ok:
        await interaction.followup.send(
            f"✅ Mentve + weboldal frissítve.\nElőző: `{prev_rank}` → Elért: `{new_rank}` | {delta:+d} pont",
            ephemeral=True
        )
    else:
        await interaction.followup.send(
            f"⚠️ Mentés hiba a weboldal felé (status {status}) {text}",
            ephemeral=True
        )

# =========================================================
# Ticket system
# - can open different mode tickets
# - cannot open same mode ticket twice
# - 14 day cooldown after closing
# =========================================================
def make_ticket_channel_name(mode: str, user_id: int) -> str:
    safe_mode = mode.lower().replace(" ", "").replace("-", "")
    return f"ticket-{safe_mode}-{user_id}"

async def find_existing_ticket_channel(guild: discord.Guild, mode: str, user_id: int) -> Optional[discord.TextChannel]:
    name = make_ticket_channel_name(mode, user_id)
    for ch in guild.text_channels:
        if ch.name == name:
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

        if not (is_staff_or_admin(interaction.user) or interaction.user.id == self.opener_id):
            await interaction.response.send_message("Nincs jogosultságod bezárni.", ephemeral=True)
            return

        await interaction.response.send_message("✅ Ticket zárása... 3 mp és törlöm a csatornát.", ephemeral=True)

        set_cooldown_now(self.opener_id, self.mode)

        ch = interaction.channel
        await discord.utils.sleep_until(discord.utils.utcnow() + discord.utils.timedelta(seconds=3))

        try:
            if isinstance(ch, discord.TextChannel):
                await ch.delete(reason="Ticket closed")
        except discord.Forbidden:
            try:
                await interaction.followup.send("⚠️ Nem tudtam törölni a csatornát (hiányzó jog: Manage Channels).", ephemeral=True)
            except Exception:
                pass

class TicketModeSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Válassz játékmódot...",
            min_values=1,
            max_values=1,
            options=[discord.SelectOption(label=m, value=m) for m in MODE_LIST],
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        guild = interaction.guild
        user = interaction.user
        mode = self.values[0]

        left = cooldown_left(user.id, mode)
        if left > 0:
            days = left // 86400
            hours = (left % 86400) // 3600
            await interaction.response.send_message(
                f"⏳ `{mode}` ticketre még cooldown van: {days} nap {hours} óra.",
                ephemeral=True,
            )
            return

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
                name=make_ticket_channel_name(mode, user.id),
                category=category,
                overwrites=overwrites,
                reason="Ticket created",
            )
        except discord.Forbidden:
            await interaction.response.send_message("⚠️ Nincs jogom csatornát létrehozni (Manage Channels kell).", ephemeral=True)
            return

        ping_text = ping_role.mention if ping_role else (staff_role.mention if staff_role else "@here")

        await channel.send(
            content=f"{ping_text}\n**Teszt kérés**\nKattints a listában és válassz játékmódot.",
            view=CloseTicketView(mode=mode, opener_id=user.id),
        )

        await interaction.response.send_message(f"✅ Ticket létrehozva: {channel.mention}", ephemeral=True)

class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketModeSelect())

@app_commands.command(name="ticketpanel", description="Teszt ticket panel küldése.")
async def ticketpanel(interaction: discord.Interaction):
    if not interaction.guild or interaction.guild.id != GUILD_ID:
        await interaction.response.send_message("Ez a parancs csak a NeoTiers szerveren használható.", ephemeral=True)
        return
    if not isinstance(interaction.user, discord.Member) or not is_staff_or_admin(interaction.user):
        await interaction.response.send_message("Nincs jogosultságod ehhez.", ephemeral=True)
        return

    embed = discord.Embed(
        title="Teszt kérés",
        description="Válassz játékmódot a listából a ticket nyitáshoz.",
        color=discord.Color.blurple(),
    )
    await interaction.response.send_message(embed=embed, view=TicketPanelView())

# =========================================================
# Setup / Sync (IMPORTANT: guild sync here)
# =========================================================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id={bot.user.id})")

async def _sync_guild_commands():
    guild_obj = discord.Object(id=GUILD_ID)
    bot.tree.clear_commands(guild=guild_obj)

    bot.tree.add_command(testresult, guild=guild_obj)
    bot.tree.add_command(ticketpanel, guild=guild_obj)

    await bot.tree.sync(guild=guild_obj)
    print(f"Slash commands synced to guild {GUILD_ID}")

@bot.event
async def setup_hook():
    # persistent views survive restarts for existing messages
    bot.add_view(TicketPanelView())
    bot.add_view(CloseTicketView(mode="Mace", opener_id=0))  # dummy to register, doesn't affect logic

    # sync once on boot
    try:
        await _sync_guild_commands()
    except Exception as e:
        print("Sync error:", e)

# =========================================================
# RUN
# =========================================================
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN env is missing")

    start_health_server_thread()
    bot.run(DISCORD_TOKEN)
