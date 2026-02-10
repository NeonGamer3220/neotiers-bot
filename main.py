import os
import json
import time
import asyncio
from typing import Optional, Dict, Any, List, Tuple

import discord
from discord import app_commands
from discord.ext import commands

# =========================
# ENV CONFIG
# =========================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()

WEBSITE_BASE_URL = os.getenv("WEBSITE_BASE_URL", "https://neontiers.vercel.app").rstrip("/")
BOT_API_KEY = os.getenv("BOT_API_KEY", "").strip()  # web API key (nem discord token!)

GUILD_ID = int(os.getenv("GUILD_ID", "1469740655520780631"))
STAFF_ROLE_ID = int(os.getenv("STAFF_ROLE_ID", "1469755118634270864"))
TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID", "1469766438238687496"))

# 14 nap cooldown gamemode-onként ticketre
TICKET_COOLDOWN_SECONDS = 14 * 24 * 60 * 60

# Fájlok (Railway-n általában megmarad a konténer életén belül; ha újra buildel, nullázódhat)
OPEN_TICKETS_FILE = "open_tickets.json"
COOLDOWNS_FILE = "ticket_cooldowns.json"

# =========================
# GAMEMODES + PING ROLE IDS
# =========================
# Ticket gombok / gamemode opciók
GAMEMODES: List[str] = [
    "Vanilla", "UHC", "Pot", "NethPot", "SMP",
    "Sword", "Axe", "Mace", "Cart", "Creeper",
    "DiaSMP", "OGVanilla", "ShieldlessUHC",
    "SpearMace", "SpearElytra",
]

