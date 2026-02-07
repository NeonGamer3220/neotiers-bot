import os
import re
import discord
from discord import app_commands

# =========================
# CONFIG
# =========================
GUILD_ID = 1469740655520780631        # <-- állítsd át ha másik szerver
STAFF_ROLE_ID = 1469755118634270864     # <-- staff role id (aki kezeli a ticketeket)
TICKET_CATEGORY_ID = 0                  # <-- IDE írd a Tickets kategória ID-ját (kötelező)

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("Missing DISCORD_TOKEN environment variable")

# A gombok feliratai (a képedhez hasonló)
MODES = [
    "Vanilla", "UHC", "Pot", "NethPot", "SMP",
    "Sword", "Axe", "Mace", "Cart", "Creeper",
    "DiaSMP", "OGVanilla", "ShieldlessUHC",
]

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
class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Ticket zárás", style=discord.ButtonStyle.danger, custom_id="neotickets:close")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Csak szerveren használható.", ephemeral=True)
            return

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("Hibás csatorna.", ephemeral=True)
            return

        # Csak staff vagy ticket owner zárhassa
        is_staff = interaction.user.get_role(STAFF_ROLE_ID) is not None or interaction.user.guild_permissions.administrator
        is_owner = channel.topic and f"ticket_owner:{interaction.user.id}" in channel.topic

        if not (is_staff or is_owner):
            await interaction.response.send_message("Nincs jogosultságod bezárni ezt a ticketet.", ephemeral=True)
            return

        await interaction.response.send_message("✅ Ticket zárása... (csatorna törlés 5 mp múlva)", ephemeral=True)
        try:
            await channel.send("🔒 Ticket lezárva. A csatorna 5 mp múlva törlődik.")
        except Exception:
            pass

        await discord.utils.sleep_until(discord.utils.utcnow() + discord.timedelta(seconds=5))
        try:
            await channel.delete(reason=f"Ticket closed by {interaction.user} ({interaction.user.id})")
        except discord.Forbidden:
            # Ha nincs delete jog
            pass

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
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Csak szerveren használható.", ephemeral=True)
            return

        guild = interaction.guild
        user = interaction.user

        if TICKET_CATEGORY_ID == 0:
            await interaction.response.send_message("⚠️ A bot nincs beállítva: TICKET_CATEGORY_ID = 0", ephemeral=True)
            return

        existing = user_already_has_ticket(guild, user.id)
        if existing:
            await interaction.response.send_message(f"Van már ticketed: {existing.mention}", ephemeral=True)
            return

        category = guild.get_channel(TICKET_CATEGORY_ID)
        if not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message("⚠️ Hibás ticket kategória ID.", ephemeral=True)
            return

        staff_role = guild.get_role(STAFF_ROLE_ID)
        if staff_role is None:
            await interaction.response.send_message("⚠️ Hibás STAFF_ROLE_ID (nincs ilyen role).", ephemeral=True)
            return

        # Jogosultságok
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            staff_role: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }

        ch_name = ticket_channel_name(self.mode, user)

        await interaction.response.defer(ephemeral=True)

        channel = await guild.create_text_channel(
            name=ch_name,
            category=category,
            overwrites=overwrites,
            topic=f"ticket_owner:{user.id} | mode:{self.mode}",
            reason=f"Ticket opened by {user} ({user.id}) - {self.mode}"
        )

        embed = discord.Embed(
            title="Teszt kérés",
            description=f"**Játékmód:** `{self.mode}`\n**Nyitotta:** {user.mention}\n\nÍrj ide részleteket, staff hamarosan jön.",
            color=discord.Color.blurple()
        )

        await channel.send(content=f"{user.mention} {staff_role.mention}", embed=embed, view=CloseTicketView())
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
        # Persistent views
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
        description="Kattints egy alábbi gombra, hogy tudd tesztelni a gombon feltüntetett játékmódból.",
        color=discord.Color.blurple()
    )
    await interaction.response.send_message(embed=embed, view=TicketPanelView())

bot.run(TOKEN)
