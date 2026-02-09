import discord
from discord import app_commands
from discord.ui import View, Button
import os
import aiohttp
import asyncio

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN env var missing!")

GUILD_ID = 1469740655520780631
STAFF_ROLE_ID = 1469755118634270864
TICKET_CATEGORY_ID = 1469766438238687496

API_URL = "https://neontiers.vercel.app/api/tests"
BOT_API_KEY = TOKEN

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

intents = discord.Intents.default()
intents.guilds = True
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


def has_staff_role(member: discord.Member) -> bool:
    return any(r.id == STAFF_ROLE_ID for r in member.roles)


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
                await interaction.followup.send(
                    "❌ Már van nyitott ticketed ebből a játékmódból.",
                    ephemeral=True
                )
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

        try:
            if ping_role:
                await channel.send(f"{ping_role.mention} | Új teszt kérés!")
            else:
                await channel.send("⚠️ Ping role nem található ehhez a módhoz.")
        except Exception:
            pass

        await channel.send(embed=make_ticket_embed(self.mode, interaction.user), view=CloseTicketView())
        await interaction.followup.send(f"✅ Ticket létrehozva: {channel.mention}", ephemeral=True)


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


@tree.command(name="testresult", description="Teszt eredmény elküldése a weboldalra", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    username="Minecraft név (skin ehhez)",
    gamemode="Játékmód",
    rank="Elért rang (pl. HT4)"
)
async def testresult(interaction: discord.Interaction, username: str, gamemode: str, rank: str):
    await interaction.response.defer(ephemeral=True)

    payload = {
        "username": username,
        "gamemode": gamemode,
        "rank": rank,
        "tester": interaction.user.name
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                API_URL,
                json=payload,
                headers={"Authorization": f"Bearer {BOT_API_KEY}"}
            ) as resp:
                if resp.status == 200:
                    await interaction.followup.send("✅ Teszt eredmény elküldve a weboldalra.", ephemeral=True)
                else:
                    text = await resp.text()
                    await interaction.followup.send(f"❌ Web API hiba: {resp.status}\n{text}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Hálózati/API hiba: {e}", ephemeral=True)


@client.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"Logged in as {client.user}")


client.run(TOKEN)
