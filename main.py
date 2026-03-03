import os
import json
import time
import asyncio
from typing import Dict, Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

import aiohttp
from aiohttp import web

# =========================
# ENV / CONFIG
# =========================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
STAFF_ROLE_ID = int(os.getenv("STAFF_ROLE_ID", "0"))
TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID", "0"))

WEBSITE_URL = os.getenv("WEBSITE_URL", "").rstrip("/")  # e.g. https://neontiers.vercel.app
BOT_API_KEY = os.getenv("BOT_API_KEY", "")              # shared secret between bot and website

WIPE_GLOBAL_COMMANDS = os.getenv("WIPE_GLOBAL_COMMANDS", "0") == "1"

COOLDOWN_SECONDS = 14 * 24 * 60 * 60
DATA_FILE = "data.json"

HTTP_TIMEOUT_SECONDS = 10  # hard timeout so it never "thinks forever"


# =========================
# CONSTANTS
# =========================
TICKET_TYPES = [
    ("Vanilla", "vanilla", 1469763891226480926),
    ("UHC", "uhc", 1469765994988704030),
    ("Pot", "pot", 1469763780593324032),
    ("NethPot", "nethpot", 1469763817218117697),
    ("SMP", "smp", 1469764274955223161),
    ("Sword", "sword", 1469763677141074125),
    ("Axe", "axe", 1469763738889486518),
    ("Mace", "mace", 1469763612452196375),
    ("Cart", "cart", 1469763920871952435),
    ("Creeper", "creeper", 1469764200812249180),
    ("DiaSMP", "diasmp", 1469763946968911893),
    ("OGVanilla", "ogvanilla", 1469764329460203571),
    ("ShieldlessUHC", "shieldlessuhc", 1469766017243807865),
    ("SpearMace", "spearmace", 1469968704203788425),
    ("SpearElytra", "spearelytra", 1469968762575912970),
]

MODE_LIST = [t[0] for t in TICKET_TYPES]

RANKS = [
    "Unranked",
    "LT5", "HT5",
    "LT4", "HT4",
    "LT3", "HT3",
    "LT2", "HT2",
    "LT1", "HT1",
]

POINTS = {
    "Unranked": 0,
    "LT5": 1, "HT5": 2,
    "LT4": 3, "HT4": 4,
    "LT3": 5, "HT3": 6,
    "LT2": 7, "HT2": 8,
    "LT1": 9, "HT1": 10,
}


# =========================
# STORAGE
# =========================
def _load_data() -> Dict[str, Any]:
    if not os.path.exists(DATA_FILE):
        return {"ticket_state": {}, "cooldowns": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"ticket_state": {}, "cooldowns": {}}


def _save_data(data: Dict[str, Any]) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_open_ticket_channel_id(user_id: int, mode_key: str) -> Optional[int]:
    data = _load_data()
    return data.get("ticket_state", {}).get(str(user_id), {}).get(mode_key)


def set_open_ticket_channel_id(user_id: int, mode_key: str, channel_id: Optional[int]) -> None:
    data = _load_data()
    ticket_state = data.setdefault("ticket_state", {})
    user_state = ticket_state.setdefault(str(user_id), {})
    if channel_id is None:
        user_state.pop(mode_key, None)
    else:
        user_state[mode_key] = channel_id
    _save_data(data)


def get_last_closed(user_id: int, mode_key: str) -> float:
    data = _load_data()
    return float(data.get("cooldowns", {}).get(str(user_id), {}).get(mode_key, 0))


def set_last_closed(user_id: int, mode_key: str, ts: float) -> None:
    data = _load_data()
    cds = data.setdefault("cooldowns", {})
    u = cds.setdefault(str(user_id), {})
    u[mode_key] = ts
    _save_data(data)


def cooldown_left(user_id: int, mode_key: str) -> int:
    last = get_last_closed(user_id, mode_key)
    if last <= 0:
        return 0
    left = int((last + COOLDOWN_SECONDS) - time.time())
    return max(0, left)


