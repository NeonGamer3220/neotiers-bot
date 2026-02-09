
import os
import discord
from discord import app_commands
from discord.ui import View, Button
import aiohttp

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

# Website API
API_URL = "https://neontiers.vercel.app/api/tests"
BOT_API_KEY = TOKEN  # IGEN: csak a bot token

# Ping roles per gamemode (ticket ping!)
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
    "DiaSMP": 1469763946968911893,
    "Cart": 1469763920871952435,
    "Creeper": 1469764200812249180,
    "SpearMace": 1469968704203788425,
    "SpearElytra": 1469968762575912970,
}

# Rank (value = short code that goes to API) -> (HU label, points)
RANKS = {
    "Unranked": ("Unranked", 0),
    "LT5": ("Alacsony Tier 5", 1),
    "HT5": ("Magas Tier 5", 2),
    "LT4": ("Alacsony Tier 4", 3),
    "HT4": ("Magas Tier 4", 4),
    "LT3": ("Alacsony Tier 3", 5),
    "HT3": ("Magas Tier 3", 6),
    "LT2": ("Alacsony Tier 2", 7),
    "HT2": ("Magas Tier 2", 8),
    "LT1": ("Alacsony Tier 1", 9),
    "HT1": ("Magas Tier 1", 10),
}

GAMEMODES = list(PING_ROLES.keys())

# =========================
# DISCORD SETUP
# =========================
intents = discord.Intents.default()
intents.guilds = True
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# =========================
# HELPERS
# =========================
def has_staff_role(member: discord.Member) -> bool:
    return any(r.id == STAFF_ROLE_ID for r in member.roles)

def panel_embed() -> discord.Embed:
    return discord.Embed(
        title="Teszt kérés",
        description="Kattints egy gombra, hogy ticketet nyiss az adott játékmódhoz.",
        color=0x7b5cff
    )

def ticket_embed(mode: str, user: discord.Member) -> discord.Embed:
    return discord.Embed(
        title="Teszt ticket",
        description=f"Játékmód: **{mode}**\nKérte: {user.mention}",
        color=0x2b2d31
    )

