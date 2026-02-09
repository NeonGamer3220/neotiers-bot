import os
import json
import time
import asyncio
from datetime import datetime, timezone

import requests
import discord
from discord import app_commands
from discord.ui import View, Button

# =========================================
# CONFIG (EDIT THESE)
# =========================================
GUILD_ID = 1469740655520780631
STAFF_ROLE_ID = 1469755118634270864
TICKET_CATEGORY_ID = 1469766438238687496

SITE_URL = "https://neontiers.vercel.app"
COOLDOWN_DAYS = 14

# Gamemode -> ping role ID (these get pinged on ticket create)
GAMEMODE_PING_ROLES = {
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

GAMEMODES = [
    "Vanilla", "UHC", "Pot", "NethPot", "SMP",
    "Sword", "Axe", "Mace", "Cart", "Creeper",
    "DiaSMP", "OGVanilla", "ShieldlessUHC",
    "SpearMace", "SpearElytra",
]

RANKS = ["Unranked", "LT5", "HT5", "LT4", "HT4", "LT3", "HT3", "LT2", "HT2", "LT1", "HT1"]

# Where we persist data (cooldowns + open tickets + prev ranks)
DATA_FILE = "data.json"


# =========================================
# STORAGE
# =========================================
_storage_lock = asyncio.Lock()
_storage = {
    "cooldowns": {},   # user_id -> mode -> last_closed_unix
    "open": {},        # channel_id -> { "user_id": int, "mode": str }
    "prev_ranks": {}   # mc_name_lower -> mode -> rank
}

def _now_unix() -> int:
    return int(time.time())

def _load_storage():
    global _storage
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                _storage = json.load(f)
    except Exception:
        # if file is broken, keep defaults
        pass

def _save_storage():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(_storage, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# =========================================
# WEB POST
# =========================================
def post_test_to_site(username: str, gamemode: str, rank: str, tester: str = "") -> tuple[bool, str]:
    key = os.getenv("BOT_API_KEY", "")
    if not key:
        return False, "BOT_API_KEY env hiányzik a botnál."

    url = f"{SITE_URL}/api/tests"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "username": username,
        "gamemode": gamemode,
        "rank": rank,
        "tester": tester,
    }

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        if r.status_code != 200:
            return False, f"API {r.status_code}: {r.text[:250]}"
        return True, "OK"
    except Exception as e:
        return False, f"Request failed: {e}"


# =========================================
# DISCORD BOT
# =========================================
class NeoTiersBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        _load_storage()

        # Persistent views
        self.add_view(TicketPanelView())
        self.add_view(CloseTicketView())

        guild = discord.Object(id=GUILD_ID)
        await self.tree.sync(guild=guild)

    async def on_ready(self):
        print(f"Logged in as {self.user} (id={self.user.id})")


bot = NeoTiersBot()


# =========================================
# PERMISSION / UTILS
# =========================================
def is_staff(member: discord.Member) -> bool:
    return any(r.id == STAFF_ROLE_ID for r in member.roles) or member.guild_permissions.administrator

def human_remaining(seconds: int) -> str:
    if seconds <= 0:
        return "0 mp"
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    mins = (seconds % 3600) // 60
    if days > 0:
        return f"{days} nap {hours} óra"
    if hours > 0:
        return f"{hours} óra {mins} perc"
    return f"{mins} perc"

def safe_channel_name(mode: str, user: discord.Member) -> str:
    base = f"{mode}-{user.name}".lower()
    base = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in base)
    if len(base) > 90:
        base = base[:90]
    return f"ticket-{base}"

async def can_open_mode(user_id: int, mode: str) -> tuple[bool, str]:
    async with _storage_lock:
        # Prevent opening same mode if already open
        for ch_id, info in _storage.get("open", {}).items():
            if int(info.get("user_id", 0)) == user_id and info.get("mode") == mode:
                return False, "Van már nyitott ticketed ebből a játékmódból."

        # Cooldown check
        last = _storage.get("cooldowns", {}).get(str(user_id), {}).get(mode, 0)
        if last:
            now = _now_unix()
            cd_seconds = COOLDOWN_DAYS * 86400
            remain = (last + cd_seconds) - now
            if remain > 0:
                return False, f"Erre a módra még cooldown van: {human_remaining(remain)}"

    return True, "OK"