# =========================
# PERMISSIONS
# =========================
def is_staff_member(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    if STAFF_ROLE_ID and any(r.id == STAFF_ROLE_ID for r in member.roles):
        return True
    return False


# =========================
# DISCORD BOT
# =========================
intents = discord.Intents.default()
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
http_session: Optional[aiohttp.ClientSession] = None


# =========================
# HEALTH SERVER (Railway)
# =========================
async def start_health_server():
    app = web.Application()

    async def health(_request):
        return web.Response(text="ok")

    app.router.add_get("/health", health)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.getenv("PORT", "8080"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Health server running on :{port}")


# =========================
# WEBSITE API
# =========================
def _auth_headers() -> Dict[str, str]:
    if not BOT_API_KEY:
        return {}
    return {"Authorization": f"Bearer {BOT_API_KEY}"}


async def api_get_tests(username: str, mode: str) -> Dict[str, Any]:
    if not WEBSITE_URL:
        return {"status": 0, "data": {"tests": []}}

    url = f"{WEBSITE_URL}/api/tests?username={username}&mode={mode}"

    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
    async with http_session.get(url, headers=_auth_headers(), timeout=timeout) as resp:
        try:
            data = await resp.json()
        except Exception:
            data = {"error": await resp.text()}
        return {"status": resp.status, "data": data}


async def api_post_test(username: str, mode: str, rank: str, tester: discord.Member) -> Dict[str, Any]:
    if not WEBSITE_URL:
        return {"status": 0, "data": {"error": "WEBSITE_URL not set"}}

    url = f"{WEBSITE_URL}/api/tests"
    payload = {
        "username": username,
        "mode": mode,
        "rank": rank,
        "testerId": str(tester.id),
        "testerName": tester.display_name,
        "upsert": True,
        "ts": int(time.time()),
    }

    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
    async with http_session.post(url, json=payload, headers=_auth_headers(), timeout=timeout) as resp:
        try:
            data = await resp.json()
        except Exception:
            data = {"error": await resp.text()}
        return {"status": resp.status, "data": data}


async def api_rename_player(old_name: str, new_name: str) -> Dict[str, Any]:
    """Rename a player on the tierlist (admin only)"""
    if not WEBSITE_URL:
        return {"status": 0, "data": {"error": "WEBSITE_URL not set"}}

    # Use /api/tests/rename endpoint with POST method
    url = f"{WEBSITE_URL}/api/tests/rename"
    payload = {
        "oldName": old_name,
        "newName": new_name,
    }

    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
    async with http_session.post(url, json=payload, headers=_auth_headers(), timeout=timeout) as resp:
        try:
            data = await resp.json()
        except Exception:
            data = {"error": await resp.text()}
        return {"status": resp.status, "data": data}


# =========================
# UI VIEWS
# =========================
class CloseTicketView(discord.ui.View):
    def __init__(self, owner_id: int, mode_key: str):
        super().__init__(timeout=None)
        self.owner_id = owner_id
        self.mode_key = mode_key

    @discord.ui.button(label="Ticket zárása", style=discord.ButtonStyle.danger, custom_id="neotiers_close_ticket")
    async def close(self, interaction: discord.Interaction, _button: discord.ui.Button):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("Hiba: ez nem szövegcsatorna.", ephemeral=True)
            return

        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("Hiba: member not found.", ephemeral=True)
            return

        if member.id != self.owner_id and not is_staff_member(member):
            await interaction.response.send_message("Nincs jogosultságod a ticket zárásához.", ephemeral=True)
            return

        await interaction.response.send_message("✅ Ticket zárása... 3 mp múlva törlöm a csatornát.", ephemeral=True)

        set_last_closed(self.owner_id, self.mode_key, time.time())
        set_open_ticket_channel_id(self.owner_id, self.mode_key, None)

        await asyncio.sleep(3)
        try:
            await channel.delete(reason="NeoTiers ticket closed")
        except discord.Forbidden:
            try:
                await channel.send("❌ Nem tudom törölni a csatornát (Missing Permissions). Add a botnak **Csatornák kezelése** jogot + a kategórián is.")
            except Exception:
                pass
        except Exception:
            pass


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for label, mode_key, _rid in TICKET_TYPES:
            self.add_item(TicketButton(label=label, mode_key=mode_key))


class TicketButton(discord.ui.Button):
    def __init__(self, label: str, mode_key: str):
        super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id=f"neotiers_ticket_{mode_key}")
        self.mode_key = mode_key

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        member = interaction.user

        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message("Hiba: guild/member nem elérhető.", ephemeral=True)
            return

        left = cooldown_left(member.id, self.mode_key)
        if left > 0:
            days = left // (24 * 3600)
            hours = (left % (24 * 3600)) // 3600
            await interaction.response.send_message(
                f"⏳ **Cooldown**: ebből a játékmódból ({self.mode_key}) csak **{days} nap {hours} óra** múlva nyithatsz új ticketet.",
                ephemeral=True
            )
            return

        existing_channel_id = get_open_ticket_channel_id(member.id, self.mode_key)
        if existing_channel_id:
            ch = guild.get_channel(existing_channel_id)
            if ch:
                await interaction.response.send_message("Van már ticketed ebből a játékmódból. 🔒", ephemeral=True)
                return
            else:
                set_open_ticket_channel_id(member.id, self.mode_key, None)

        category = guild.get_channel(TICKET_CATEGORY_ID) if TICKET_CATEGORY_ID else None
        if TICKET_CATEGORY_ID and not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(
                "❌ Ticket kategória rossz / nem kategória. Állítsd be jól a TICKET_CATEGORY_ID-t.",
                ephemeral=True
            )
            return

        staff_role = guild.get_role(STAFF_ROLE_ID) if STAFF_ROLE_ID else None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True, manage_channels=True
            )

        safe_name = member.name.lower().replace(" ", "-")
        channel_name = f"{self.mode_key}-{safe_name}"

        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category if isinstance(category, discord.CategoryChannel) else None,
                overwrites=overwrites,
                topic=f"NeoTiers ticket | owner={member.id} | mode={self.mode_key}",
                reason="NeoTiers ticket created"
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Nincs jogom csatornát létrehozni. Add a botnak **Csatornák kezelése** jogot (és a kategórián is).",
                ephemeral=True
            )
            return

        set_open_ticket_channel_id(member.id, self.mode_key, channel.id)

        ping_role_id = None
        for _label, mk, rid in TICKET_TYPES:
            if mk == self.mode_key:
                ping_role_id = rid
                break

        ping_text = f"<@&{ping_role_id}>" if ping_role_id else ""

        embed = discord.Embed(
            title="Teszt kérés",
            description="Kattints egy alábbi gombra, hogy tudd tesztelni a gombon feltüntetett játékmódból.",
            color=discord.Color.blurple()
        )
        embed.add_field(name="Játékmód", value=self.mode_key, inline=True)
        embed.add_field(name="Játékos", value=member.mention, inline=True)

        await channel.send(content=ping_text, embed=embed, view=CloseTicketView(owner_id=member.id, mode_key=self.mode_key))
        await interaction.response.send_message(f"✅ Ticket létrehozva: {channel.mention}", ephemeral=True)