# PING ROLE ID-k gamemode szerint (amit te küldtél)
PING_ROLE_BY_MODE: Dict[str, int] = {
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

# Kik használhatják a /testresult parancsot:
# - staff role, vagy bármelyik gamemode teszter szerep (itt a ping role id-ket használjuk)
ALLOWED_TESTER_ROLE_IDS: List[int] = [STAFF_ROLE_ID] + list(set(PING_ROLE_BY_MODE.values()))

# =========================
# RANKS (short kódok)
# =========================
# Te ezt akarod: LT3/HT3 jellegű, nem "Alacsony Tier 3"
RANKS: List[str] = [
    "Unranked",
    "LT5", "HT5",
    "LT4", "HT4",
    "LT3", "HT3",
    "LT2", "HT2",
    "LT1", "HT1",
]

# Pontok: a screenshot alapján a +8 pont = HT2 pontja (tehát NEM diff, hanem az új rank pontja)
RANK_POINTS: Dict[str, int] = {
    "Unranked": 0,
    "LT5": 1, "HT5": 2,
    "LT4": 3, "HT4": 4,
    "LT3": 5, "HT3": 6,
    "LT2": 7, "HT2": 8,
    "LT1": 9, "HT1": 10,
}

# =========================
# HELPERS: JSON STORE
# =========================
def _load_json(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def _save_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

open_tickets: Dict[str, Dict[str, int]] = _load_json(OPEN_TICKETS_FILE, {})
# open_tickets[user_id_str][mode] = channel_id

cooldowns: Dict[str, Dict[str, int]] = _load_json(COOLDOWNS_FILE, {})
# cooldowns[user_id_str][mode] = unix_timestamp_when_closed

def _now() -> int:
    return int(time.time())

def _user_has_any_role(member: discord.Member, role_ids: List[int]) -> bool:
    s = set(role_ids)
    return any(r.id in s for r in member.roles)

# =========================
# HELPERS: WEB API (aiohttp nincs kell, discord.py hozza az aiohttp-ot)
# =========================
async def web_get_json(url: str) -> Tuple[int, Any]:
    # discord.py dependency: aiohttp
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                txt = await resp.text()
                try:
                    return resp.status, json.loads(txt)
                except Exception:
                    return resp.status, {"raw": txt}
    except Exception as e:
        return 0, {"error": str(e)}

async def web_post_json(url: str, payload: dict) -> Tuple[int, Any]:
    import aiohttp
    headers = {}
    if BOT_API_KEY:
        headers["x-api-key"] = BOT_API_KEY

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                txt = await resp.text()
                try:
                    return resp.status, json.loads(txt)
                except Exception:
                    return resp.status, {"raw": txt}
    except Exception as e:
        return 0, {"error": str(e)}

async def get_previous_rank_from_web(username: str, mode: str) -> str:
    # GET /api/tests?username=... (a route.js-ben támogatjuk)
    q = f"{WEBSITE_BASE_URL}/api/tests?username={username}"
    status, data = await web_get_json(q)
    if status != 200 or not isinstance(data, dict):
        return "Unranked"

    tests = data.get("tests", [])
    if not isinstance(tests, list):
        return "Unranked"

    # keressük az adott mode-ot
    for t in tests:
        if not isinstance(t, dict):
            continue
        if str(t.get("mode", "")).lower() == mode.lower():
            r = str(t.get("rank", "Unranked"))
            return r if r in RANKS else "Unranked"

    return "Unranked"

# =========================
# DISCORD BOT SETUP
# =========================
intents = discord.Intents.default()
intents.guilds = True
intents.members = True  # kell a role checkhez / ticket permshez

bot = commands.Bot(command_prefix="!", intents=intents)

GUILD_OBJECT = discord.Object(id=GUILD_ID)

# =========================
# UI: Ticket panel
# =========================
def sanitize_channel_name(s: str) -> str:
    s = s.lower().replace(" ", "-")
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789-"
    s = "".join(ch for ch in s if ch in allowed)
    return s[:90] if s else "ticket"

class CloseTicketView(discord.ui.View):
    def __init__(self, owner_id: int, mode: str):
        super().__init__(timeout=None)
        self.owner_id = owner_id
        self.mode = mode

    @discord.ui.button(label="Ticket zárása", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if interaction.guild is None or interaction.channel is None:
                return

            member = interaction.user
            if not isinstance(member, discord.Member):
                await interaction.response.send_message("Hiba: nem vagy szerver tagként felismerve.", ephemeral=True)
                return

            # csak tulaj vagy staff zárhatja
            is_owner = (member.id == self.owner_id)
            is_staff = _user_has_any_role(member, [STAFF_ROLE_ID])
            if not (is_owner or is_staff):
                await interaction.response.send_message("Nincs jogod lezárni ezt a ticketet.", ephemeral=True)
                return

            await interaction.response.send_message("✅ Ticket lezárása... (3 mp)", ephemeral=True)

            # cooldown beállítás
            uid = str(self.owner_id)
            cooldowns.setdefault(uid, {})
            cooldowns[uid][self.mode] = _now()
            _save_json(COOLDOWNS_FILE, cooldowns)

            # open ticket törlés
            uid2 = str(self.owner_id)
            if uid2 in open_tickets and self.mode in open_tickets[uid2]:
                del open_tickets[uid2][self.mode]
                if not open_tickets[uid2]:
                    del open_tickets[uid2]
                _save_json(OPEN_TICKETS_FILE, open_tickets)

            # csatorna törlése
            await asyncio.sleep(3)
            try:
                await interaction.channel.delete(reason="Ticket closed")
            except discord.Forbidden:
                # ha nem tud törölni, legalább jelezzük
                # (ide már nem tudunk írni a törölt/nem törölt csatornába biztosan, de megpróbáljuk)
                try:
                    await interaction.followup.send("❌ Nem tudtam törölni a csatornát (Missing Permissions).", ephemeral=True)
                except Exception:
                    pass
            except Exception:
                pass

        except Exception as e:
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(f"❌ Hiba: {e}", ephemeral=True)
                else:
                    await interaction.response.send_message(f"❌ Hiba: {e}", ephemeral=True)
            except Exception:
                pass

class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        # 5 gomb / sor limit, szóval több sorba pakoljuk
        row = 0
        col = 0
        for mode in GAMEMODES:
            if col >= 5:
                row += 1
                col = 0
            self.add_item(TicketButton(mode=mode, row=row))
            col += 1

class TicketButton(discord.ui.Button):
    def __init__(self, mode: str, row: int = 0):
        super().__init__(label=mode, style=discord.ButtonStyle.primary, row=row)
        self.mode = mode

    async def callback(self, interaction: discord.Interaction):
        try:
            # gyors válasz, hogy ne legyen "Az alkalmazás nem válaszolt"
            await interaction.response.defer(ephemeral=True, thinking=False)

            guild = interaction.guild
            if guild is None:
                await interaction.followup.send("Hiba: csak szerveren használható.", ephemeral=True)
                return

            member = interaction.user
            if not isinstance(member, discord.Member):
                await interaction.followup.send("Hiba: nem vagy szerver tagként felismerve.", ephemeral=True)
                return

            # 1) ugyanabból a MODE-ból ne lehessen 2 ticket egyszerre
            uid = str(member.id)
            if uid in open_tickets and self.mode in open_tickets[uid]:
                ch_id = open_tickets[uid][self.mode]
                ch = guild.get_channel(ch_id)
                if ch is not None:
                    await interaction.followup.send(f"Van már **{self.mode}** ticketed: {ch.mention}", ephemeral=True)
                    return
                else:
                    # csatorna már nem létezik → töröljük a nyilvántartást
                    del open_tickets[uid][self.mode]
                    if not open_tickets[uid]:
                        del open_tickets[uid]
                    _save_json(OPEN_TICKETS_FILE, open_tickets)

            # 2) 14 nap cooldown ugyanarra a MODE-ra
            last = cooldowns.get(uid, {}).get(self.mode, 0)
            if last:
                remaining = (last + TICKET_COOLDOWN_SECONDS) - _now()
                if remaining > 0:
                    days = remaining // 86400
                    hours = (remaining % 86400) // 3600
                    await interaction.followup.send(
                        f"⏳ **{self.mode}** ticket cooldown aktív.\nMég: **{days} nap {hours} óra**",
                        ephemeral=True
                    )
                    return

            # category
            category = guild.get_channel(TICKET_CATEGORY_ID)
            if not isinstance(category, discord.CategoryChannel):
                await interaction.followup.send("❌ Ticket kategória rossz / nem találom.", ephemeral=True)
                return

            staff_role = guild.get_role(STAFF_ROLE_ID)
            if staff_role is None:
                await interaction.followup.send("❌ STAFF_ROLE_ID rossz / nem találom.", ephemeral=True)
                return

            # ping role (mode-specific), ha nincs akkor staff role ping
            ping_role_id = PING_ROLE_BY_MODE.get(self.mode, STAFF_ROLE_ID)
            ping_role = guild.get_role(ping_role_id) or staff_role

            # csatorna létrehozás
            ch_name = sanitize_channel_name(f"{self.mode}-{member.name}")
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                member: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True,
                ),
                staff_role: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_messages=True,
                ),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_channels=True,
                    manage_messages=True,
                ) if guild.me else None
            }
            overwrites = {k: v for k, v in overwrites.items() if v is not None}

            channel = await guild.create_text_channel(
                name=ch_name,
                category=category,
                overwrites=overwrites,
                reason="Ticket created"
            )

            # nyilvántartás
            open_tickets.setdefault(uid, {})
            open_tickets[uid][self.mode] = channel.id
            _save_json(OPEN_TICKETS_FILE, open_tickets)

            # ticket üzenet
            await channel.send(
                content=f"{ping_role.mention}\n🎫 **Teszt kérés – {self.mode}**\nKérlek írd le mit szeretnél tesztelni!",
                view=CloseTicketView(owner_id=member.id, mode=self.mode)
            )

            await interaction.followup.send(f"✅ Ticket létrehozva: {channel.mention}", ephemeral=True)

        except discord.Forbidden:
            try:
                await interaction.followup.send(
                    "❌ Missing Permissions. A botnak kell: **Manage Channels**, **View Channels**, **Send Messages**.",
                    ephemeral=True
                )
            except Exception:
                pass
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ Hiba: {e}", ephemeral=True)
            except Exception:
                pass