# =========================================
# TICKET VIEWS
# =========================================
class TicketPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

        # Buttons (no icons; Discord buttons text only)
        # Layout: Discord auto-wraps.
        for mode in [
            "Vanilla", "UHC", "Pot", "NethPot", "SMP",
            "Sword", "Axe", "Mace", "Cart", "Creeper",
            "DiaSMP", "OGVanilla", "ShieldlessUHC",
            "SpearMace", "SpearElytra"
        ]:
            self.add_item(OpenTicketButton(mode))


class OpenTicketButton(Button):
    def __init__(self, mode: str):
        super().__init__(label=mode, style=discord.ButtonStyle.primary, custom_id=f"open_ticket:{mode}")
        self.mode = mode

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if interaction.guild is None:
            await interaction.followup.send("❌ Ezt csak szerveren lehet használni.", ephemeral=True)
            return
        if interaction.guild.id != GUILD_ID:
            await interaction.followup.send("❌ Rossz szerver.", ephemeral=True)
            return

        ok, reason = await can_open_mode(interaction.user.id, self.mode)
        if not ok:
            await interaction.followup.send(f"🔒 {reason}", ephemeral=True)
            return

        guild = interaction.guild
        category = guild.get_channel(TICKET_CATEGORY_ID)
        if category is None or not isinstance(category, discord.CategoryChannel):
            await interaction.followup.send("❌ Ticket kategória rosszul van beállítva.", ephemeral=True)
            return

        staff_role = guild.get_role(STAFF_ROLE_ID)
        if staff_role is None:
            await interaction.followup.send("❌ STAFF_ROLE_ID rossz.", ephemeral=True)
            return

        # Overwrites: only opener + staff
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            staff_role: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }

        try:
            channel = await guild.create_text_channel(
                name=safe_channel_name(self.mode, interaction.user),
                category=category,
                overwrites=overwrites,
                topic=f"NeoTiers Ticket | mode={self.mode} | user_id={interaction.user.id}",
            )
        except discord.Forbidden:
            await interaction.followup.send("❌ A botnak nincs joga csatornát létrehozni ebben a kategóriában.", ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(f"❌ Hiba csatorna létrehozásnál: {e}", ephemeral=True)
            return

        # Store open ticket mapping
        async with _storage_lock:
            _storage.setdefault("open", {})[str(channel.id)] = {"user_id": interaction.user.id, "mode": self.mode}
            _save_storage()

        # Ping role for this mode, fallback ping staff role
        ping_role_id = GAMEMODE_PING_ROLES.get(self.mode)
        ping_text = f"<@&{ping_role_id}>" if ping_role_id else f"<@&{STAFF_ROLE_ID}>"

        embed = discord.Embed(
            title="Teszt kérés",
            description="Kattints a **Close** gombra, ha vége a tesztnek.\n"
                        "A cooldown csak lezárás után indul (14 nap / mód).",
            color=discord.Color.blurple()
        )
        embed.add_field(name="Játékmód", value=self.mode, inline=True)
        embed.add_field(name="Nyitotta", value=f"<@{interaction.user.id}>", inline=True)
        embed.set_footer(text="NeoTiers Ticket System")

        await channel.send(content=ping_text, embed=embed, view=CloseTicketView())
        await interaction.followup.send(f"✅ Ticket létrehozva: {channel.mention}", ephemeral=True)


class CloseTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CloseTicketButton())


class CloseTicketButton(Button):
    def __init__(self):
        super().__init__(label="Ticket zárása", style=discord.ButtonStyle.danger, custom_id="close_ticket")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if interaction.guild is None or interaction.channel is None:
            await interaction.followup.send("❌ Ez csak szerveren működik.", ephemeral=True)
            return

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("❌ Nem szöveg csatorna.", ephemeral=True)
            return

        # Determine owner/mode from storage
        async with _storage_lock:
            info = _storage.get("open", {}).get(str(channel.id))

        if not info:
            # if not tracked, still allow staff to delete
            if not is_staff(interaction.user):
                await interaction.followup.send("❌ Nincs hozzáférés.", ephemeral=True)
                return
            try:
                await interaction.followup.send("✅ Zárás... (3 mp)", ephemeral=True)
                await asyncio.sleep(3)
                await channel.delete(reason="Ticket closed (untracked).")
            except discord.Forbidden:
                await interaction.followup.send("❌ A botnak nincs joga törölni a csatornát.", ephemeral=True)
            return

        owner_id = int(info.get("user_id", 0))
        mode = info.get("mode", "Unknown")

        # Only owner or staff can close
        if interaction.user.id != owner_id and not is_staff(interaction.user):
            await interaction.followup.send("❌ Ezt csak a ticket nyitója vagy staff zárhatja.", ephemeral=True)
            return

        # Set cooldown + remove open mapping
        async with _storage_lock:
            _storage.setdefault("cooldowns", {}).setdefault(str(owner_id), {})[mode] = _now_unix()
            _storage.setdefault("open", {}).pop(str(channel.id), None)
            _save_storage()

        try:
            await interaction.followup.send("✅ Ticket zárva. 3 mp múlva törlöm a csatornát.", ephemeral=True)
            await asyncio.sleep(3)
            await channel.delete(reason=f"Ticket closed | mode={mode} | owner={owner_id}")
        except discord.Forbidden:
            await interaction.followup.send("❌ A botnak nincs joga törölni a csatornát (Manage Channels kell).", ephemeral=True)


