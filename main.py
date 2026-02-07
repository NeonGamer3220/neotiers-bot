import os
import re
import discord
from discord import app_commands

# =========================
# CONFIG (EDIT THESE)
# =========================
GUILD_ID = 1469740655520780631         # your server id
STAFF_ROLE_ID = 1469755118634270864     # staff role that can see tickets (and fallback ping)
TICKET_CATEGORY_ID = 1469766438238687496                # <-- put your TICKETS category ID here (MUST NOT BE 0)

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("Missing DISCORD_TOKEN environment variable (Railway Variables -> DISCORD_TOKEN)")

# =========================
# MODES (BUTTONS)
# =========================
MODES = [
    "Vanilla", "UHC", "Pot", "NethPot", "SMP",
    "Sword", "Axe", "Mace", "Cart", "Creeper",
    "DiaSMP", "OGVanilla", "ShieldlessUHC",
    "Spear Elytra", "Spear Mace",
]

# =========================
# MODE -> PING ROLE ID MAP
# (pings these roles instead of "tester")
# =========================
MODE_PING_ROLE_IDS = {
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
    "Spear Elytra": 1469764028195668199,
    "Spear Mace": 1469763993857163359,
    "Cart": 1469763920871952435,
    "DiaSMP": 1469763946968911893,
    "Creeper": 1469764200812249180,
}

# =========================
# HELPERS
# =========================
def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:20] if len(s) > 20 else s

def ticket_channel_name(mode: str, user: discord.Member) -> str:
    base = f"ticket-{slugify(mode)}-{slugify(user.name)}"
    return base[:90]

def user_already_has_ticket(guild: discord.Guild, user_id: int) -> discord.TextChannel | None:
    for ch in guild.text_channels:
        if ch.topic and f"ticket_owner:{user_id}" in ch.topic:
            return ch
    return None

# =========================
# VIEWS (PERSISTENT BUTTONS)
# =========================
import asyncio
import discord

class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Ticket zárás", style=discord.ButtonStyle.danger, custom_id="neotickets:close")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        channel = interaction.channel

        if guild is None or not isinstance(channel, discord.TextChannel) or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("❌ Hibás környezet (guild/channel).", ephemeral=True)
            return

        me = guild.me or guild.get_member(interaction.client.user.id)
        if me is None:
            await interaction.followup.send("❌ Nem találom a bot membert (guild.me).", ephemeral=True)
            return

        perms = channel.permissions_for(me)
        if not perms.manage_channels:
            await interaction.followup.send(
                "❌ Nem tudom törölni a csatornát: **Manage Channels** hiányzik ebben a ticket csatornában / kategóriában.",
                ephemeral=True
            )
            return

        # ki zárhatja: ticket owner vagy staff/admin
        staff_role = guild.get_role(STAFF_ROLE_ID)
        is_staff = interaction.user.guild_permissions.administrator or (staff_role and staff_role in interaction.user.roles)
        is_owner = channel.topic and f"ticket_owner:{interaction.user.id}" in channel.topic

        if not (is_staff or is_owner):
            await interaction.followup.send("❌ Nincs jogod bezárni ezt a ticketet.", ephemeral=True)
            return

        await interaction.followup.send("✅ Ticket zárása... (törlés 3 mp múlva)", ephemeral=True)
        try:
            await channel.send("🔒 Ticket lezárva. A csatorna 3 mp múlva törlődik.")
        except Exception:
            pass

        await asyncio.sleep(3)

        try:
            await channel.delete(reason=f"Ticket closed by {interaction.user} ({interaction.user.id})")
        except discord.Forbidden:
            await channel.send("❌ 403: Nem tudtam törölni (permission). Nézd meg a Tickets kategória/jogokat.")
        except Exception as e:
            await channel.send(f"❌ Nem tudtam törölni: {type(e).__name__}: {e}")


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for mode in MODES:
            self.add_item(TicketModeButton(mode))


