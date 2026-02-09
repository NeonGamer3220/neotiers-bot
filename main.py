import discord
from discord import app_commands
from discord.ui import View, Button
import os
import aiohttp
import asyncio
import json
from pathlib import Path

# =========================
# ENV
# =========================
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN env var missing!")

# =========================
# CONFIG (EDIT THESE)
# =========================
GUILD_ID = 1469740655520780631
STAFF_ROLE_ID = 1469755118634270864
TICKET_CATEGORY_ID = 1469766438238687496

# Website API (Vercel)
API_URL = "https://neontiers.vercel.app/api/tests"
BOT_API_KEY = TOKEN  # igen, csak a bot token

# Ping roles per gamemode
PING_ROLES = {
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

MODE_LIST = list(PING_ROLES.keys())

# Rank options (short format)
RANKS = ["Unranked", "LT5", "HT5", "LT4", "HT4", "LT3", "HT3", "LT2", "HT2", "LT1", "HT1"]

# Points mapping (tweakable)
RANK_POINTS = {
    "Unranked": 0,
    "LT5": 1, "HT5": 2,
    "LT4": 3, "HT4": 4,
    "LT3": 5, "HT3": 6,
    "LT2": 7, "HT2": 8,
    "LT1": 9, "HT1": 10,
}

# Local storage for previous ranks
DATA_FILE = Path("player_ranks.json")

# =========================
# DISCORD SETUP
# =========================
intents = discord.Intents.default()
intents.guilds = True
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# =========================
# STORAGE
# =========================
def load_data() -> dict:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_data(data: dict):
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def key_for(player: str, mode: str) -> str:
    return f"{player.lower()}::{mode}"

def get_previous_rank(player: str, mode: str) -> str:
    data = load_data()
    return data.get(key_for(player, mode), "Unranked")

def set_previous_rank(player: str, mode: str, rank: str):
    data = load_data()
    data[key_for(player, mode)] = rank
    save_data(data)

# =========================
# HELPERS
# =========================
def has_staff_role(member: discord.Member) -> bool:
    return any(r.id == STAFF_ROLE_ID for r in member.roles)

def skin_url(username: str) -> str:
    return f"https://minotar.net/helm/{username}/128.png"

def make_panel_embed() -> discord.Embed:
    return discord.Embed(
        title="Teszt kérés",
        description="Kattints egy gombra, hogy ticketet nyiss az adott játékmódhoz.",
        color=0x7b5cff
    )

def make_ticket_embed(mode: str, user: discord.Member) -> discord.Embed:
    return discord.Embed(
        title="Teszt ticket",
        description=f"Játékmód: **{mode}**\nKérte: {user.mention}",
        color=0x2b2d31
    )

def make_test_embed(tester: discord.Member, tested_player: str, username: str, mode: str, prev_rank: str, earned_rank: str) -> discord.Embed:
    e = discord.Embed(
        title=f"{tested_player} teszt eredménye 🏆",
        color=0x2b2d31
    )
    e.add_field(name="Tesztelő:", value=f"{tester.mention}", inline=False)
    e.add_field(name="Játékmód:", value=mode, inline=False)
    e.add_field(name="Minecraft név:", value=tested_player, inline=False)
    e.add_field(name="Előző rang:", value=prev_rank, inline=False)
    e.add_field(name="Elért rang:", value=earned_rank, inline=False)
    e.set_thumbnail(url=skin_url(username))
    return e

# =========================
# UI: CLOSE TICKET
# =========================
class CloseTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CloseTicketButton())

class CloseTicketButton(Button):
    def __init__(self):
        super().__init__(label="Ticket bezárása", style=discord.ButtonStyle.danger, emoji="🗑️")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send("🗑 Ticket törlődik 3 mp múlva...", ephemeral=True)
        try:
            await asyncio.sleep(3)
            await interaction.channel.delete()
        except discord.Forbidden:
            await interaction.followup.send("❌ Nincs jogom törölni a csatornát.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Hiba: {e}", ephemeral=True)

# =========================
# UI: TICKET PANEL
# =========================
class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
        for name in MODE_LIST:
            self.add_item(TicketButton(name))

