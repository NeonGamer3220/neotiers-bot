import os
import re
import time
import asyncio
import sqlite3
from typing import Optional, Dict, List, Tuple

import discord
from discord import app_commands
from discord.ext import commands

# =========================
# ENV / CONFIG
# =========================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()

GUILD_ID = int(os.getenv("GUILD_ID", "1469740655520780631"))
STAFF_ROLE_ID = int(os.getenv("STAFF_ROLE_ID", "1469755118634270864"))
TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID", "1469766438238687496"))

WEBSITE_BASE_URL = os.getenv("WEBSITE_BASE_URL", "https://neontiers.vercel.app").rstrip("/")
BOT_API_KEY = os.getenv("BOT_API_KEY", "").strip()

DB_PATH = os.getenv("DB_PATH", "neotiers.db")

# =========================
# GAMEMODES + PING ROLES (ticket ping)
# =========================
MODE_PING_ROLE_IDS: Dict[str, int] = {
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
    "SpearElytra": 1469764028195668199,
    "SpearMace": 1469763993857163359,
    "Cart": 1469763920871952435,
    "DiaSMP": 1469763946968911893,
    "Creeper": 1469764200812249180,

    # NEW extra pings you asked
    "SpearMace2": 1469968704203788425,     # extra ping role
    "SpearElytra2": 1469968762575912970,   # extra ping role
}

# Ticket panel modes (buttons)
TICKET_MODES: List[str] = [
    "Vanilla", "UHC", "Pot", "NethPot", "SMP",
    "Sword", "Axe", "Mace", "Cart", "Creeper",
    "DiaSMP", "OGVanilla", "ShieldlessUHC",
    "SpearMace", "SpearElytra",
]

# which mode pings which role when a ticket opens
TICKET_MODE_TO_PING_ROLE: Dict[str, List[int]] = {
    "Mace": [1469763612452196375],
    "Sword": [1469763677141074125],
    "Axe": [1469763738889486518],
    "Pot": [1469763780593324032],
    "NethPot": [1469763817218117697],
    "SMP": [1469764274955223161],
    "UHC": [1469765994988704030],
    "Vanilla": [1469763891226480926],
    "OGVanilla": [1469764329460203571],
    "ShieldlessUHC": [1469766017243807865],
    "SpearElytra": [1469968762575912970],  # NEW
    "SpearMace": [1469968704203788425],    # NEW
    "Cart": [1469763920871952435],
    "DiaSMP": [1469763946968911893],
    "Creeper": [1469764200812249180],
}

# =========================
# /testresult ranks (SHORT, not "Alacsony Tier 3")
# =========================
RANKS: List[str] = [
    "Unranked",
    "LT5", "HT5",
    "LT4", "HT4",
    "LT3", "HT3",
    "LT2", "HT2",
    "LT1", "HT1",
]

# Optional: points mapping (if you want website to calculate, you can ignore this)
RANK_POINTS: Dict[str, int] = {
    "Unranked": 0,
    "LT5": 1, "HT5": 2,
    "LT4": 3, "HT4": 4,
    "LT3": 5, "HT3": 6,
    "LT2": 7, "HT2": 8,
    "LT1": 9, "HT1": 10,
}

# =========================
# Permissions
# =========================
ALLOWED_TESTER_ROLE_IDS = set(MODE_PING_ROLE_IDS.values()) | {STAFF_ROLE_ID}


def is_admin_or_allowed_tester(interaction: discord.Interaction) -> bool:
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return False
    member: discord.Member = interaction.user
    if member.guild_permissions.administrator:
        return True
    member_role_ids = {r.id for r in member.roles}
    return len(member_role_ids.intersection(ALLOWED_TESTER_ROLE_IDS)) > 0