# =========================
# COMMANDS
# =========================
def _choices_from_list(values):
    return [app_commands.Choice(name=v, value=v) for v in values]


@app_commands.command(name="ticketpanel", description="Ticket panel üzenet kirakása.")
async def ticketpanel(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    try:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("Hiba.", ephemeral=True)
            return
        if not is_staff_member(interaction.user):
            await interaction.followup.send("Nincs jogosultságod.", ephemeral=True)
            return
        if interaction.channel is None:
            await interaction.followup.send("Hiba: nincs csatorna.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Teszt kérés",
            description="Kattints egy alábbi gombra, hogy tudd tesztelni a gombon feltüntetett játékmódból.",
            color=discord.Color.blurple()
        )

        await interaction.channel.send(embed=embed, view=TicketPanelView())
        await interaction.followup.send("✅ Ticket panel kirakva.", ephemeral=True)

    except discord.Forbidden:
        await interaction.followup.send("❌ Nem tudok ide írni (Missing Permissions). Adj írás jogot a botnak ebben a csatornában.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


@app_commands.command(name="testresult", description="Minecraft tier teszt eredmény embed + weboldal mentés.")
@app_commands.describe(
    username="Minecraft név (ebből lesz a skin a weboldalon)",
    tester="Tesztelő (Discord user)",
    gamemode="Játékmód",
    rank="Elért rank (pl. LT3 / HT3)"
)
@app_commands.choices(
    gamemode=_choices_from_list(MODE_LIST),
    rank=_choices_from_list(RANKS)
)
async def testresult(
    interaction: discord.Interaction,
    username: str,
    tester: discord.Member,
    gamemode: app_commands.Choice[str],
    rank: app_commands.Choice[str],
):
    await interaction.response.defer(ephemeral=True)

    try:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("Hiba.", ephemeral=True)
            return
        if not is_staff_member(interaction.user):
            await interaction.followup.send("Nincs jogosultságod ehhez a parancshoz.", ephemeral=True)
            return
        if interaction.channel is None:
            await interaction.followup.send("Hiba: nincs csatorna.", ephemeral=True)
            return

        mode_val = gamemode.value
        rank_val = rank.value

        # Previous rank from website (best-effort)
        prev_rank = "Unranked"
        if WEBSITE_URL:
            try:
                res = await api_get_tests(username=username, mode=mode_val)
                if res.get("status") == 200:
                    tests = res["data"].get("tests", [])
                    if isinstance(tests, list) and tests:
                        # pick first match if returned
                        for t in tests:
                            if str(t.get("mode", "")).lower() == mode_val.lower() and str(t.get("username", "")).lower() == username.lower():
                                prev_rank = str(t.get("rank", "Unranked")) or "Unranked"
                                break
            except Exception:
                pass

        prev_points = POINTS.get(prev_rank, 0)
        new_points = POINTS.get(rank_val, 0)
        diff = new_points - prev_points

        # PUBLIC EMBED (everyone sees)
        skin_url = f"https://minotar.net/helm/{username}/128.png"
        embed = discord.Embed(
            title=f"{username} teszt eredménye 🏆",
            color=discord.Color.dark_grey()
        )
        embed.set_thumbnail(url=skin_url)
        embed.add_field(name="Tesztelő:", value=tester.mention, inline=False)
        embed.add_field(name="Játékmód:", value=mode_val, inline=False)
        embed.add_field(name="Minecraft név:", value=username, inline=False)
        embed.add_field(name="Előző rang:", value=prev_rank, inline=False)
        embed.add_field(name="Elért rang:", value=rank_val, inline=False)

        await interaction.channel.send(embed=embed)

        # SAVE TO WEBSITE (UPsert)
        if not WEBSITE_URL:
            await interaction.followup.send("⚠️ WEBSITE_URL nincs beállítva, nem mentem webre.", ephemeral=True)
            return

        save = await api_post_test(username=username, mode=mode_val, rank=rank_val, tester=tester)
        save_status = save.get("status")
        save_data = save.get("data")
        save_ok = (save_status == 200 or save_status == 201)

        if save_ok:
            await interaction.followup.send(
                f"✅ Mentve + weboldal frissítve.\nElőző: **{prev_rank}** → Elért: **{rank_val}** | "
                f"{'+' if diff>=0 else ''}{diff} pont",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"⚠️ Mentés hiba a weboldal felé (status {save_status}) | {save_data}",
                ephemeral=True
            )

    except aiohttp.ClientError as e:
        await interaction.followup.send(f"⚠️ Web hiba: {type(e).__name__}: {e}", ephemeral=True)
    except asyncio.TimeoutError:
        await interaction.followup.send("⚠️ Web timeout (nem válaszolt 10 mp-en belül).", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ Nem tudok ide írni / embedet küldeni (Missing Permissions).", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


@app_commands.command(name="tierlistnamechange", description="Játékos nevének megváltoztatása a tierlistán (admin csak)")
@app_commands.describe(
    oldname="A jelenlegi név a tierlistán",
    newname="Az új név ami megjelenik a tierlistán"
)
async def tierlistnamechange(interaction: discord.Interaction, oldname: str, newname: str):
    await interaction.response.defer(ephemeral=True)

    try:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("Hiba.", ephemeral=True)
            return
        if not is_staff_member(interaction.user):
            await interaction.followup.send("Nincs jogosultságod ehhez a parancshoz.", ephemeral=True)
            return

        # Call the website API to rename the player
        if not WEBSITE_URL:
            await interaction.followup.send("⚠️ WEBSITE_URL nincs beállítva.", ephemeral=True)
            return

        result = await api_rename_player(old_name=oldname, new_name=newname)
        status = result.get("status")
        data = result.get("data", {})

        if status == 200:
            updated_count = data.get("updatedCount", 0)
            await interaction.followup.send(
                f"✅ Sikeresen átnevezve: **{oldname}** → **{newname}**\n"
                f"Frissítve: {updated_count} db bejegyzés (összes gamemód)",
                ephemeral=True
            )
        elif status == 404:
            await interaction.followup.send(
                f"❌ Játékos nem találva: **{oldname}**",
                ephemeral=True
            )
        elif status == 401 or status == 403:
            await interaction.followup.send(
                "❌ Nincs jogosultságod ehhez a parancshoz.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"⚠️ Hiba (status {status}): {data}",
                ephemeral=True
            )

    except aiohttp.ClientError as e:
        await interaction.followup.send(f"⚠️ Web hiba: {type(e).__name__}: {e}", ephemeral=True)
    except asyncio.TimeoutError:
        await interaction.followup.send("⚠️ Web timeout (nem válaszolt 10 mp-en belül).", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


@app_commands.command(name="profile", description="Megnézed egy játékos tierjeit a tierlistáról.")
@app_commands.describe(
    name="A játékos neve a tierlistán"
)
async def profile(interaction: discord.Interaction, name: str):
    await interaction.response.defer(ephemeral=False)

    try:
        if not WEBSITE_URL:
            await interaction.followup.send("⚠️ WEBSITE_URL nincs beállítva.", ephemeral=True)
            return

        # Use the new API endpoint that supports filtering by username only
        url = f"{WEBSITE_URL}/api/tests?username={name}"
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        async with http_session.get(url, headers=_auth_headers(), timeout=timeout) as resp:
            try:
                data = await resp.json()
            except Exception:
                data = {}

            if resp.status != 200:
                await interaction.followup.send(f"⚠️ Hiba a weboldal lekérésekor: {resp.status}", ephemeral=True)
                return

            tests = data.get("tests", [])

            if not tests:
                await interaction.followup.send(f"❌ Nincs találat erre a névre: **{name}**", ephemeral=False)
                return

            # Build embed
            embed = discord.Embed(
                title=f"{name} profilja",
                color=discord.Color.blurple()
            )

            # Sort by points (desc)
            tests.sort(key=lambda x: x.get("points", 0), reverse=True)

            # List modes
            mode_strs = []
            total_points = 0
            for t in tests:
                m = t.get("gamemode", "?")
                r = t.get("rank", "?")
                p = t.get("points", 0)
                total_points += p
                mode_strs.append(f"**{m}**: {r} ({p}pt)")

            embed.description = "\n".join(mode_strs)
            embed.add_field(name="Összes pont", value=str(total_points), inline=False)

            # Skin
            skin_url = f"https://minotar.net/helm/{name}/128.png"
            embed.set_thumbnail(url=skin_url)

            await interaction.followup.send(embed=embed)

    except aiohttp.ClientError as e:
        await interaction.followup.send(f"⚠️ Web hiba: {type(e).__name__}: {e}", ephemeral=True)
    except asyncio.TimeoutError:
        await interaction.followup.send("⚠️ Web timeout (nem válaszolt 10 mp-en belül).", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


# =========================
# GLOBAL APP COMMAND ERROR HANDLER
# =========================
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    try:
        # If already responded, use followup, else normal response
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ Parancs hiba: {type(error).__name__}: {error}", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Parancs hiba: {type(error).__name__}: {error}", ephemeral=True)
    except Exception:
        pass


# =========================
# SETUP / EVENTS
# =========================
async def wipe_global_commands_once():
    try:
        bot.tree.clear_commands(guild=None)
        await bot.tree.sync()
        print("Global commands wiped.")
    except Exception as e:
        print("Failed to wipe global commands:", e)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id={bot.user.id})")

    # persistent views
    bot.add_view(TicketPanelView())
    bot.add_view(CloseTicketView(owner_id=0, mode_key=""))

    guild = discord.Object(id=GUILD_ID) if GUILD_ID else None

    if WIPE_GLOBAL_COMMANDS:
        await wipe_global_commands_once()

    try:
        if guild:
            await bot.tree.sync(guild=guild)
            print(f"Slash commands synced to guild {GUILD_ID}")
        else:
            await bot.tree.sync()
            print("Slash commands synced globally (no GUILD_ID set).")
    except Exception as e:
        print("Sync failed:", e)


async def main():
    global http_session

    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN is missing")

    http_session = aiohttp.ClientSession()

    # health server
    asyncio.create_task(start_health_server())

    # register commands (guild-scoped for instant updates)
    if GUILD_ID:
        g = discord.Object(id=GUILD_ID)
        bot.tree.add_command(ticketpanel, guild=g)
        bot.tree.add_command(testresult, guild=g)
        bot.tree.add_command(tierlistnamechange, guild=g)
        bot.tree.add_command(profile, guild=g)
    else:
        bot.tree.add_command(ticketpanel)
        bot.tree.add_command(testresult)
        bot.tree.add_command(tierlistnamechange)
        bot.tree.add_command(profile)

    try:
        await bot.start(DISCORD_TOKEN)
    finally:
        if http_session:
            await http_session.close()


if __name__ == "__main__":
    asyncio.run(main())