class TicketButton(Button):
    def __init__(self, mode: str):
        super().__init__(label=mode, style=discord.ButtonStyle.primary)
        self.mode = mode

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("❌ Guild not found.", ephemeral=True)
            return

        category = guild.get_channel(TICKET_CATEGORY_ID)
        if category is None or not isinstance(category, discord.CategoryChannel):
            await interaction.followup.send("❌ Ticket kategória ID rossz vagy nem kategória.", ephemeral=True)
            return

        # Block SAME gamemode ticket, allow different modes
        topic_value = f"{interaction.user.id}:{self.mode}"
        for ch in category.text_channels:
            if ch.topic == topic_value:
                await interaction.followup.send("❌ Már van nyitott ticketed ebből a játékmódból.", ephemeral=True)
                return

        staff_role = guild.get_role(STAFF_ROLE_ID)
        if staff_role is None:
            await interaction.followup.send("❌ STAFF_ROLE_ID rossz (nincs ilyen rang).", ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            staff_role: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }

        try:
            channel = await guild.create_text_channel(
                name=f"{self.mode.lower()}-{interaction.user.name}".replace(" ", "-"),
                category=category,
                overwrites=overwrites,
                topic=topic_value
            )
        except discord.Forbidden:
            await interaction.followup.send("❌ Nincs jogom csatornát létrehozni (Manage Channels kell).", ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(f"❌ Hiba csatorna létrehozásnál: {e}", ephemeral=True)
            return

        # Ping correct gamemode role
        ping_role_id = PING_ROLES.get(self.mode)
        ping_role = guild.get_role(ping_role_id) if ping_role_id else None
        if ping_role:
            await channel.send(f"{ping_role.mention} | Új teszt kérés!")
        else:
            await channel.send("⚠️ Ping role nem található ehhez a módhoz.")

        await channel.send(embed=make_ticket_embed(self.mode, interaction.user), view=CloseTicketView())
        await interaction.followup.send(f"✅ Ticket létrehozva: {channel.mention}", ephemeral=True)

# =========================
# SLASH: ticketpanel
# =========================
@tree.command(name="ticketpanel", description="Teszt kérő panel küldése", guild=discord.Object(id=GUILD_ID))
async def ticketpanel(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    if not isinstance(interaction.user, discord.Member):
        await interaction.followup.send("❌ Member not found.", ephemeral=True)
        return

    if not has_staff_role(interaction.user):
        await interaction.followup.send("❌ Nincs jogod (STAFF_ROLE_ID kell).", ephemeral=True)
        return

    try:
        await interaction.channel.send(embed=make_panel_embed(), view=TicketView())
    except discord.Forbidden:
        await interaction.followup.send("❌ Nincs jogom ide írni.", ephemeral=True)
        return

    await interaction.followup.send("✅ Panel elküldve.", ephemeral=True)

# =========================
# SLASH: testresult (CHOICES + required tester + required username)
# =========================
MODE_CHOICES = [app_commands.Choice(name=m, value=m) for m in MODE_LIST]
RANK_CHOICES = [app_commands.Choice(name=r, value=r) for r in RANKS]

@tree.command(
    name="testresult",
    description="Teszt eredmény (előző rang automatikus + weboldal pontok)",
    guild=discord.Object(id=GUILD_ID)
)
@app_commands.describe(
    tested_player="Minecraft játékos neve (nem Discord tag!)",
    tester="Tesztelő (Discord tag)",
    username="Minecraft skin név",
    gamemode="Játékmód",
    rank_earned="Elért rang"
)
@app_commands.choices(gamemode=MODE_CHOICES, rank_earned=RANK_CHOICES)
async def testresult(
    interaction: discord.Interaction,
    tested_player: str,
    tester: discord.Member,
    username: str,
    gamemode: app_commands.Choice[str],
    rank_earned: app_commands.Choice[str],
):
    await interaction.response.defer(ephemeral=True)

    # permission: staff only
    if not isinstance(interaction.user, discord.Member) or not has_staff_role(interaction.user):
        await interaction.followup.send("❌ Nincs jogod a parancshoz (STAFF_ROLE_ID kell).", ephemeral=True)
        return

    mode = gamemode.value
    earned = rank_earned.value
    prev = get_previous_rank(tested_player, mode)
    pts = RANK_POINTS.get(earned, 0)

    # Send embed public to channel
    try:
        embed = make_test_embed(tester, tested_player, username, mode, prev, earned)
        await interaction.channel.send(embed=embed)
    except Exception:
        pass

    # Save previous rank
    set_previous_rank(tested_player, mode, earned)

    # IMPORTANT: send compatible payload keys (so your route can't complain)
    payload = {
        # likely required by your API:
        "tested_player": tested_player,
        "tester": str(tester.id),
        "tester_id": str(tester.id),
        "tester_name": str(tester),
        "username": username,
        "gamemode": mode,
        "previous_rank": prev,
        "rank_earned": earned,
        "points": pts,

        # compatibility aliases (in case the route expects different names):
        "player": tested_player,
        "skin": username,
        "mode": mode,
        "previousRank": prev,
        "rankEarned": earned,
        "rank": earned,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                API_URL,
                json=payload,
                headers={"Authorization": f"Bearer {BOT_API_KEY}"}
            ) as resp:
                text = await resp.text()
                if resp.status == 200:
                    await interaction.followup.send(
                        f"✅ Mentve + weboldal frissítve.\nElőző: `{prev}` → Elért: `{earned}` | +`{pts}` pont",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        f"⚠️ Embed elküldve, DE web API hiba: {resp.status}\n{text}",
                        ephemeral=True
                    )
    except Exception as e:
        await interaction.followup.send(f"⚠️ Embed elküldve, DE web API hálózati hiba: {e}", ephemeral=True)

# =========================
# READY
# =========================
@client.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"Logged in as {client.user}")

client.run(TOKEN)
