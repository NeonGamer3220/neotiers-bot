import os
import re
import json
import asyncio
import discord
from discord import app_commands

# =========================
# CONFIG (YOUR CORRECT ONES)
# =========================
GUILD_ID = 1469740655520780631
STAFF_ROLE_ID = 1469755118634270864
TICKET_CATEGORY_ID = 1469766438238687496

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("Missing DISCORD_TOKEN env var (Railway Variables -> DISCORD_TOKEN)")

# =========================
# TICKET SYSTEM CONFIG
# =========================
MODES = [
    "Vanilla", "UHC", "Pot", "NethPot", "SMP",
    "Sword", "Axe", "Mace", "Cart", "Creeper",
    "DiaSMP", "OGVanilla", "ShieldlessUHC",
    "Spear Elytra", "Spear Mace",
]

# mode -> ping role id (YOUR LIST)
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
# TESTRESULT CONFIG
# =========================
HISTORY_FILE = "test_history.json"

# who can use /testresult:
# - admins always
# - plus: staff role id (you can add more IDs here if you want)
ALLOWED_ROLE_IDS = {STAFF_ROLE_ID}

# gamemodes same as ticket
GAMEMODE_CHOICES = [app_commands.Choice(name=m, value=m) for m in MODES]

# Hungarian display -> stored value (MCTIERS style)
RANKS = [
    ("Nem rangsorolt", "Unranked"),
    ("Alacsony Tier 5", "Low Tier 5"),
    ("Magas Tier 5", "High Tier 5"),
    ("Alacsony Tier 4", "Low Tier 4"),
    ("Magas Tier 4", "High Tier 4"),
    ("Alacsony Tier 3", "Low Tier 3"),
    ("Magas Tier 3", "High Tier 3"),
    ("Alacsony Tier 2", "Low Tier 2"),
    ("Magas Tier 2", "High Tier 2"),
    ("Alacsony Tier 1", "Low Tier 1"),
    ("Magas Tier 1", "High Tier 1"),
]
RANK_CHOICES = [app_commands.Choice(name=hu, value=val) for hu, val in RANKS]
RANK_VALUE_TO_HU = {val: hu for hu, val in RANKS}

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

def user_already_has_ticket_for_mode(guild: discord.Guild, user_id: int, mode: str) -> discord.TextChannel | None:
    needle_owner = f"ticket_owner:{user_id}"
    needle_mode = f"mode:{mode}"
    for ch in guild.text_channels:
        if not ch.topic:
            continue
        if needle_owner in ch.topic and needle_mode in ch.topic:
            return ch
    return None

def mc_avatar(username: str) -> str:
    u = username.strip().replace(" ", "")
    return f"https://mc-heads.net/avatar/{u}/128"

def sanitize_player_key(name: str) -> str:
    return re.sub(r"\s+", "", name.strip().lower())

def load_history() -> dict:
    if not os.path.exists(HISTORY_FILE):
        return {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_history(data: dict) -> None:
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def can_use_testresult(interaction: discord.Interaction) -> bool:
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return False
    member: discord.Member = interaction.user
    if member.guild_permissions.administrator:
        return True
    return any(r.id in ALLOWED_ROLE_IDS for r in member.roles)

# =========================
# VIEWS (PERSISTENT)
# =========================
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
                "❌ Nem tudom törölni a csatornát: **Manage Channels** hiányzik ebben a csatornában/kategóriában.",
                ephemeral=True
            )
            return

        # who can close: ticket owner OR staff/admin
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
            try:
                await channel.send("❌ 403: Nem tudtam törölni (permission kategóriában/csatornában).")
            except Exception:
                pass
        except Exception as e:
            try:
                await channel.send(f"❌ Nem tudtam törölni: {type(e).__name__}: {e}")
            except Exception:
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
        await interaction.response.defer(ephemeral=True)

        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("Csak szerveren használható.", ephemeral=True)
            return

        guild = interaction.guild
        user = interaction.user

        existing = user_already_has_ticket_for_mode(guild, user.id, self.mode)