# =========================
# SQLite (cooldowns + open tickets)
# =========================
def db_init():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ticket_open (
            user_id INTEGER NOT NULL,
            mode TEXT NOT NULL,
            channel_id INTEGER NOT NULL,
            PRIMARY KEY (user_id, mode)
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ticket_cooldown (
            user_id INTEGER NOT NULL,
            mode TEXT NOT NULL,
            last_closed_ts INTEGER NOT NULL,
            PRIMARY KEY (user_id, mode)
        );
    """)
    conn.commit()
    conn.close()


def db_get_open_ticket_channel(user_id: int, mode: str) -> Optional[int]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT channel_id FROM ticket_open WHERE user_id=? AND mode=?;", (user_id, mode))
    row = cur.fetchone()
    conn.close()
    return int(row[0]) if row else None


def db_set_open_ticket(user_id: int, mode: str, channel_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO ticket_open(user_id, mode, channel_id) VALUES(?,?,?);",
                (user_id, mode, channel_id))
    conn.commit()
    conn.close()


def db_remove_open_ticket(user_id: int, mode: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM ticket_open WHERE user_id=? AND mode=?;", (user_id, mode))
    conn.commit()
    conn.close()


def db_get_last_closed(user_id: int, mode: str) -> Optional[int]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT last_closed_ts FROM ticket_cooldown WHERE user_id=? AND mode=?;", (user_id, mode))
    row = cur.fetchone()
    conn.close()
    return int(row[0]) if row else None


def db_set_last_closed(user_id: int, mode: str, ts: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO ticket_cooldown(user_id, mode, last_closed_ts) VALUES(?,?,?);",
                (user_id, mode, ts))
    conn.commit()
    conn.close()


COOLDOWN_SECONDS = 14 * 24 * 60 * 60  # 14 days


# =========================
# Discord Bot
# =========================
intents = discord.Intents.default()
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


# =========================
# Ticket UI
# =========================
class CloseTicketView(discord.ui.View):
    def __init__(self, owner_id: int, mode: str):
        super().__init__(timeout=None)
        self.owner_id = owner_id
        self.mode = mode

    @discord.ui.button(label="Ticket lezárása", style=discord.ButtonStyle.danger, custom_id="neotiers_close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Staff or owner can close
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        member: discord.Member = interaction.user
        is_staff = member.guild_permissions.administrator or any(r.id == STAFF_ROLE_ID for r in member.roles)
        is_owner = interaction.user.id == self.owner_id

        if not (is_staff or is_owner):
            await interaction.response.send_message("❌ Nincs jogosultságod lezárni ezt a ticketet.", ephemeral=True)
            return

        await interaction.response.send_message("✅ Ticket lezárása... 3 mp múlva törlöm a csatornát.", ephemeral=True)

        # cooldown starts now
        db_set_last_closed(self.owner_id, self.mode, int(time.time()))
        db_remove_open_ticket(self.owner_id, self.mode)

        channel = interaction.channel
        await asyncio.sleep(3)

        try:
            if isinstance(channel, discord.TextChannel):
                await channel.delete(reason="NeoTiers ticket closed")
        except discord.Forbidden:
            # If missing permission, tell staff
            try:
                await interaction.followup.send("❌ Nem tudtam törölni a csatornát (Missing Permissions). Add a botnak: Manage Channels.", ephemeral=True)
            except:
                pass
        except Exception:
            pass


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for mode in TICKET_MODES:
            self.add_item(TicketButton(mode))


class TicketButton(discord.ui.Button):
    def __init__(self, mode: str):
        super().__init__(label=mode, style=discord.ButtonStyle.primary, custom_id=f"neotiers_ticket_{mode}")
        self.mode = mode

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        guild = interaction.guild
        member: discord.Member = interaction.user

        # 1) Don't allow duplicate SAME mode ticket
        open_ch = db_get_open_ticket_channel(member.id, self.mode)
        if open_ch:
            await interaction.response.send_message("❌ Van már ticketed ebből a játékmódból.", ephemeral=True)
            return

        # 2) 14 day cooldown PER MODE
        last_closed = db_get_last_closed(member.id, self.mode)
        if last_closed:
            remaining = (last_closed + COOLDOWN_SECONDS) - int(time.time())
            if remaining > 0:
                days = remaining // (24 * 60 * 60)
                hours = (remaining % (24 * 60 * 60)) // 3600
                await interaction.response.send_message(
                    f"⏳ Ebből a módból még cooldown van: **{days} nap {hours} óra**.",
                    ephemeral=True
                )
                return

        # category
        category = guild.get_channel(TICKET_CATEGORY_ID)
        if not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message("❌ Ticket kategória nincs beállítva / rossz ID.", ephemeral=True)
            return

        # channel name
        safe_name = re.sub(r"[^a-z0-9\-]", "", member.name.lower().replace(" ", "-"))
        channel_name = f"{self.mode.lower()}-{safe_name}-{member.id}".lower()[:95]

        # permissions
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }

        staff_role = guild.get_role(STAFF_ROLE_ID)
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True)

        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                reason="NeoTiers ticket created"
            )
        except discord.Forbidden:
            await interaction.response.send_message("❌ A botnak nincs joga csatornát létrehozni (Manage Channels).", ephemeral=True)
            return

        db_set_open_ticket(member.id, self.mode, channel.id)

        # ping role(s) for this mode
        ping_ids = TICKET_MODE_TO_PING_ROLE.get(self.mode, [])
        pings = []
        for rid in ping_ids:
            role = guild.get_role(rid)
            if role:
                pings.append(role.mention)

        ping_text = " ".join(pings) if pings else (staff_role.mention if staff_role else "")

        embed = discord.Embed(
            title="Teszt kérés",
            description="Kattints a **Ticket lezárása** gombra, ha kész vagytok.\n"
                        "A tesztet a kiválasztott játékmódból végezzétek.",
            color=discord.Color.blurple()
        )
        embed.add_field(name="Játékmód", value=self.mode, inline=True)
        embed.add_field(name="Kérte", value=member.mention, inline=True)

        await channel.send(content=ping_text, embed=embed, view=CloseTicketView(owner_id=member.id, mode=self.mode))

        await interaction.response.send_message(f"✅ Ticket megnyitva: {channel.mention}", ephemeral=True)


# =========================
# Website API call
# =========================
async def post_test_to_website(payload: dict) -> Tuple[bool, int, dict]:
    """
    POST to WEBSITE_BASE_URL/api/tests with Authorization Bearer BOT_API_KEY
    Returns (ok, status, json_or_error)
    """
    if not WEBSITE_BASE_URL:
        return False, 0, {"error": "Missing WEBSITE_BASE_URL"}
    if not BOT_API_KEY:
        return False, 0, {"error": "Missing BOT_API_KEY (set it on bot + Vercel too)"}

    url = f"{WEBSITE_BASE_URL}/api/tests"

    headers = {
        "Authorization": f"Bearer {BOT_API_KEY}",
        "Content-Type": "application/json"
    }

    # discord.py already depends on aiohttp, so it's available
    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=10) as resp:
                status = resp.status
                try:
                    data = await resp.json()
                except Exception:
                    text = await resp.text()
                    data = {"raw": text}
                return (200 <= status < 300), status, data
    except Exception as e:
        return False, 0, {"error": str(e)}


# =========================
# Slash Commands
# =========================
class ModeChoice(app_commands.Choice[str]):
    pass


def mode_choices() -> List[app_commands.Choice[str]]:
    return [app_commands.Choice(name=m, value=m) for m in TICKET_MODES]


def rank_choices() -> List[app_commands.Choice[str]]:
    return [app_commands.Choice(name=r, value=r) for r in RANKS]


@bot.tree.command(name="ticketpanel", description="Ticket panel kiküldése (Teszt kérés gombokkal).")
@app_commands.checks.has_permissions(administrator=True)
async def ticketpanel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Teszt kérés",
        description="Kattints egy alábbi gombra, hogy tudj tesztelni a gombon feltüntetett játékmódból.",
        color=discord.Color.blurple()
    )
    await interaction.response.send_message(embed=embed, view=TicketPanelView())


@bot.tree.command(name="testresult", description="Teszt eredmény kiküldése + weboldal frissítése.")
@app_commands.describe(
    mc_name="Minecraft név (ebből lesz a skin a weboldalon)",
    tester="Ki tesztelt (Discord @)",
    gamemode="Játékmód",
    rank="Elért rank (pl. LT3, HT4, ...)"
)
@app_commands.choices(gamemode=mode_choices(), rank=rank_choices())
async def testresult(
    interaction: discord.Interaction,
    mc_name: str,
    tester: discord.Member,
    gamemode: app_commands.Choice[str],
    rank: app_commands.Choice[str],
):
    # permission
    if not is_admin_or_allowed_tester(interaction):
        await interaction.response.send_message("❌ Nincs jogosultságod ehhez a parancshoz.", ephemeral=True)
        return

    # sanitize mc name
    mc_name = mc_name.strip()
    if not re.fullmatch(r"[A-Za-z0-9_]{3,16}", mc_name):
        await interaction.response.send_message("❌ Hibás Minecraft név. (3-16, csak betű/szám/_) ", ephemeral=True)
        return

    mode = gamemode.value
    earned = rank.value

    # Public embed (EVERYONE sees this)  ✅ this is the one you want
    skin_url = f"https://minotar.net/armor/bust/{mc_name}/100.png"

    embed = discord.Embed(
        title=f"{mc_name} teszt eredménye 🏆",
        color=discord.Color.dark_embed()
    )
    embed.set_thumbnail(url=skin_url)
    embed.add_field(name="Tesztelő:", value=tester.mention, inline=False)
    embed.add_field(name="Játékmód:", value=mode, inline=False)
    embed.add_field(name="Minecraft név:", value=mc_name, inline=False)
    embed.add_field(name="Elért rang:", value=earned, inline=False)

    # send public message first
    await interaction.channel.send(embed=embed)

    # Save to website (this will overwrite latest per (mc_name, mode) on website side)
    payload = {
        "mc_name": mc_name,
        "tester_id": str(tester.id),
        "tester_tag": str(tester),
        "mode": mode,
        "rank": earned,
        "timestamp": int(time.time()),
    }

    ok, status, data = await post_test_to_website(payload)

    if ok:
        pts = RANK_POINTS.get(earned, 0)
        await interaction.response.send_message(
            f"✅ Mentve + weboldal frissítve.\nElért: **{earned}** | +**{pts} pont**",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            f"⚠️ Mentés hiba a weboldal felé (status {status})\n`{data}`",
            ephemeral=True
        )


# =========================
# Startup / Sync
# =========================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id={bot.user.id})")
    try:
        guild = discord.Object(id=GUILD_ID)
        await bot.tree.sync(guild=guild)
        print(f"Slash commands synced to guild {GUILD_ID}")
    except Exception as e:
        print("Sync failed:", e)


async def setup_persistent_views():
    # Keep views persistent after restart (for button custom_id)
    bot.add_view(TicketPanelView())
    bot.add_view(CloseTicketView(owner_id=0, mode=""))  # dummy, custom_id kept


async def main():
    db_init()
    await setup_persistent_views()
    await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise SystemExit("Missing DISCORD_TOKEN env var")
    asyncio.run(main())
