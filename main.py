import os
import re
import time
import sqlite3
import asyncio
from typing import Optional, Dict, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from aiohttp import ClientSession
from aiohttp import web

# =========================
# ENV CONFIG
# =========================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()

GUILD_ID = int(os.getenv("GUILD_ID", "0"))
STAFF_ROLE_ID = int(os.getenv("STAFF_ROLE_ID", "0"))  # staff role that should see tickets + can use commands
TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID", "0"))

# Web API (Vercel Next.js) - shared secret between bot and website
WEBSITE_BASE_URL = os.getenv("WEBSITE_BASE_URL", "https://neontiers.vercel.app").rstrip("/")
BOT_API_KEY = os.getenv("BOT_API_KEY", "").strip()

# Optional extra allowed role IDs for /testresult and admin commands
# comma separated: "123,456"
ALLOWED_ROLE_IDS = {
    int(x.strip()) for x in os.getenv("ALLOWED_ROLE_IDS", "").split(",") if x.strip().isdigit()
}

# =========================
# CONSTANTS (MODES / TIERS)
# =========================
MODE_LIST = [
    "Sword",
    "Axe",
    "Mace",
    "Pot",
    "NethPot",
    "Creeper",
    "DiaSMP",
    "UHC",
    "Vanilla",
    "SpearElytra",
    "SpearMace",
    "OGVanilla",
    "ShieldlessUHC",
    "SMP",
    "Cart",
]

# Ticket ping role IDs (as you gave earlier)
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

# Tier options (short codes only, as you demanded)
TIER_LIST = [
    "Unranked",
    "LT5",
    "HT5",
    "LT4",
    "HT4",
    "LT3",
    "HT3",
    "LT2",
    "HT2",
    "LT1",
    "HT1",
]

# Points per tier (edit if you want)
TIER_POINTS = {
    "Unranked": 0,
    "LT5": 1,
    "HT5": 2,
    "LT4": 3,
    "HT4": 4,
    "LT3": 5,
    "HT3": 6,
    "LT2": 7,
    "HT2": 8,
    "LT1": 9,
    "HT1": 10,
}

# Cooldown in seconds: 14 days
COOLDOWN_SECONDS = 14 * 24 * 60 * 60

# =========================
# DB (SQLite)
# =========================
DB_PATH = "data.db"


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    cur = conn.cursor()

    # latest test per (player, mode)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tests (
            player TEXT NOT NULL,
            mode TEXT NOT NULL,
            tier TEXT NOT NULL,
            tester_id INTEGER NOT NULL,
            tester_name TEXT NOT NULL,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY(player, mode)
        )
        """
    )

    # open tickets per (user, mode) so you can open different modes, but not same mode twice
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS open_tickets (
            user_id INTEGER NOT NULL,
            mode TEXT NOT NULL,
            channel_id INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            PRIMARY KEY(user_id, mode)
        )
        """
    )

    # cooldowns per (user, mode), updated when ticket is closed
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS cooldowns (
            user_id INTEGER NOT NULL,
            mode TEXT NOT NULL,
            last_closed INTEGER NOT NULL,
            PRIMARY KEY(user_id, mode)
        )
        """
    )

    conn.commit()
    conn.close()


def get_previous_tier(player: str, mode: str) -> str:
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT tier FROM tests WHERE player=? AND mode=?", (player, mode))
    row = cur.fetchone()
    conn.close()
    return row["tier"] if row else "Unranked"


def upsert_test(player: str, mode: str, tier: str, tester_id: int, tester_name: str) -> str:
    prev = get_previous_tier(player, mode)
    now = int(time.time())
    conn = db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO tests(player, mode, tier, tester_id, tester_name, updated_at)
        VALUES(?,?,?,?,?,?)
        ON CONFLICT(player, mode) DO UPDATE SET
            tier=excluded.tier,
            tester_id=excluded.tester_id,
            tester_name=excluded.tester_name,
            updated_at=excluded.updated_at
        """,
        (player, mode, tier, tester_id, tester_name, now),
    )
    conn.commit()
    conn.close()
    return prev


def get_total_points(player: str) -> int:
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT mode, tier FROM tests WHERE player=?", (player,))
    rows = cur.fetchall()
    conn.close()
    total = 0
    for r in rows:
        total += TIER_POINTS.get(r["tier"], 0)
    return total