class TicketModeButton(discord.ui.Button):
    def __init__(self, mode: str):
        super().__init__(
            label=mode,
            style=discord.ButtonStyle.primary,
            custom_id=f"neotickets:open:{slugify(mode)}"
        )
        self.mode = mode

    async def callback(self, interaction: discord.Interaction):
        # Prevent "Az alkalmazás nem válaszolt"
        await interaction.response.defer(ephemeral=True)

        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("Csak szerveren használható.", ephemeral=True)
            return

        guild = interaction.guild
        user = interaction.user

        if TICKET_CATEGORY_ID == 0:
            await interaction.followup.send("⚠️ A bot nincs beállítva: TICKET_CATEGORY_ID = 0", ephemeral=True)
            return

        existing = user_already_has_ticket(guild, user.id)
        if existing:
            await interaction.followup.send(f"Van már ticketed: {existing.mention}", ephemeral=True)
            return

        category = guild.get_channel(TICKET_CATEGORY_ID)
        if not isinstance(category, discord.CategoryChannel):
            await interaction.followup.send("⚠️ Hibás ticket kategória ID (nem Category).", ephemeral=True)
            return

        staff_role = guild.get_role(STAFF_ROLE_ID)
        if staff_role is None:
            await interaction.followup.send("⚠️ Hibás STAFF_ROLE_ID (nincs ilyen role).", ephemeral=True)
            return

        # Check create perms quickly (helps debugging)
        me = guild.me
        if me is None:
            await interaction.followup.send("Bot guild.me hiba.", ephemeral=True)
            return

        if not category.permissions_for(me).manage_channels:
            await interaction.followup.send(
                "❌ A bot nem tud csatornát létrehozni ebben a kategóriában.\n"
                "Kell: ✅ View Channel + ✅ Manage Channels a TICKETS kategóriában a bot role-nak.",
                ephemeral=True
            )
            return

        # Overwrites: only user + staff role can see
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            staff_role: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }

        ch_name = ticket_channel_name(self.mode, user)

        # Create channel
        try:
            channel = await guild.create_text_channel(
                name=ch_name,
                category=category,
                overwrites=overwrites,
                topic=f"ticket_owner:{user.id} | mode:{self.mode}",
                reason=f"Ticket opened by {user} ({user.id}) - {self.mode}"
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Missing Permissions: a bot nem tud csatornát létrehozni itt.\n"
                "Ellenőrizd a kategória permissionöket (nincs piros X a bot role-nál).",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="Teszt kérés",
            description=(
                f"**Játékmód:** `{self.mode}`\n"
                f"**Nyitotta:** {user.mention}\n\n"
                "Írj ide részleteket, staff hamarosan jön."
            ),
            color=discord.Color.blurple()
        )

        # Ping mode-specific role (fallback to staff role if missing)
        ping_role_id = MODE_PING_ROLE_IDS.get(self.mode)
        ping_role = guild.get_role(ping_role_id) if ping_role_id else None

        pings = [user.mention]
        if ping_role:
            pings.append(ping_role.mention)
        else:
            pings.append(staff_role.mention)

        await channel.send(content=" ".join(pings), embed=embed, view=CloseTicketView())
        await interaction.followup.send(f"✅ Ticket megnyitva: {channel.mention}", ephemeral=True)


# =========================
# BOT
# =========================
class NeoTiersTicketBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        # Persistent views (buttons survive restart)
        self.add_view(TicketPanelView())
        self.add_view(CloseTicketView())

        guild = discord.Object(id=GUILD_ID)
        await self.tree.sync(guild=guild)
        print(f"Commands synced to guild {GUILD_ID}")


bot = NeoTiersTicketBot()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id={bot.user.id})")


# =========================
# COMMAND: POST PANEL
# =========================
@bot.tree.command(name="ticketpanel", description="(Admin) Kirakja a NeoTiers ticket panelt.")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def ticketpanel(interaction: discord.Interaction):
    if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Csak admin rakhat ki panelt.", ephemeral=True)
        return

    embed = discord.Embed(
        title="Teszt kérés",
        description="Kattints egy alábbi gombra, hogy tudj ticketet nyitni a kiválasztott játékmódhoz.",
        color=discord.Color.blurple()
    )
    await interaction.response.send_message(embed=embed, view=TicketPanelView())


bot.run(TOKEN)
