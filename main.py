import discord
from discord import app_commands
from discord.ui import View, Button
import os
import requests

TOKEN = os.getenv("DISCORD_TOKEN")

GUILD_ID = 1469740655520780631
STAFF_ROLE_ID = 1469755118634270864
TICKET_CATEGORY_ID = 1469766438238687496

API_URL = "https://neontiers.vercel.app/api/tests"
BOT_API_KEY = TOKEN  # ugyanaz

PING_ROLES = {
    "Sword": 1469763677141074125,
    "Axe": 1469763738889486518,
    "Mace": 1469763612452196375,
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

intents = discord.Intents.default()
intents.guilds = True
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# =========================
# READY
# =========================
@client.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"Logged in as {client.user}")

# =========================
# TICKET PANEL
# =========================
class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
        for name in PING_ROLES.keys():
            self.add_item(TicketButton(name))

class TicketButton(Button):
    def __init__(self, mode):
        super().__init__(label=mode, style=discord.ButtonStyle.primary)
        self.mode = mode

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        category = guild.get_channel(TICKET_CATEGORY_ID)

        # van-e már ticket ebből a módból
        for ch in category.text_channels:
            if ch.topic == f"{interaction.user.id}:{self.mode}":
                await interaction.response.send_message(
                    "❌ Már van nyitott ticketed ebből a játékmódból.",
                    ephemeral=True
                )
                return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.get_role(STAFF_ROLE_ID): discord.PermissionOverwrite(view_channel=True)
        }

        channel = await guild.create_text_channel(
            name=f"{self.mode.lower()}-{interaction.user.name}",
            category=category,
            overwrites=overwrites,
            topic=f"{interaction.user.id}:{self.mode}"
        )

        role = guild.get_role(PING_ROLES[self.mode])
        await channel.send(f"{role.mention} | Új teszt kérés!")

        await channel.send(
            "❌ Ticket bezárása:",
            view=CloseTicketView()
        )

        await interaction.response.send_message(
            f"✅ Ticket létrehozva: {channel.mention}",
            ephemeral=True
        )

class CloseTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CloseTicketButton())

class CloseTicketButton(Button):
    def __init__(self):
        super().__init__(label="Ticket bezárása", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("🗑 Ticket törlés 3 mp múlva...")
        await interaction.channel.delete(delay=3)

# =========================
# PANEL PARANCS
# =========================
@tree.command(name="ticketpanel", description="Teszt kérő panel", guild=discord.Object(id=GUILD_ID))
async def ticketpanel(interaction: discord.Interaction):
    if STAFF_ROLE_ID not in [r.id for r in interaction.user.roles]:
        await interaction.response.send_message("❌ Nincs jogod.", ephemeral=True)
        return

    await interaction.channel.send(
        "🧪 **Teszt kérés**\nVálassz játékmódot:",
        view=TicketView()
    )
    await interaction.response.send_message("✅ Panel elküldve.", ephemeral=True)

# =========================
# TESTRESULT → WEB
# =========================
@tree.command(name="testresult", description="Teszt eredmény rögzítése", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    username="Minecraft név",
    gamemode="Játékmód",
    rank="Elért rang"
)
async def testresult(
    interaction: discord.Interaction,
    username: str,
    gamemode: str,
    rank: str
):
    payload = {
        "username": username,
        "gamemode": gamemode,
        "rank": rank,
        "tester": interaction.user.name
    }

    r = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {BOT_API_KEY}",
            "Content-Type": "application/json"
        },
        json=payload
    )

    if r.status_code == 200:
        await interaction.response.send_message("✅ Teszt eredmény elküldve a weboldalra.")
    else:
        await interaction.response.send_message("❌ Hiba a web API-nál.")

# =========================
client.run(TOKEN)