def has_open_ticket(user_id: int, mode: str) -> Optional[int]:
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT channel_id FROM open_tickets WHERE user_id=? AND mode=?", (user_id, mode))
    row = cur.fetchone()
    conn.close()
    return int(row["channel_id"]) if row else None


def set_open_ticket(user_id: int, mode: str, channel_id: int):
    conn = db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO open_tickets(user_id, mode, channel_id, created_at)
        VALUES(?,?,?,?)
        ON CONFLICT(user_id, mode) DO UPDATE SET
            channel_id=excluded.channel_id,
            created_at=excluded.created_at
        """,
        (user_id, mode, channel_id, int(time.time())),
    )
    conn.commit()
    conn.close()


def clear_open_ticket_by_channel(channel_id: int):
    conn = db()
    cur = conn.cursor()
    cur.execute("DELETE FROM open_tickets WHERE channel_id=?", (channel_id,))
    conn.commit()
    conn.close()


def get_last_closed(user_id: int, mode: str) -> int:
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT last_closed FROM cooldowns WHERE user_id=? AND mode=?", (user_id, mode))
    row = cur.fetchone()
    conn.close()
    return int(row["last_closed"]) if row else 0


def set_last_closed(user_id: int, mode: str, ts: int):
    conn = db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO cooldowns(user_id, mode, last_closed)
        VALUES(?,?,?)
        ON CONFLICT(user_id, mode) DO UPDATE SET
            last_closed=excluded.last_closed
        """,
        (user_id, mode, ts),
    )
    conn.commit()
    conn.close()


def sanitize_mc_name(name: str) -> str:
    name = name.strip()
    # Allow typical MC username pattern
    if not re.fullmatch(r"[A-Za-z0-9_]{3,16}", name):
        return name  # we won't hard-block, but it may break skin preview
    return name


# =========================
# BOT SETUP
# =========================
intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

http_session: Optional[ClientSession] = None


def is_allowed_for_admin(interaction: discord.Interaction) -> bool:
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return False
    member: discord.Member = interaction.user

    # admin permission OR STAFF_ROLE_ID OR ALLOWED_ROLE_IDS
    if member.guild_permissions.administrator:
        return True
    if STAFF_ROLE_ID and any(r.id == STAFF_ROLE_ID for r in member.roles):
        return True
    if ALLOWED_ROLE_IDS and any(r.id in ALLOWED_ROLE_IDS for r in member.roles):
        return True
    return False


# =========================
# WEB KEEPALIVE (prevents Railway stop)
# =========================
async def _health(request):
    return web.Response(text="ok")