# =========================
# COMMANDS
# =========================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id={bot.user.id})")

    try:
        # guild-only sync gyorsabb
        bot.tree.copy_global_to(guild=GUILD_OBJECT)
        await bot.tree.sync(guild=GUILD_OBJECT)
        print(f"Slash commands synced to guild {GUILD_ID}")
    except Exception as e:
        print("Sync error:", e)

def make_skin_url(username: str) -> str:
    # Minecraft skin head/face (overlay)
    safe = username.strip()
    return f"https://crafatar.com/avatars/{safe}?overlay=true&size=160"

def rank_hu_label(rank: str) -> str:
    # Discord embedben maradjon rövid (LT3/HT2), nem "Alacsony Tier 3"
    return rank

@app_commands.command(name="ticketpanel", description="Teszt ticket panel kiírása (gombokkal).")
async def ticketpanel(interaction: discord.Interaction):
    try:
        await interaction.response.send_message(
            "🎫 **Teszt kérés**\nKattints egy gombra, hogy ticketet nyiss a megfelelő játékmódból.",
            view=TicketPanelView(),
        )
    except Exception as e:
        # ha itt hiba van és nincs válasz: "Az alkalmazás nem válaszolt"
        try:
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ Hiba: {e}", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Hiba: {e}", ephemeral=True)
        except Exception:
            pass

