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
BOT_API_KEY = TOKEN  # csak a bot token

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

GAMEMODES = list(PING_ROLES.keys())

# Rank codes (AZT írjuk ki, NEM magyar szöveget)
RANK_CODES = [
    "Unranked",
    "LT5", "HT5",
    "LT4", "HT4",
    "LT3", "HT3",
    "LT2", "HT2",
    "LT1", "HT1",
]

# pontozás (ha kell a zöld “+ pont” üzenethez)
RANK_POINTS = {
    "Unranked": 0,
    "LT5": 1, "HT5": 2,
    "LT4": 3, "HT4": 4,
    "LT3": 5, "HT3": 6,
    "LT2": 7, "HT2": 8,
    "LT1": 9, "HT1": 10,
}

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

async def fetch_previous_rank(mc_name: str, gamemode: str) -> str:
    """
    Előző rang lekérése a weboldal API-ból.
    Végigmegy a tests listán és megkeresi (mc_name + gamemode) legutóbbi rankját.
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(API_URL) as resp:
                if resp.status != 200:
                    return "Unranked"
                data = await resp.json()
                tests = data.get("tests", [])

                # Ha a backend már "latest" jellegűt ad, akkor első találat elég.
                # Ha nem, akkor a listát fordítva is nézhetjük. (biztosabb)
                for t in reversed(tests):
                    if str(t.get("username", "")).strip().lower() == mc_name.strip().lower() and str(t.get("gamemode", "")).strip() == gamemode:
                        r = str(t.get("rank", "Unranked")).strip() or "Unranked"
                        return r if r in RANK_CODES else "Unranked"
    except Exception:
        pass
    return "Unranked"

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
# /testresult (AS YOU WANT)
# mc_name (skin)
# tester (user mention)
# gamemode (choice)
# tier (choice = LT3 etc)
# previous rank auto from API
# =========================
GAMEMODE_CHOICES = [app_commands.Choice(name=m, value=m) for m in GAMEMODES]
TIER_CHOICES = [app_commands.Choice(name=code, value=code) for code in RANK_CODES]

@tree.command(
    name="testresult",
    description="Teszt eredmény (mc_név + tesztelő + játékmód + tier) + weboldal mentés",
    guild=discord.Object(id=GUILD_ID)
)
@app_commands.describe(
    mc_name="Minecraft név (skin ehhez)",
    tester="Tesztelő (Discord)",
    gamemode="Játékmód",
    tier="Elért tier (pl. LT3, HT4...)"
)
@app_commands.choices(gamemode=GAMEMODE_CHOICES, tier=TIER_CHOICES)
async def testresult(
    interaction: discord.Interaction,
    mc_name: str,
    tester: discord.Member,
    gamemode: app_commands.Choice[str],
    tier: app_commands.Choice[str],
):
    await interaction.response.defer(ephemeral=True)

    # permission
    if not isinstance(interaction.user, discord.Member) or not has_staff_role(interaction.user):
        await interaction.followup.send("❌ Nincs jogod használni (STAFF_ROLE_ID kell).", ephemeral=True)
        return

    gm = gamemode.value
    new_rank = tier.value  # LT3 stb

    # előző rang automatikus
    prev_rank = await fetch_previous_rank(mc_name, gm)

    # POST to website
    payload = {
        "username": mc_name.strip(),
        "gamemode": gm,
        "rank": new_rank,
        "tester": str(tester.id),  # backendnek mindegy; weboldalon nem kell, de elküldjük
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

    # EMBED — pont úgy mint a képen, és kódokat írunk ki (LT3 stb)
    skin_url = f"https://mc-heads.net/avatar/{mc_name}/64"

    embed = discord.Embed(
        title=f"{mc_name} teszt eredménye 🏆",
        color=0x2b2d31
    )
    embed.set_thumbnail(url=skin_url)
    embed.add_field(name="Tesztelő:", value=tester.mention, inline=False)
    embed.add_field(name="Játékmód:", value=gm, inline=False)
    embed.add_field(name="Minecraft név:", value=mc_name, inline=False)
    embed.add_field(name="Előző rang:", value=prev_rank, inline=False)
    embed.add_field(name="Elért rang:", value=new_rank, inline=False)

    # küldés publikusba
    try:
        await interaction.channel.send(embed=embed)
    except Exception:
        pass

    pts = RANK_POINTS.get(new_rank, 0)
    await interaction.followup.send(
        f"✅ Mentve + weboldal frissítve.\nElőző: **{prev_rank}** → Elért: **{new_rank}** | **+{pts} pont**",
        ephemeral=True
    )

# =========================
# READY
# =========================
@client.event
async def on_ready():
    client.add_view(TicketView())
    client.add_view(CloseTicketView())
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"Logged in as {client.user}")

client.run(TOKEN)