async def fetch_previous_rank(username: str, gamemode: str) -> str:
    """Get previous rank for (username,gamemode) from API GET /api/tests."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(API_URL) as resp:
                if resp.status != 200:
                    return "Unranked"
                data = await resp.json()
                # expected: { tests: [...] }
                for t in data.get("tests", []):
                    if str(t.get("username", "")).strip().lower() == username.strip().lower() and str(t.get("gamemode", "")).strip() == gamemode:
                        return str(t.get("rank", "Unranked")).strip() or "Unranked"
    except Exception:
        pass
    return "Unranked"

def rank_hu(rank_code: str) -> str:
    return RANKS.get(rank_code, (rank_code, 0))[0]

def rank_points(rank_code: str) -> int:
    return RANKS.get(rank_code, (rank_code, 0))[1]

# =========================
# UI: CLOSE TICKET (persistent)
# =========================
class CloseTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CloseTicketButton())

class CloseTicketButton(Button):
    def __init__(self):
        super().__init__(
            label="Ticket bezárása",
            style=discord.ButtonStyle.danger,
            emoji="🗑️",
            custom_id="ticket_close"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send("🗑 Ticket törlődik 3 mp múlva...", ephemeral=True)
        try:
            await interaction.channel.delete(delay=3)
        except discord.Forbidden:
            await interaction.followup.send("❌ Nincs jogom törölni a csatornát.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Hiba: {e}", ephemeral=True)

# =========================
# UI: TICKET PANEL (persistent)
# =========================
class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
        for mode in GAMEMODES:
            self.add_item(TicketButton(mode))

class TicketButton(Button):
    def __init__(self, mode: str):
        super().__init__(
            label=mode,
            style=discord.ButtonStyle.primary,
            custom_id=f"ticket_mode_{mode}"
        )
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

        # Same-gamemode duplicate block, different gamemode allowed
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

        # Ping GAMEMODE role (not tester)
        ping_role_id = PING_ROLES.get(self.mode)
        ping_role = guild.get_role(ping_role_id) if ping_role_id else None

        try:
            if ping_role:
                await channel.send(f"{ping_role.mention} | Új teszt kérés!")
            else:
                await channel.send("⚠️ Ping role nem található ehhez a módhoz.")
        except Exception:
            pass

        await channel.send(embed=ticket_embed(self.mode, interaction.user), view=CloseTicketView())
        await interaction.followup.send(f"✅ Ticket létrehozva: {channel.mention}", ephemeral=True)

# =========================
# SLASH: /ticketpanel
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
        await interaction.channel.send(embed=panel_embed(), view=TicketView())
    except discord.Forbidden:
        await interaction.followup.send("❌ Nincs jogom ide írni.", ephemeral=True)
        return

    await interaction.followup.send("✅ Panel elküldve.", ephemeral=True)

# =========================
# /testresult (OLD STYLE but connected)
# username = mc name
# gamemode = CHOICE
# rank = CHOICE
# tester = implicit interaction.user
# previous rank = automatic from website
# =========================

# choices
GAMEMODE_CHOICES = [app_commands.Choice(name=m, value=m) for m in GAMEMODES]
RANK_CHOICES = [app_commands.Choice(name=f"{rank_hu(code)} ({code})", value=code) for code in RANKS.keys()]

@tree.command(
    name="testresult",
    description="Teszt eredmény mentése + weboldal frissítése (választható mód/rang)",
    guild=discord.Object(id=GUILD_ID)
)
@app_commands.describe(
    username="Minecraft név (skin ehhez)",
    gamemode="Játékmód",
    rank="Elért rang"
)
@app_commands.choices(gamemode=GAMEMODE_CHOICES, rank=RANK_CHOICES)
async def testresult(
    interaction: discord.Interaction,
    username: str,
    gamemode: app_commands.Choice[str],
    rank: app_commands.Choice[str],
):
    await interaction.response.defer(ephemeral=True)

    gm = gamemode.value
    new_rank_code = rank.value

    prev_rank_code = await fetch_previous_rank(username, gm)

    # POST to website (upsert should be handled server-side)
    payload = {
        "username": username.strip(),
        "gamemode": gm,
        "rank": new_rank_code,
        "tester": interaction.user.name
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                API_URL,
                json=payload,
                headers={"Authorization": f"Bearer {BOT_API_KEY}"}
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    await interaction.followup.send(f"❌ Web API hiba: {resp.status}\n{text}", ephemeral=True)
                    return
    except Exception as e:
        await interaction.followup.send(f"❌ Hálózati/API hiba: {e}", ephemeral=True)
        return

    prev_hu = rank_hu(prev_rank_code)
    new_hu = rank_hu(new_rank_code)
    pts = rank_points(new_rank_code)

    # Public embed (results message)
    skin_url = f"https://mc-heads.net/avatar/{username}/64"

    embed = discord.Embed(
        title=f"{username} teszt eredménye 🏆",
        color=0x2b2d31
    )
    embed.set_thumbnail(url=skin_url)
    embed.add_field(name="Tesztelő:", value=interaction.user.mention, inline=False)
    embed.add_field(name="Játékmód:", value=gm, inline=False)
    embed.add_field(name="Minecraft név:", value=username, inline=False)
    embed.add_field(name="Előző rang:", value=prev_hu, inline=False)
    embed.add_field(name="Elért rang:", value=new_hu, inline=False)

    # Summary also in embed (so it appears “rendesen”)
    embed.add_field(
        name="Összegzés",
        value=f"✅ Mentve + weboldal frissítve.\nElőző: **{prev_rank_code}** → Elért: **{new_rank_code}** | **+{pts} pont**",
        inline=False
    )

    try:
        await interaction.channel.send(embed=embed)
    except Exception:
        pass

    # Ephemeral status (the green one)
    await interaction.followup.send(
        f"✅ Mentve + weboldal frissítve.\nElőző: **{prev_rank_code}** → Elért: **{new_rank_code}** | **+{pts} pont**",
        ephemeral=True
    )

# =========================
# READY
# =========================
@client.event
async def on_ready():
    # persistent views
    client.add_view(TicketView())
    client.add_view(CloseTicketView())

    await tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"Logged in as {client.user}")

client.run(TOKEN)