# =========================================
# SLASH COMMANDS
# =========================================
@bot.tree.command(name="ticketpanel", description="Kirakja a ticket panelt (csak staff).", guild=discord.Object(id=GUILD_ID))
async def ticketpanel(interaction: discord.Interaction):
    if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user):
        await interaction.response.send_message("❌ Nincs hozzáférés.", ephemeral=True)
        return

    embed = discord.Embed(
        title="Teszt kérés",
        description="Kattints egy gombra, hogy ticketet nyiss a választott játékmódból.\n"
                    f"Cooldown: **{COOLDOWN_DAYS} nap / mód** (lezárás után).",
        color=discord.Color.blurple()
    )
    await interaction.response.send_message(embed=embed, view=TicketPanelView())


@bot.tree.command(name="pingapi", description="Teszt: küld egy próba POST-ot a weboldalra.", guild=discord.Object(id=GUILD_ID))
async def pingapi(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    ok, msg = post_test_to_site(
        username="debugUser",
        gamemode="Mace",
        rank="HT4",
        tester=str(interaction.user.id)
    )

    if ok:
        await interaction.followup.send("✅ POST sikeres! Nézd meg: https://neontiers.vercel.app/api/tests", ephemeral=True)
    else:
        await interaction.followup.send(f"❌ POST nem ment: {msg}", ephemeral=True)


@bot.tree.command(name="testresult", description="Teszt eredmény (előző rang automatikus + web sync).", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    testedplayer="Minecraft név (nem Discord név)",
    tester="Tesztelő Discord tag",
    username="Skin név (általában ugyanaz, mint a MC név)",
    gamemode="Játékmód",
    rank_earned="Elért rang"
)
@app_commands.choices(
    gamemode=[app_commands.Choice(name=m, value=m) for m in GAMEMODES],
    rank_earned=[app_commands.Choice(name=r, value=r) for r in RANKS],
)
async def testresult(
    interaction: discord.Interaction,
    testedplayer: str,
    tester: discord.Member,
    username: str,
    gamemode: app_commands.Choice[str],
    rank_earned: app_commands.Choice[str],
):
    # permission: staff only
    if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user):
        await interaction.response.send_message("❌ Nincs hozzáférés.", ephemeral=True)
        return

    await interaction.response.defer()  # avoid "app didn't respond"

    mc_key = testedplayer.strip().lower()
    mode = gamemode.value
    earned = rank_earned.value

    # get prev rank + update storage
    async with _storage_lock:
        prev = _storage.setdefault("prev_ranks", {}).setdefault(mc_key, {}).get(mode, "Unranked")
        _storage["prev_ranks"][mc_key][mode] = earned
        _save_storage()

    # send to website (earned rank)
    ok, msg = post_test_to_site(
        username=testedplayer.strip(),
        gamemode=mode,
        rank=earned,
        tester=str(tester.id)
    )

    emb = discord.Embed(
        title=f"{testedplayer.strip()} — Teszt eredmény",
        color=discord.Color.blurple()
    )
    emb.add_field(name="Tesztelő", value=f"<@{tester.id}>", inline=False)
    emb.add_field(name="Játékmód", value=mode, inline=True)
    emb.add_field(name="Előző rang", value=prev, inline=True)
    emb.add_field(name="Elért rang", value=earned, inline=True)
    emb.add_field(name="Skin név", value=username.strip(), inline=False)

    if ok:
        emb.set_footer(text="✅ Web sync sikeres (neontiers.vercel.app)")
    else:
        emb.set_footer(text=f"⚠️ Web sync FAILED: {msg[:120]}")

    await interaction.followup.send(embed=emb)


# =========================================
# RUN
# =========================================
token = os.getenv("DISCORD_TOKEN", "")
if not token:
    raise RuntimeError("DISCORD_TOKEN env hiányzik (Discord bot token).")

bot.run(token)
