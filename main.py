import discord
from discord import app_commands
from discord.ui import View, Button
import os
import aiohttp

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN env var missing!")

# =========================
# CONFIG
# =========================
GUILD_ID = 1469740655520780631
STAFF_ROLE_ID = 1469755118634270864
TICKET_CATEGORY_ID = 1469766438238687496

API_URL = "https://neontiers.vercel.app/api/tests"
BOT_API_KEY = TOKEN  # csak a bot token

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
    "SpearElytra": 1469968762575912970,
    "SpearMace": 1469968704203788425,
}

# Rank -> Hungarian label + short code + points
RANKS = {
    "Unranked": ("Unranked", "Unranked", 0),
    "LT5": ("Alacsony Tier 5", "LT5", 1),
    "HT5": ("Magas Tier 5", "HT5", 2),
    "LT4": ("Alacsony Tier 4", "LT4", 3),
    "HT4": ("Magas Tier 4", "HT4", 4),
    "LT3": ("Alacsony Tier 3", "LT3", 5),
    "HT3": ("Magas Tier 3", "HT3", 6),
    "LT2": ("Alacsony Tier 2", "LT2", 7),
    "HT2": ("Magas Tier 2", "HT2", 8),
    "LT1": ("Alacsony Tier 1", "LT1", 9),
    "HT1": ("Magas Tier 1", "HT1", 10),
}

# =========================
# DISCORD
# =========================
intents = discord.Intents.default()
intents.guilds = True
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

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

# =========================
# UI: CLOSE
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
            await interaction.channel.delete(delay=3)
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
        for name in PING_ROLES.keys():
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

        ping_role_id = PING_ROLES.get(self.mode)
        ping_role = guild.get_role(ping_role_id) if ping_role_id else None

        if ping_role:
            await channel.send(f"{ping_role.mention} | Új teszt kérés!")
        else:
            await channel.send("⚠️ Ping role nem található ehhez a módhoz.")

        await channel.send(embed=ticket_embed(self.mode, interaction.user), view=CloseTicketView())
        await interaction.followup.send(f"✅ Ticket létrehozva: {channel.mention}", ephemeral=True)

# =========================
# COMMAND: ticketpanel
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
# COMMAND: testresult (POST → web + embed)
# =========================
@tree.command(name="testresult", description="Teszt eredmény mentése + weboldal frissítés", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    username="Minecraft név (skin ehhez)",
    gamemode="Játékmód (pl. Mace)",
    rank="Elért rang (pl. LT3)"
)
async def testresult(interaction: discord.Interaction, username: str, gamemode: str, rank: str):
    await interaction.response.defer(ephemeral=True)

    gm = gamemode.strip()
    rk = rank.strip()

    # fallback
    prev_short = "Unranked"
    prev_hu = "Unranked"

    # Előző rang lekérése az API-ból (ha van)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(API_URL) as r:
                data = await r.json()
                for t in data.get("tests", []):
                    if t.get("username") == username and t.get("gamemode") == gm:
                        prev_short = t.get("rank", "Unranked")
                        break
    except Exception:
        pass

    prev_hu = RANKS.get(prev_short, ("Unranked", prev_short, 0))[0]
    new_hu, new_short, new_pts = RANKS.get(rk, (rk, rk, 0))

    # POST (upsert a weboldalon kezeli a duplikációt)
    payload = {
        "username": username,
        "gamemode": gm,
        "rank": new_short,
        "tester": interaction.user.name
    }

    ok = False
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                API_URL,
                json=payload,
                headers={"Authorization": f"Bearer {BOT_API_KEY}"}
            ) as resp:
                ok = (resp.status == 200)
                if not ok:
                    text = await resp.text()
                    await interaction.followup.send(f"❌ Web API hiba: {resp.status}\n{text}", ephemeral=True)
                    return
    except Exception as e:
        await interaction.followup.send(f"❌ Hálózati/API hiba: {e}", ephemeral=True)
        return

    # ✅ Publikus embed (ez hiányzott “rendesen”)
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

    # ✅ ez a “zöld pipás” szöveg most már az embedben is megjelenik normálisan
    embed.add_field(
        name="Összegzés",
        value=f"✅ Mentve + weboldal frissítve.\nElőző: **{prev_short}** → Elért: **{new_short}** | **+{new_pts} pont**",
        inline=False
    )

    try:
        await interaction.channel.send(embed=embed)
    except Exception:
        pass

    await interaction.followup.send(
        f"✅ Mentve + weboldal frissítve.\nElőző: **{prev_short}** → Elért: **{new_short}** | **+{new_pts} pont**",
        ephemeral=True
    )

# =========================
@client.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"Logged in as {client.user}")

client.run(TOKEN)