async def start_web_server():
    port = int(os.getenv("PORT", "8080"))
    app = web.Application()
    app.router.add_get("/", _health)
    app.router.add_get("/health", _health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Health server running on :{port}")


# =========================
# TICKET UI
# =========================
class CloseTicketView(discord.ui.View):
    def __init__(self, opener_id: int, mode: str):
        super().__init__(timeout=None)
        self.opener_id = opener_id
        self.mode = mode

    @discord.ui.button(label="Ticket lezárása", style=discord.ButtonStyle.danger, custom_id="ticket_close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not interaction.channel:
            return

        channel: discord.TextChannel = interaction.channel  # type: ignore
        user_id = self.opener_id
        mode = self.mode

        # Only opener or staff/admin can close
        can_close = (interaction.user.id == user_id) or is_allowed_for_admin(interaction)
        if not can_close:
            await interaction.response.send_message("Nincs jogosultságod lezárni ezt a ticketet.", ephemeral=True)
            return

        # Mark cooldown + clear open ticket
        now = int(time.time())
        set_last_closed(user_id, mode, now)
        clear_open_ticket_by_channel(channel.id)

        await interaction.response.send_message("Ticket lezárva. 3 mp múlva törlöm a csatornát…", ephemeral=True)
        await asyncio.sleep(3)

        try:
            await channel.delete(reason="Ticket closed")
        except discord.Forbidden:
            # If bot cannot delete, at least inform
            try:
                await channel.send("❌ Nincs jogom törölni ezt a csatornát. Adj a botnak **Csatornák kezelése** jogot.")
            except Exception:
                pass


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        # Create buttons dynamically (Discord max 25 components per view)
        # We'll add in 2 rows/lines; if you add more later, we may need multiple views.
        for mode in MODE_LIST:
            self.add_item(TicketButton(mode=mode))


class TicketButton(discord.ui.Button):
    def __init__(self, mode: str):
        super().__init__(
            label=mode,
            style=discord.ButtonStyle.primary,
            custom_id=f"ticket_open_{mode.lower()}",
        )
        self.mode = mode

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        guild = interaction.guild
        member: discord.Member = interaction.user

        if TICKET_CATEGORY_ID == 0:
            await interaction.response.send_message("❌ TICKET_CATEGORY_ID nincs beállítva.", ephemeral=True)
            return

        category = guild.get_channel(TICKET_CATEGORY_ID)
        if not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message("❌ TICKET_CATEGORY_ID nem kategória csatornára mutat.", ephemeral=True)
            return

        mode = self.mode

        # Block opening same mode if already open
        existing = has_open_ticket(member.id, mode)
        if existing:
            await interaction.response.send_message("Van már ticketed ebből a játékmódból!", ephemeral=True)
            return

        # Cooldown check for this mode only
        last = get_last_closed(member.id, mode)
        now = int(time.time())
        remaining = (last + COOLDOWN_SECONDS) - now
        if remaining > 0:
            days = remaining // 86400
            hours = (remaining % 86400) // 3600
            await interaction.response.send_message(
                f"⏳ **{mode}** ticket cooldown aktív.\nMég: **{days} nap {hours} óra**.",
                ephemeral=True,
            )
            return

        # Create channel permissions
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }

        staff_role = guild.get_role(STAFF_ROLE_ID) if STAFF_ROLE_ID else None
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )

        # Create channel
        safe_name = re.sub(r"[^a-z0-9\-]", "", member.display_name.lower().replace(" ", "-"))[:16] or "user"
        channel_name = f"{mode.lower()}-{safe_name}"

        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                reason="Ticket created",
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Nincs jogom csatornát létrehozni. Adj a botnak **Csatornák kezelése** jogot.",
                ephemeral=True,
            )
            return

        set_open_ticket(member.id, mode, channel.id)

        # Ping correct role for this mode
        ping_role_id = MODE_PING_ROLE.get(mode, 0)
        ping_text = ""
        if ping_role_id:
            ping_text = f"<@&{ping_role_id}>"

        embed = discord.Embed(
            title="Teszt kérés",
            description="Kattints egy alábbi gombra, hogy tudd tesztelni a gombon feltüntetett játékmódból.",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Játékmód", value=mode, inline=True)
        embed.add_field(name="Kérő", value=member.mention, inline=True)

        await channel.send(content=ping_text, embed=embed, view=CloseTicketView(opener_id=member.id, mode=mode))

        await interaction.response.send_message(f"✅ Ticket létrehozva: {channel.mention}", ephemeral=True)


# =========================
# /testresult (embed + website update)
# =========================
MODE_CHOICES = [app_commands.Choice(name=m, value=m) for m in MODE_LIST]
TIER_CHOICES = [app_commands.Choice(name=t, value=t) for t in TIER_LIST]


async def post_to_website(payload: dict) -> Tuple[bool, str]:
    """
    POST to: {WEBSITE_BASE_URL}/api/tests
    Authorization: Bearer BOT_API_KEY
    """
    if not BOT_API_KEY:
        return False, "BOT_API_KEY nincs beállítva a botnál."

    url = f"{WEBSITE_BASE_URL}/api/tests"
    headers = {"Authorization": f"Bearer {BOT_API_KEY}", "Content-Type": "application/json"}

    try:
        assert http_session is not None
        async with http_session.post(url, json=payload, headers=headers, timeout=15) as resp:
            text = await resp.text()
            if resp.status >= 200 and resp.status < 300:
                return True, text
            return False, f"status {resp.status} | {text}"
    except Exception as e:
        return False, str(e)


@tree.command(name="testresult", description="Minecraft tier teszt eredmény (mentés + weboldal frissítés).")
@app_commands.describe(
    mc_name="Minecraft név (ebből lesz skin a weboldalon)",
    tester="Ki tesztelte (Discord)",
    gamemode="Játékmód",
    tier="Elért tier",
)
@app_commands.choices(gamemode=MODE_CHOICES, tier=TIER_CHOICES)
async def testresult(
    interaction: discord.Interaction,
    mc_name: str,
    tester: discord.Member,
    gamemode: app_commands.Choice[str],
    tier: app_commands.Choice[str],
):
    if not interaction.guild:
        await interaction.response.send_message("❌ Csak szerveren használható.", ephemeral=True)
        return

    # Permission check
    if not is_allowed_for_admin(interaction):
        await interaction.response.send_message("❌ Nincs jogosultságod ehhez.", ephemeral=True)
        return

    player = sanitize_mc_name(mc_name)
    mode = gamemode.value
    new_tier = tier.value

    # Save latest result per mode (DB upsert)
    prev_tier = upsert_test(
        player=player,
        mode=mode,
        tier=new_tier,
        tester_id=tester.id,
        tester_name=str(tester),
    )

    total_points = get_total_points(player)
    delta = TIER_POINTS.get(new_tier, 0) - TIER_POINTS.get(prev_tier, 0)

    # Build the PUBLIC embed (the one you kept yelling for)
    skin_url = f"https://minotar.net/armor/bust/{player}/128.png"

    embed = discord.Embed(
        title=f"{player} teszt eredménye 🏆",
        color=discord.Color.dark_theme(),
    )
    embed.set_thumbnail(url=skin_url)

    embed.add_field(name="Tesztelő:", value=tester.mention, inline=False)
    embed.add_field(name="Játékmód:", value=mode, inline=False)
    embed.add_field(name="Minecraft név:", value=player, inline=False)
    embed.add_field(name="Előző rang:", value=prev_tier, inline=False)
    embed.add_field(name="Elért rang:", value=new_tier, inline=False)

    # Send PUBLIC message (everyone sees)
    await interaction.response.send_message(embed=embed)

    # Also send an ephemeral status message (optional, but useful)
    # We do it as followup because initial response is already used for the embed.
    payload = {
        "player": player,
        "mode": mode,
        "tier": new_tier,
        "previous_tier": prev_tier,
        "tester_id": tester.id,
        "tester_name": str(tester),
        "points_total": total_points,
        "points_delta": delta,
        "updated_at": int(time.time()),
    }

    ok, msg = await post_to_website(payload)
    if ok:
        await interaction.followup.send(
            f"✅ Mentve + weboldal frissítve.\nElőző: **{prev_tier}** → Elért: **{new_tier}** | "
            f"{'+' if delta >= 0 else ''}{delta} pont",
            ephemeral=True,
        )
    else:
        await interaction.followup.send(f"⚠️ Mentés hiba a weboldal felé ({msg})", ephemeral=True)


# =========================
# /ticketpanel
# =========================
@tree.command(name="ticketpanel", description="Teszt ticket panel kirakása.")
async def ticketpanel(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("❌ Csak szerveren használható.", ephemeral=True)
        return

    if not is_allowed_for_admin(interaction):
        await interaction.response.send_message("❌ Nincs jogosultságod ehhez.", ephemeral=True)
        return

    embed = discord.Embed(
        title="Teszt kérés",
        description="Kattints egy alábbi gombra, hogy tudd tesztelni a gombon feltüntetett játékmódból.",
        color=discord.Color.blurple(),
    )
    await interaction.response.send_message(embed=embed, view=TicketPanelView())


# =========================
# STARTUP
# =========================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id={bot.user.id})")

    # Sync commands only to your guild for instant updates (fast)
    if GUILD_ID:
        guild = discord.Object(id=GUILD_ID)
        try:
            await tree.sync(guild=guild)
            print(f"Slash commands synced to guild {GUILD_ID}")
        except Exception as e:
            print("Command sync error:", e)

    # Keep views persistent (so buttons keep working after restart)
    bot.add_view(TicketPanelView())
    bot.add_view(CloseTicketView(opener_id=0, mode="Sword"))  # dummy; discord only needs the class registered


async def main():
    global http_session
    init_db()

    http_session = ClientSession()

    # Start web server to keep container alive (Railway)
    await start_web_server()

    try:
        await bot.start(DISCORD_TOKEN)
    finally:
        if http_session:
            await http_session.close()


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN env missing!")
    asyncio.run(main())