if existing:
    await interaction.followup.send(
        f"❌ Már van nyitott ticketed ebben a játékmódban (**{self.mode}**): {existing.mention}",
        ephemeral=True
    )
    return

        category = guild.get_channel(TICKET_CATEGORY_ID)
        if not isinstance(category, discord.CategoryChannel):
            await interaction.followup.send("⚠️ Hibás TICKET_CATEGORY_ID (nem Category).", ephemeral=True)
            return

        staff_role = guild.get_role(STAFF_ROLE_ID)
        if staff_role is None:
            await interaction.followup.send("⚠️ Hibás STAFF_ROLE_ID (nincs ilyen role).", ephemeral=True)
            return

        me = guild.me or guild.get_member(interaction.client.user.id)
        if me is None:
            await interaction.followup.send("⚠️ Bot member hiba (guild.me).", ephemeral=True)
            return

        if not category.permissions_for(me).manage_channels:
            await interaction.followup.send(
                "❌ A bot nem tud csatornát létrehozni ebben a kategóriában.\n"
                "Fix: Tickets kategória permission → bot role: ✅ View Channel + ✅ Manage Channels",
                ephemeral=True
            )
            return

        # overwrites: everyone hidden, staff+user allowed, bot explicitly allowed
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            staff_role: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True, embed_links=True, attach_files=True
            ),
        }

        ch_name = ticket_channel_name(self.mode, user)

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
                "❌ Missing Permissions: a bot nem tud csatornát létrehozni itt (kategória/role deny).",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="Teszt kérés",
            description=(
                "Kattintsott játékmód alapján ticket nyílt.\n\n"
                f"**Játékmód:** `{self.mode}`\n"
                f"**Nyitotta:** {user.mention}\n\n"
                "Írj ide részleteket, staff hamarosan jön."
            ),
            color=discord.Color.blurple()
        )

        ping_role_id = MODE_PING_ROLE_IDS.get(self.mode)
        ping_role = guild.get_role(ping_role_id) if ping_role_id else None

        pings = [user.mention]
        if ping_role:
            pings.append(ping_role.mention)
        else:
            # fallback if missing map
            pings.append(staff_role.mention)

        try:
            await channel.send(content=" ".join(pings), embed=embed, view=CloseTicketView())
        except Exception as e:
            await interaction.followup.send(f"⚠️ Ticket létrejött, de üzenet hiba: {type(e).__name__}: {e}", ephemeral=True)
            return

        await interaction.followup.send(f"✅ Ticket megnyitva: {channel.mention}", ephemeral=True)

# =========================
# BOT
# =========================
class NeoTiersBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        # persistent buttons survive restart
        self.add_view(TicketPanelView())
        self.add_view(CloseTicketView())

        guild = discord.Object(id=GUILD_ID)
        await self.tree.sync(guild=guild)
        print(f"Slash commands synced to guild {GUILD_ID}")

bot = NeoTiersBot()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id={bot.user.id})")

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    print("APP COMMAND ERROR:", repr(error))
    try:
        msg = f"❌ Hiba: {error}"
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except Exception:
        pass

# =========================
# COMMAND: TICKET PANEL
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

# =========================
# COMMAND: RESYNC (optional helper)
# =========================
@bot.tree.command(name="resync", description="(Admin) Slash parancsok újraszinkronizálása ehhez a szerverhez.")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def resync(interaction: discord.Interaction):
    if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Csak admin használhatja.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    await interaction.followup.send("✅ Újraszinkronizálva.", ephemeral=True)

# =========================
# COMMAND: TESTRESULT (MCTIERS)
# =========================
@bot.tree.command(name="testresult", description="MCTIERS teszt eredmény (előző rang automatikus, nincs region).")
@app_commands.guilds(discord.Object(id=GUILD_ID))
@app_commands.describe(
    testedplayer="Tesztelt játékos (Minecraft név, nem Discord user)",
    tester="Tesztelő (Discord user)",
    username="Minecraft név a skin/fejhez",
    gamemode="Játékmód",
    rank_earned="Elért rang",
)
@app_commands.choices(gamemode=GAMEMODE_CHOICES, rank_earned=RANK_CHOICES)
async def testresult(
    interaction: discord.Interaction,
    testedplayer: str,
    tester: discord.Member,
    username: str,
    gamemode: app_commands.Choice[str],
    rank_earned: app_commands.Choice[str],
):
    if not can_use_testresult(interaction):
        await interaction.response.send_message("❌ Nincs jogosultságod ehhez a parancshoz.", ephemeral=True)
        return

    await interaction.response.defer()

    history = load_history()
    player_key = sanitize_player_key(testedplayer)
    mode = gamemode.value

    previous_value = "Unranked"
    if player_key in history and isinstance(history[player_key], dict) and mode in history[player_key]:
        previous_value = history[player_key][mode]

    # save new earned rank
    history.setdefault(player_key, {})
    history[player_key][mode] = rank_earned.value
    save_history(history)

    prev_hu = RANK_VALUE_TO_HU.get(previous_value, previous_value)
    earned_hu = RANK_VALUE_TO_HU.get(rank_earned.value, rank_earned.value)

    embed = discord.Embed(
        title=f"{testedplayer} teszt eredménye 🏆",
        color=discord.Color.red()
    )
    embed.set_thumbnail(url=mc_avatar(username))

    embed.add_field(name="Tesztelő:", value=tester.mention, inline=False)
    embed.add_field(name="Játékmód:", value=mode, inline=False)
    embed.add_field(name="Minecraft név:", value=username, inline=False)
    embed.add_field(name="Előző rang:", value=prev_hu, inline=False)
    embed.add_field(name="Elért rang:", value=earned_hu, inline=False)

    await interaction.followup.send(embed=embed)

# =========================
# START
# =========================
bot.run(TOKEN)