bot.tree.add_command(ticketpanel, guild=GUILD_OBJECT)

@app_commands.choices(
    gamemode=[app_commands.Choice(name=m, value=m) for m in GAMEMODES],
    rank=[app_commands.Choice(name=r, value=r) for r in RANKS],
)
@app_commands.command(
    name="testresult",
    description="Teszt eredmény rögzítése + weboldal frissítése (NeonTiers)."
)
@app_commands.describe(
    username="Minecraft név (ebből lesz a skin a weboldalon)",
    tester="Ki tesztelte? (Discord tag)",
    gamemode="Játékmód",
    rank="Elért tier (LT/HT)"
)
async def testresult(
    interaction: discord.Interaction,
    username: str,
    tester: discord.Member,
    gamemode: app_commands.Choice[str],
    rank: app_commands.Choice[str],
):
    # permission
    if interaction.guild is None or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("Ez csak szerveren használható.", ephemeral=True)
        return

    caller: discord.Member = interaction.user
    if not _user_has_any_role(caller, ALLOWED_TESTER_ROLE_IDS):
        await interaction.response.send_message("Nincs jogosultságod ehhez a parancshoz.", ephemeral=True)
        return

    # hogy biztos ne timeoutoljon
    await interaction.response.defer(ephemeral=True)

    mc_name = username.strip()
    mode = gamemode.value
    new_rank = rank.value

    # előző rank lekérés webből
    prev_rank = await get_previous_rank_from_web(mc_name, mode)
    if prev_rank not in RANKS:
        prev_rank = "Unranked"

    # pont: az új rank pontja (felülírja a régit a weboldalon)
    points = RANK_POINTS.get(new_rank, 0)

    # web mentés (UP SERT: username+mode felülír)
    payload = {
        "username": mc_name,
        "mode": mode,
        "rank": new_rank,
        "points": points,
        "testerId": str(tester.id),
        "testerTag": str(tester),
        "timestamp": int(time.time()),
        "previousRank": prev_rank,
    }

    status, data = await web_post_json(f"{WEBSITE_BASE_URL}/api/tests", payload)

    # 1) Ephemeral visszajelzés
    if status == 200:
        await interaction.followup.send(
            f"✅ Mentve + weboldal frissítve.\nElőző: **{prev_rank}** → Elért: **{new_rank}** | **+{points} pont**",
            ephemeral=True
        )
    else:
        await interaction.followup.send(
            f"⚠️ Mentés hiba a weboldal felé (status {status}).\n{data}",
            ephemeral=True
        )

    # 2) A KÉRT “RENDES” EMBED a csatornába
    try:
        embed = discord.Embed(
            title=f"{mc_name} teszt eredménye 🏆",
            color=discord.Color.from_rgb(180, 0, 0),
        )
        embed.add_field(name="Tesztelő:", value=tester.mention, inline=False)
        embed.add_field(name="Játékmód:", value=mode, inline=False)
        embed.add_field(name="Minecraft név:", value=mc_name, inline=False)
        embed.add_field(name="Előző rang:", value=rank_hu_label(prev_rank), inline=False)
        embed.add_field(name="Elért rang:", value=rank_hu_label(new_rank), inline=False)

        embed.set_thumbnail(url=make_skin_url(mc_name))

        # küldés a csatornába
        if interaction.channel:
            await interaction.channel.send(embed=embed)
    except Exception:
        pass

bot.tree.add_command(testresult, guild=GUILD_OBJECT)

# =========================
# RUN
# =========================
if not DISCORD_TOKEN:
    raise RuntimeError("Missing DISCORD_TOKEN env var.")

bot.run(DISCORD_TOKEN)
