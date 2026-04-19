import os
import asyncio

# Import discord for bot setup FIRST (before other modules that need bot)
import discord
from discord import app_commands
from discord.ext import commands

# =========================
# DISCORD BOT
# =========================
intents = discord.Intents.default()
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
http_session = None

# NOW import our refactored modules (they use 'bot' defined above)
from shared_utils import *
from core_testing import *
from misc_features import *

# Register bot reference in modules that need it
from core_testing import set_bot
set_bot(bot)

# =========================
# HEALTH SERVER (Railway)
# =========================
from aiohttp import web

async def start_health_server():
    app = web.Application()

    async def health(_request):
        return web.Response(text="ok")

    # API endpoint for Minecraft link code verification
    async def verify_link(request):
        # Skip auth check entirely for now - allow all requests

        # Get code from query params
        code = request.query.get("code", "")
        minecraft_name = request.query.get("minecraft", "")

        if not code or not minecraft_name:
            return web.json_response({"success": False, "error": "Missing code or minecraft parameter"}, status=400)

        # Verify the code
        discord_id = await verify_link_code_async(code.upper())

        if discord_id is None:
            return web.json_response({"success": False, "error": "Invalid or expired code"}, status=400)

        # Link the Minecraft account to the Discord account
        await link_minecraft_account_async(discord_id, minecraft_name)

        # Send confirmation DM to the user
        try:
            user = await bot.fetch_user(discord_id)
            if user:
                # April Fools' funny link confirmation
                if APRIL_FOOLS_MODE:
                    funny_titles = [
                        "🎪 Cirkuszi összekapcsolás sikeres!",
                        "🤡 Bohóc összekapcsolás sikeres!",
                        "🎭 Színházi összekapcsolás sikeres!",
                        "🃏 Kártya összekapcsolás sikeres!",
                    ]
                    title = random.choice(funny_titles)
                else:
                    title = "✅ Összekapcsolás sikeres!"
                funny_footer = "Most már használhatod a tierlistát!"

                embed = discord.Embed(
                    title=title,
                    description=f"A Discord fiókod össze lett kapcsolva a **Minecraft** fiókkal!\n\n"
                                f"**Minecraft név:** `{minecraft_name}`\n"
                                f"**Összekapcsolva:** Örökre!",
                    color=discord.Color.green()
                )
                embed.set_footer(text=funny_footer)
                await user.send(embed=embed)
        except Exception as e:
            print(f"Could not send DM to user: {e}")

        return web.json_response({
            "success": True,
            "discord_id": discord_id,
            "minecraft": minecraft_name
        })

    app.router.add_get("/health", health)
    app.router.add_get("/api/link/verify", verify_link)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.getenv("PORT", "8080"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Health server running on :{port}")


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


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    try:
        # April Fools' funny error messages
        funny_errors = [
            "🤡 A bot ma részeg, próbáld újra!",
            "🎪 A cirkusz összeomlott!",
            "🎭 Ez egy áprilisi tréfa volt!",
            "🃏 A kártyák összekeveredtek!",
            "🤡 A bohóc elfelejtette a parancsot!",
            "🎪 Az elefánt rálépett a kódra!",
            "🎭 A színész elfelejtette a szöveget!",
            "🃏 A mágus eltüntette a parancsot!",
        ]

        if APRIL_FOOLS_MODE:
            error_msg = random.choice(funny_errors)
        else:
            error_msg = f"❌ Parancs hiba: {type(error).__name__}: {error}"

        # If already responded, use followup, else normal response
        if interaction.response.is_done():
            await interaction.followup.send(error_msg, ephemeral=True)
        else:
            await interaction.response.send_message(error_msg, ephemeral=True)
    except Exception:
        pass


async def main():
    global http_session

    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN is missing")

    # Initialize database
    await init_db()

    http_session = aiohttp.ClientSession()

    # health server
    asyncio.create_task(start_health_server())

    # queue maintenance task
    asyncio.create_task(queue_maintenance_task())

    # register commands - Use guild commands only (faster sync, avoids duplicates)
    if GUILD_ID:
        g = discord.Object(id=GUILD_ID)
        # Commands are now registered in their respective modules
    else:
        # Only register as global if no GUILD_ID
        # Commands are now registered in their respective modules
        pass

    try:
        await bot.start(DISCORD_TOKEN)
    finally:
        if http_session:
            await http_session.close()
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())