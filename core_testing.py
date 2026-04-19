import discord
from discord import app_commands
from discord.ext import commands

import time
from typing import Dict, Any, List

from shared_utils import *

# Bot reference - will be set from main.py
bot = None

def set_bot(bot_instance):
    global bot
    bot = bot_instance


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
        try:
            channel = interaction.channel
            if not isinstance(channel, discord.TextChannel):
                await interaction.response.send_message("❌ Hiba", ephemeral=True)
                return

            member = interaction.user
            topic = channel.topic or ""
            owner_id = 0
            if "owner=" in topic:
                try:
                    owner_id = int(topic.split("owner=")[1].split("|")[0].strip())
                except:
                    owner_id = 0

            if member.id != owner_id and not is_staff_member(member):
                await interaction.response.send_message("❌ Nincs jogod", ephemeral=True)
                return

            await interaction.response.send_message("✅ Ticket bezárva!", ephemeral=True)
            set_last_closed(owner_id, "", time.time())
            await asyncio.sleep(2)
            try:
                await channel.delete(reason="Ticket closed")
            except:
                pass
        except Exception as e:
            print(f"close ticket error: {e}")
            # Check if we already responded to avoid "Interaction already acknowledged"
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Hiba: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Hiba: {e}", ephemeral=True)

        # Get owner_id and mode_key from channel topic
        topic = channel.topic or ""
        owner_id = 0
        mode_key = ""
        if "owner=" in topic:
            try:
                owner_id = int(topic.split("owner=")[1].split("|")[0].strip())
            except (ValueError, IndexError):
                owner_id = 0
        if "mode=" in topic:
            try:
                mode_key = topic.split("mode=")[1].strip()
            except IndexError:
                mode_key = ""

        set_last_closed(owner_id, mode_key, time.time())
        set_open_ticket_channel_id(owner_id, mode_key, None)

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

    @discord.ui.button(label="Tier adása", style=discord.ButtonStyle.success, custom_id="neotiers_give_tier")
    async def give_tier(self, interaction: discord.Interaction, _button: discord.ui.Button):
        """Give tier to the ticket owner - only for staff"""
        if not is_staff_member(interaction.user):
            await interaction.response.send_message("❌ Nincs jogod", ephemeral=True)
            return
        await interaction.response.send_message("✅ Köszi! Tier adás kész.", ephemeral=True)
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("Hiba: ez nem szövegcsatorna.", ephemeral=True)
            return

        # Get owner_id and mode from channel topic
        topic = channel.topic or ""
        owner_id = 0
        mode_key = ""
        if "owner=" in topic:
            try:
                owner_id = int(topic.split("owner=")[1].split("|")[0].strip())
            except (ValueError, IndexError):
                owner_id = 0
        if "mode=" in topic:
            try:
                mode_key = topic.split("mode=")[1].split("|")[0].strip()
            except (ValueError, IndexError):
                mode_key = ""

        if owner_id == 0:
            await interaction.response.send_message("Hiba: nem találom a ticket tulajdonosát.", ephemeral=True)
            return

        # Get linked Minecraft name for the owner
        linked_minecraft = get_linked_minecraft_name(owner_id)
        if not linked_minecraft:
            await interaction.response.send_message("❌ A játékos nincs összekapcsolva! Nem tudom a Minecraft nevét.", ephemeral=True)
            return

        # Show a select menu for tier selection (including mode)
        tier_select = TierSelectView(owner_id, linked_minecraft, mode_key, member)
        await interaction.response.send_message("Válaszd ki a játékmódot és a tier-t:", view=tier_select, ephemeral=True)


class TierSelectView(discord.ui.View):
    def __init__(self, owner_id: int, linked_minecraft: str, mode_key: str, tester: discord.Member):
        super().__init__(timeout=60)
        self.owner_id = owner_id
        self.linked_minecraft = linked_minecraft
        self.mode_key = mode_key
        self.tester = tester
        # Find the mode label from TICKET_TYPES
        mode_label = mode_key
        for label, key, _rid in TICKET_TYPES:
            if key == mode_key:
                mode_label = label
                break
        self.mode_label = mode_label
        self.add_item(GameModeSelect(mode_label, mode_key))
        self.add_item(TierSelect())


class GameModeSelect(discord.ui.Select):
    def __init__(self, mode_label: str, mode_key: str):
        options = [discord.SelectOption(label=label, value=key) for label, key, _rid in TICKET_TYPES]
        super().__init__(placeholder="Játékmód...", options=options, custom_id="gamemode_select")
        self.mode_label = mode_label
        self._default_value = mode_key

    async def callback(self, interaction: discord.Interaction):
        try:
            # All code that might fail goes INSIDE the try block
            selected_tier = self.values[0]
            view = self.view
            owner_id = view.owner_id
            linked_minecraft = view.linked_minecraft
            tester = view.tester
            mode_key = view.mode_key
            mode_label = view.mode_label

            # Get the owner member
            owner_member = interaction.guild.get_member(owner_id)
            if not owner_member:
                await interaction.response.send_message("Hiba: nem találom a Discord felhasználót.", ephemeral=True)
                return

            # ... [The rest of your logic for calculating points and sending embeds] ...

            # Example success message
            await interaction.response.send_message(f"✅ Tier beállítva: **{selected_tier}**", ephemeral=True)

        except Exception as e:
            # THIS IS THE MISSING BLOCK causing the SyntaxError
            print(f"tier select error: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Hiba: {e}", ephemeral=True)


async def callback(self, interaction: discord.Interaction):
        try:
            # Everything below this must be indented 8 spaces (2 levels)
            selected_tier = self.values[0]
            view = self.view
            owner_id = view.owner_id
            linked_minecraft = view.linked_minecraft
            tester = view.tester
            mode_key = view.mode_key
            mode_label = view.mode_label

            owner_member = interaction.guild.get_member(owner_id)
            if not owner_member:
                await interaction.response.send_message("Hiba: nem találom a Discord felhasználót.", ephemeral=True)
                return

            # --- PREVIOUS RANK LOGIC ---
            prev_rank = "Unranked"
            prev_points = 0
            if WEBSITE_URL:
                try:
                    mode_param = normalize_gamemode(mode_key)
                    res = await api_get_tests(username=linked_minecraft, mode=mode_param)
                    if res.get("status") == 200:
                        data = res.get("data", {})
                        test = data.get("test")
                        tests = data.get("tests", [])
                        target = test if test else (tests[0] if tests else None)
                        if target:
                            prev_rank = str(target.get("rank", "Unranked")) or "Unranked"
                            prev_points = POINTS.get(prev_rank, 0)
                except Exception as e:
                    print(f"Error fetching previous rank: {e}")

            # --- EMBED CALCULATION ---
            new_points = POINTS.get(selected_tier, 0)
            diff = new_points - prev_points
            points_str = f"+{diff}" if diff > 0 else str(diff)
            if diff == 0: points_str = "±0"

            embed = discord.Embed(title=f"{linked_minecraft} teszt eredménye 🏆", color=discord.Color.dark_grey())
            embed.set_thumbnail(url=f"https://minotar.net/helm/{linked_minecraft}/128.png")
            embed.add_field(name="Tesztelő:", value=tester.mention, inline=False)
            embed.add_field(name="Játékmód:", value=mode_label, inline=False)
            embed.add_field(name="Elért rang:", value=f"{selected_tier} ({new_points} pont)", inline=False)
            embed.add_field(name="Pontok:", value=points_str, inline=False)

            # --- SEND RESULTS ---
            tier_channel = None
            tier_channel_id_str = os.getenv("TIER_RESULTS_CHANNEL_ID", "0")
            try:
                tier_channel_id = int(tier_channel_id_str)
                if tier_channel_id:
                    tier_channel = interaction.guild.get_channel(tier_channel_id)
            except:
                pass
            
            if not tier_channel:
                tier_channel = discord.utils.get(interaction.guild.text_channels, name="teszteredmenyek")

            if tier_channel:
                await tier_channel.send(embed=embed)

            # --- SAVE & COOLDOWN ---
            if WEBSITE_URL:
                mode_to_save = get_gamemode_display_name(mode_key)
                await api_post_test(username=linked_minecraft, mode=mode_to_save, rank=selected_tier, tester=tester)
            
            set_last_closed(owner_id, mode_key, time.time())
            await interaction.response.send_message(f"✅ Tier beállítva: **{selected_tier}**", ephemeral=True)

        except Exception as e:
            # This is the "except" block Python was looking for
            print(f"tier select error: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Hiba: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Hiba: {e}", ephemeral=True)

        # Calculate new points
        new_points = POINTS.get(selected_tier, 0)
        diff = new_points - prev_points
        points_str = f"+{diff}" if diff > 0 else str(diff)
        if diff == 0:
            points_str = "±0"

        # Create embed like /testresult
        skin_url = f"https://minotar.net/helm/{linked_minecraft}/128.png"

        # April Fools' effects
        display_mc = linked_minecraft
        display_mode = mode_label
        display_prev_rank = get_funny_rank(prev_rank) if APRIL_FOOLS_MODE else prev_rank
        display_selected_tier = get_funny_rank(selected_tier) if APRIL_FOOLS_MODE else selected_tier

        embed = discord.Embed(
            title=f"{display_mc} teszt eredménye 🏆",
            color=discord.Color.dark_grey()
        )
        embed.set_thumbnail(url=skin_url)
        embed.add_field(name="Tesztelő:", value=tester.mention, inline=False)
        embed.add_field(name="Játékmód:", value=display_mode, inline=False)
        embed.add_field(name="Minecraft név:", value=display_mc, inline=False)
        embed.add_field(name="Előző rang:", value=f"{display_prev_rank} ({prev_points} pont)", inline=False)
        embed.add_field(name="Elért rang:", value=f"{display_selected_tier} ({new_points} pont)", inline=False)
        embed.add_field(name="Pontok:", value=points_str, inline=False)

        # Add random April Fools' message
        if APRIL_FOOLS_MODE and random.random() < 0.3:
            embed.add_field(name="🎪 Áprilisi üzenet:", value=get_april_fools_message(), inline=False)

        # Send to the test results channel
        tier_channel_id_str = os.getenv("TIER_RESULTS_CHANNEL_ID", "0")
        print(f"DEBUG: TIER_RESULTS_CHANNEL_ID env var: {tier_channel_id_str}")

        tier_channel_id = 0
        try:
            tier_channel_id = int(tier_channel_id_str)
        except ValueError:
            print(f"DEBUG: Could not parse tier_channel_id: {tier_channel_id_str}")

        print(f"DEBUG: Parsed tier_channel_id: {tier_channel_id}")
        print(f"DEBUG: interaction.guild.id: {interaction.guild.id}")

        if not tier_channel_id:
            # Fallback: try to find channel by name
            tier_channel = discord.utils.get(interaction.guild.text_channels, name="teszteredmenyek")
            if not tier_channel:
                tier_channel = discord.utils.get(interaction.guild.text_channels, name="test-results")
                if not tier_channel:
                    tier_channel = discord.utils.get(interaction.guild.text_channels, name="eredmenyek")
        else:
            tier_channel = interaction.guild.get_channel(tier_channel_id)
            print(f"DEBUG: Got channel object: {tier_channel}")

        if tier_channel:
            print(f"DEBUG: Sending embed to channel: {tier_channel.name} ({tier_channel.id})")
            await tier_channel.send(embed=embed)
        else:
            # Log warning but continue with saving
            print(f"Warning: Could not find tier results channel. Searched for ID: {tier_channel_id}")

        # Save to website
        if WEBSITE_URL:
            try:
                # Normalize mode to proper display name before saving
                mode_to_save = get_gamemode_display_name(mode_key)
                save = await api_post_test(username=linked_minecraft, mode=mode_to_save, rank=selected_tier, tester=tester)
                save_ok = (save.get("status") == 200 or save.get("status") == 201)
                if save_ok:
                    # Set cooldown after successful save
                    set_last_closed(owner_id, mode_key, time.time())
                    await interaction.response.send_message(f"✅ Tier beállítva: **{selected_tier}** és mentve a weboldalra!", ephemeral=True)
                else:
                    await interaction.response.send_message(f"✅ Tier beállítva: **{selected_tier}** (weboldal mentés sikertelen)", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"✅ Tier beállítva: **{selected_tier}** (weboldal hiba: {e})", ephemeral=True)
        else:
            await interaction.response.send_message(f"✅ Tier beállítva: **{selected_tier}**", ephemeral=True)
            # Set cooldown even without website save
            set_last_closed(owner_id, mode_key, time.time())


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

        # Check if user has a linked Minecraft account
        linked_minecraft = get_linked_minecraft_name(member.id)
        if not linked_minecraft:
            await interaction.response.send_message(
                "❌ **Nincs összekapcsolva a Minecraft fiókod!**\n\n"
                "Használd a `/link` parancsot a Discordban, majd `/link <kód>` a Minecraftban, "
                "hogy összekapcsold a fiókodat. Csak azok hozhatnak létre ticketet, akik összekapcsolták a fiókjukat!",
                ephemeral=True
            )
            return

        # Check cooldown
        cd = cooldown_left(member.id, self.mode_key)
        if cd > 0:
            cd_display = format_cooldown(cd)
            await interaction.response.send_message(
                f"❌ Még nem tesztelhetsz! Várj: **{cd_display}**",
                ephemeral=True
            )
            return

        # April Fools' 5% chance to open ticket
        if APRIL_FOOLS_MODE:
            if random.random() > 0.05:  # 95% chance to fail
                funny_fail_messages = [
                    "🎪 A cirkusz ma zárva! Próbáld újra! 🎪",
                    "🤡 A bohóc elfelejtette a kulcsot! Próbáld újra! 🤡",
                    "🎭 A színház szünetel! Próbáld újra! 🎭",
                    "🃏 A kártyák összekeveredtek! Próbáld újra! 🃏",
                    "🎪 Az elefánt rálépett a jegyre! Próbáld újra! 🎪",
                    "🤡 A bohóc részeg! Próbáld újra! 🤡",
                    "🎭 A színész elfelejtette a szöveget! Próbáld újra! 🎭",
                    "🃏 A mágus eltüntette a jegyet! Próbáld újra! 🃏",
                ]
                await interaction.response.send_message(random.choice(funny_fail_messages), ephemeral=True)
                return

        # Check if player is banned from testing
        # We need to check using the Discord username as the tierlist name
        # The tierlist name is the Minecraft name, not Discord name
        # We'll check both: first try Minecraft name from nickname/display name, then Discord name

        # For now, check the website for ban status using the Discord name as fallback
        # The user should ideally set their Minecraft name in their Discord nickname
        player_name = member.display_name
        if member.nick:
            player_name = member.nick

        # Try to get ban status from website
        if WEBSITE_URL:
            try:
                url = f"{WEBSITE_URL}/api/tests/ban?username={player_name}"
                timeout = aiohttp.ClientTimeout(total=5)
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=_auth_headers(), timeout=timeout) as resp:
                        if resp.status == 200:
                            ban_data = await resp.json()
                            if ban_data.get("banned"):
                                reason = ban_data.get("reason", "")
                                await interaction.response.send_message(
                                    f"❌ Ki vagy tiltva a tesztelésből!\n" +
                                    (f"**Ok:** {reason}" if reason else ""),
                                    ephemeral=True
                                )
                                return
            except Exception:
                pass  # If ban check fails, continue (fail open)

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
                topic=f"NeoTiers ticket | owner={member.id} | mode={self.mode_key} | mc={linked_minecraft}",
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

        rounds_display = get_ticket_rounds_display(self.mode_key)

        # April Fools' funny ticket embed
        if APRIL_FOOLS_MODE:
            funny_descriptions = [
                "🎪 A cirkusz megnyitotta kapuit! 🎪",
                "🤡 A bohóc várja a jelentkezésedet! 🤡",
                "🎭 A színpad készen áll! 🎭",
                "🃏 A kártyák összekeveredtek! 🃏",
                "🎪 Ma mindenki bolond! 🎪",
            ]
            description = random.choice(funny_descriptions)
        else:
            description = "Kattints egy alábbi gombra, hogy tudd tesztelni a gombon feltüntetett játékmódból."

        embed = discord.Embed(
            title="Teszt kérés",
            description=description,
            color=discord.Color.blurple()
        )

        # April Fools' funny mode display
        display_mode = get_gamemode_display_name(self.mode_key)
        if APRIL_FOOLS_MODE:
            display_mode = display_mode

        embed.add_field(name="Játékmód", value=display_mode, inline=True)
        embed.add_field(name="Minecraft név", value=f"`{linked_minecraft}`", inline=True)

        # April Fools' Melegségi szint (warmth level)
        if APRIL_FOOLS_MODE:
            melegseg = random.randint(60, 101)
            embed.add_field(name="🌡️ Melegségi szint", value=f"{melegseg}%", inline=True)

        embed.add_field(name="Körök", value=rounds_display, inline=False)
        embed.add_field(name="Játékos", value=member.mention, inline=True)

        # Add April Fools' message
        if APRIL_FOOLS_MODE and random.random() < 0.3:
            embed.add_field(name="🎪 Áprilisi üzenet:", value=get_april_fools_message(), inline=False)

        await channel.send(content=ping_text, embed=embed, view=CloseTicketView(owner_id=member.id, mode_key=self.mode_key))
        await interaction.response.send_message(f"✅ Ticket létrehozva: {channel.mention}", ephemeral=True)


# =========================
# QUEUE SYSTEM
# =========================

# Channel mappings for each gamemode queue
QUEUE_CHANNELS = {
    "sword": 1495038486120632410,
    "axe": 1495038602751774730,
    "mace": 1495038625719783586,
    "uhc": 1495038706103484487,
    "pot": 1495038741465792553,
    "nethpot": 1495038766769897482,
    "smp": 1495038799800176660,
    "vanilla": 1495038839591534834,
    "creeper": 1495038857597681818,
    "cart": 1495038915453779982,
    "diasmp": 1495038938640027760,
    "spearelytra": 1495038976988545206,
    "spearmace": 1495038999876600008,
    "shieldlessuhc": 1495039115119296572,
    "ogvanilla": 1495039145330872341,
}

# Ping role IDs for each gamemode
QUEUE_PING_ROLES = {
    "sword": 1495043729017278525,
    "axe": 1495043913583558758,
    "mace": 1495043981959237752,
    "uhc": 1495044042612805754,
    "pot": 1495044102730022942,
    "nethpot": 1495044163194847322,
    "smp": 1495044237551472893,
    "vanilla": 1495044315272052929,
    "creeper": 1495044383425171506,
    "cart": 1495044436403556443,
    "diasmp": 1495044514992095333,
    "shieldlessuhc": 1495044593211670711,
    "ogvanilla": 1495044664502386698,
    "spearelytra": 1495044732680667247,
    "spearmace": 1495044798472781944,
}

# Category where ticket channels will be created
TICKET_CREATE_CATEGORY_ID = 1495038336744689674

# In-memory queue storage
ACTIVE_QUEUES: Dict[str, Dict[str, Any]] = {}
QUEUE_MESSAGE_IDS: Dict[int, str] = {}

class QueuePlayer:
    """Represents a player in a queue"""
    def __init__(self, discord_id: int, minecraft_name: str):
        self.discord_id = discord_id
        self.minecraft_name = minecraft_name
        self.joined_at = time.time()

class QueueUserView(discord.ui.View):
    def __init__(self, gamemode: str):
        super().__init__(timeout=None)
        self.gamemode = gamemode

    @discord.ui.button(label="Belépés a queue-ba", style=discord.ButtonStyle.success)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("❌ Hiba: nem tag", ephemeral=True)
            return
        queue = ACTIVE_QUEUES.get(self.gamemode)
        if not queue:
            await interaction.response.send_message("❌ Nincs queue", ephemeral=True)
            return
        if any(p.discord_id == member.id for p in queue["players"]):
            await interaction.response.send_message("⚠️ Már benne vagy!", ephemeral=True)
            return
        if is_staff_member(member):
            queue["players"].append(QueuePlayer(member.id, "TESZTER"))
            await update_queue_message(self.gamemode)
            await interaction.response.send_message("✅ Beléptél teszterként!", ephemeral=True)
            return
        linked_mc = await get_linked_minecraft_name_async(member.id)
        if not linked_mc:
            await interaction.response.send_message("❌ Nincs linked MC! `/link`", ephemeral=True)
            return
        queue["players"].append(QueuePlayer(member.id, linked_mc))
        await update_queue_message(self.gamemode)
        await interaction.response.send_message("✅ Beléptél a queue-ba!", ephemeral=True)

    @discord.ui.button(label="Kilépés a queue-ból", style=discord.ButtonStyle.danger)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("❌ Hiba: nem tag", ephemeral=True)
            return
        queue = ACTIVE_QUEUES.get(self.gamemode)
        if not queue:
            await interaction.response.send_message("❌ Nincs queue", ephemeral=True)
            return
        for i, p in enumerate(queue["players"]):
            if p.discord_id == member.id:
                queue["players"].pop(i)
                await update_queue_message(self.gamemode)
                await interaction.response.send_message("✅ Kiléptél a queue-ból!", ephemeral=True)
                return
        await interaction.response.send_message("⚠️ Nem vagy a queue-ban", ephemeral=True)

    @discord.ui.button(label="❌ Queue bezárása", style=discord.ButtonStyle.secondary)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("❌ Hiba: nem tag", ephemeral=True)
            return
        queue = ACTIVE_QUEUES.get(self.gamemode)
        if not queue:
            await interaction.response.send_message("❌ Nincs queue", ephemeral=True)
            return
        if not is_staff_member(member) and queue["opened_by"] != member.id:
            await interaction.response.send_message("❌ Nincs jogod", ephemeral=True)
            return
        del ACTIVE_QUEUES[self.gamemode]
        await update_queue_message(self.gamemode)
        await interaction.response.send_message("✅ Queue bezárva!", ephemeral=True)

    @discord.ui.button(label="Következő játékos", style=discord.ButtonStyle.primary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("❌ Hiba: nem tag", ephemeral=True)
            return
        queue = ACTIVE_QUEUES.get(self.gamemode)
        if not queue or not queue["players"]:
            await interaction.response.send_message("❌ Nincs játékos a queue-ban", ephemeral=True)
            return
        if not is_staff_member(member) and queue["opened_by"] != member.id:
            await interaction.response.send_message("❌ Nincs jogod", ephemeral=True)
            return
        next_player_obj = queue["players"].pop(0)
        queue["called_players"].append(next_player_obj.discord_id)
        await update_queue_message(self.gamemode)
        guild = interaction.guild
        category = guild.get_channel(TICKET_CREATE_CATEGORY_ID)
        if not category or not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message("❌ Nincs kategória", ephemeral=True)
            return
        channel_name = f"{self.gamemode}-{next_player_obj.minecraft_name}"[:50].lower()
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.get_member(next_player_obj.discord_id): discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        if STAFF_ROLE_ID:
            overwrites[guild.get_role(STAFF_ROLE_ID)] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True)
        channel = await guild.create_text_channel(name=channel_name, category=category, overwrites=overwrites, topic=f"owner={next_player_obj.discord_id} | mode={self.gamemode}")
        embed = discord.Embed(title="Teszt kérés", color=discord.Color.blurple())
        embed.add_field(name="Játékos", value=f"<@{next_player_obj.discord_id}>", inline=True)
        embed.add_field(name="Minecraft", value=next_player_obj.minecraft_name, inline=True)
        embed.set_thumbnail(url=f"https://minotar.net/helm/{next_player_obj.minecraft_name}/128.png")
        view = CloseTicketView(owner_id=next_player_obj.discord_id, mode_key=self.gamemode)
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"✅ Ticket létrehozva: {channel.mention}", ephemeral=True)


class QueueTesterView(discord.ui.View):
    def __init__(self, gamemode: str):
        super().__init__(timeout=None)
        self.gamemode = gamemode

    @discord.ui.button(label="Belepes", style=discord.ButtonStyle.success)
    async def join_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("Hiba", ephemeral=True)
            return

        queue = ACTIVE_QUEUES.get(self.gamemode)
        if not queue:
            await interaction.response.send_message("❌ A queue nem létezik vagy nem nyitva.", ephemeral=True)
            return

        if any(p.discord_id == member.id for p in queue["players"]):
            await interaction.response.send_message("Már benne vagy a queue-ban!", ephemeral=True)
            return

        # Check cooldown
        cd = cooldown_left(member.id, self.gamemode)
        if cd > 0:
            await interaction.response.send_message(
                f"❌ Még nem tesztelhetsz! Várj: **{format_cooldown(cd)}**",
                ephemeral=True
            )
            return

        # Check if already LT3+ (can't join queue if already LT3 or above)
        player_tier = await get_player_tier_for_mode(member.id, self.gamemode)
        if is_lt3_or_above(player_tier):
            await interaction.response.send_message(
                f"❌ Már **{player_tier}** vagy! Használd a `/ticketpanel`-t a teszthez.",
                ephemeral=True
            )
            return

        linked_mc = await get_linked_minecraft_name_async(member.id)
        if not linked_mc:
            await interaction.response.send_message(
                "❌ Nincs összekapcsolva a Minecraft fiókod! Használd a `/link` parancsot.",
                ephemeral=True
            )
            return

        queue["players"].append(QueuePlayer(member.id, linked_mc))
        await update_queue_message(self.gamemode)
        await interaction.response.send_message(
            f"✅ Beléptél a **{get_gamemode_display_name(self.gamemode)}** queue-ba!",
            ephemeral=True
        )

    @discord.ui.button(label="Kilépés a queue-ból", style=discord.ButtonStyle.danger, custom_id="queue_leave")
    async def leave_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if not member:
            await interaction.response.send_message("Hiba: nem tag.", ephemeral=True)
            return

        queue = ACTIVE_QUEUES.get(self.gamemode)
        if not queue:
            await interaction.response.send_message("❌ A queue nem létezik.", ephemeral=True)
            return

        for i, p in enumerate(queue["players"]):
            if p.discord_id == member.id:
                queue["players"].pop(i)
                await update_queue_message(self.gamemode)
                await interaction.response.send_message(
                    f"✅ Kiléptél a **{get_gamemode_display_name(self.gamemode)}** queue-ból!",
                    ephemeral=True
                )
                return

        await interaction.response.send_message("Nem vagy a queue-ban.", ephemeral=True)

    @discord.ui.button(label="❌ Queue bezárása", style=discord.ButtonStyle.secondary, custom_id="queue_close")
    async def close_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if not member:
            await interaction.response.send_message("Hiba: nem tag.", ephemeral=True)
            return

        queue = ACTIVE_QUEUES.get(self.gamemode)
        if not queue:
            await interaction.response.send_message("❌ A queue már lezárva.", ephemeral=True)
            return

        if not is_staff_member(member) and queue["opened_by"] != member.id:
            await interaction.response.send_message("❌ Csak a queue-t megnyitó tesztelő zárhatja be.", ephemeral=True)
            return

        view = ConfirmCloseQueueView(self.gamemode)
        await interaction.response.send_message(
            f"Biztosan be szeretnéd zárni a **{get_gamemode_display_name(self.gamemode)}** queue-t?",
            view=view,
            ephemeral=True
        )

    @discord.ui.button(label="Következő játékos", style=discord.ButtonStyle.primary, custom_id="queue_next")
    async def next_player(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if not member:
            await interaction.response.send_message("Hiba: nem tag.", ephemeral=True)
            return

        queue = ACTIVE_QUEUES.get(self.gamemode)
        if not queue or not queue["players"]:
            await interaction.response.send_message("❌ Nincs több játékos a queue-ban.", ephemeral=True)
            return

        if not is_staff_member(member) and queue["opened_by"] != member.id:
            await interaction.response.send_message("❌ Csak a queue-t megnyitó tesztelő hívhatja a következő játékost.", ephemeral=True)
            return

        # Get next player (FIFO)
        next_player_obj = queue["players"].pop(0)
        queue["called_players"].append(next_player_obj.discord_id)
        await update_queue_message(self.gamemode)

        # Create ticket channel
        guild = interaction.guild
        category = guild.get_channel(TICKET_CREATE_CATEGORY_ID)
        if not category or not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message("❌ Hiba: ticket kategória nem található.", ephemeral=True)
            return

        channel_name = f"{self.gamemode}-{next_player_obj.minecraft_name}".lower().replace(" ", "-")[:50]
        try:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.get_member(next_player_obj.discord_id): discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True
                ),
            }
            if STAFF_ROLE_ID:
                staff_role = guild.get_role(STAFF_ROLE_ID)
                if staff_role:
                    overwrites[staff_role] = discord.PermissionOverwrite(
                        view_channel=True, send_messages=True, read_message_history=True, manage_channels=True
                    )

            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"owner={next_player_obj.discord_id} | mode={self.gamemode} | mc={next_player_obj.minecraft_name}",
                reason=f"Queue ticket for {next_player_obj.minecraft_name}"
            )

            # Get player's current tier and rounds info
            prev_rank = "Unranked"
            rounds_display = get_ticket_rounds_display(self.gamemode)
            if WEBSITE_URL:
                try:
                    res = await api_get_tests(username=next_player_obj.minecraft_name, mode=self.gamemode)
                    if res.get("status") == 200:
                        data = res.get("data", {})
                        test = data.get("test")
                        tests = data.get("tests", [])
                        target = test or (tests[0] if tests else None)
                        if target:
                            prev_rank = str(target.get("rank", "Unranked")) or "Unranked"
                except Exception as e:
                    print(f"Error fetching tier: {e}")

            embed = discord.Embed(
                title="Teszt kérés",
                color=discord.Color.blurple()
            )
            embed.add_field(name="Játékmód", value=get_gamemode_display_name(self.gamemode), inline=True)
            embed.add_field(name="Minecraft név", value=f"`{next_player_obj.minecraft_name}`", inline=True)
            embed.add_field(name="Jelenlegi tier", value=prev_rank, inline=True)
            embed.add_field(name="Körök", value=rounds_display, inline=False)
            embed.add_field(name="Játékos", value=f"<@{next_player_obj.discord_id}>", inline=True)
            embed.set_thumbnail(url=f"https://minotar.net/helm/{next_player_obj.minecraft_name}/128.png")

            view = CloseTicketView(owner_id=next_player_obj.discord_id, mode_key=self.gamemode)
            await channel.send(embed=embed, view=view)

            await interaction.response.send_message(
                f"✅ Ticket létrehozva: {channel.mention} | Játékos: {next_player_obj.minecraft_name}",
                ephemeral=True
            )

        except Exception as e:
            await interaction.response.send_message(f"❌ Hiba a channel létrehozása során: {e}", ephemeral=True)


class ConfirmCloseQueueView(discord.ui.View):
    def __init__(self, gamemode: str):
        super().__init__(timeout=30)
        self.gamemode = gamemode

    @discord.ui.button(label="Igen, zárja be", style=discord.ButtonStyle.danger, custom_id="queue_close_confirm")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("Hiba.", ephemeral=True)
            return

        queue = ACTIVE_QUEUES.get(self.gamemode)
        if not queue:
            await interaction.response.send_message("❌ A queue már nem létezik.", ephemeral=True)
            return

        if queue["opened_by"] != member.id and not is_staff_member(member):
            await interaction.response.send_message("❌ Csak a queue-t megnyitó tesztelő zárhatja be.", ephemeral=True)
            return

        del ACTIVE_QUEUES[self.gamemode]
        await interaction.response.send_message(
            f"✅ **{get_gamemode_display_name(self.gamemode)}** queue bezárva.",
            ephemeral=True
        )

        # Try to update the message
        try:
            msg_id = None
            for mid, gm in list(QUEUE_MESSAGE_IDS.items()):
                if gm == self.gamemode:
                    msg_id = mid
                    break
            if msg_id:
                channel_id = QUEUE_CHANNELS.get(self.gamemode)
                if channel_id:
                    channel = bot.get_channel(channel_id)
                    if channel:
                        msg = await channel.fetch_message(msg_id)
                        embed = discord.Embed(
                            title=f"🔴 {get_gamemode_display_name(self.gamemode)} Queue",
                            description="A queue zárva van.",
                            color=discord.Color.red()
                        )
                        await msg.edit(embed=embed, view=None)
                        del QUEUE_MESSAGE_IDS[msg_id]
        except Exception:
            pass

    @discord.ui.button(label="Mégsem", style=discord.ButtonStyle.secondary, custom_id="queue_close_cancel")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("❌ Mégse.", ephemeral=True)


class PingRoleSelect(discord.ui.Select):
    def __init__(self, selected_gamemodes: List[str] = None):
        self.selected_gamemodes = selected_gamemodes or []
        options = []
        for label, key, _rid in TICKET_TYPES:
            default = key in self.selected_gamemodes
            options.append(
                discord.SelectOption(
                    label=label,
                    value=key,
                    description=f"Ping értesítések ehhez a {label} queue-hoz",
                    default=default
                )
            )
        super().__init__(
            placeholder="Válaszd ki a queue-okat amikor pingelni szeretnél... (üres = mindet kikapcsolod)",
            min_values=0,
            max_values=len(TICKET_TYPES),
            options=options,
            custom_id="ping_queue_select"
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            member = interaction.user
            if not isinstance(member, discord.Member):
                await interaction.response.send_message("Hiba: nem tag.", ephemeral=True)
                return

            guild = member.guild
            selected_gms = set(self.values)

            # All gamemodes with ping roles
            all_ping_gms = set(QUEUE_PING_ROLES.keys())

            # Compute differences: for each gamemode, decide to add or remove role
            added = []
            removed = []
            errors = []

            for gm in all_ping_gms:
                role_id = QUEUE_PING_ROLES[gm]
                role = guild.get_role(role_id)
                if not role:
                    continue
                has_role = any(r.id == role_id for r in member.roles)
                should_have = gm in selected_gms
                if should_have and not has_role:
                    try:
                        await member.add_roles(role, reason="Ping preference via /pingpanel")
                        added.append(role.name)
                    except Exception as e:
                        errors.append(f"Nem sikerült hozzáadni {role.name}: {e}")
                elif not should_have and has_role:
                    try:
                        await member.remove_roles(role, reason="Ping preference via /pingpanel")
                        removed.append(role.name)
                    except Exception as e:
                        errors.append(f"Nem sikerült eltávolítani {role.name}: {e}")

            parts = []
            if added:
                parts.append(f"✅ Hozzáadva: {', '.join(added)}")
            if removed:
                parts.append(f"❌ Eltávolítva: {', '.join(removed)}")
            if not added and not removed:
                parts.append("Nincs változtatás.")
            if errors:
                parts.append("\nHibák:\n" + "\n".join(errors))

            await interaction.response.send_message("\n".join(parts), ephemeral=True)
        except Exception as e:
            print(f"Ping role select error: {e}")
            await interaction.response.send_message(f"❌ Hiba: {e}", ephemeral=True)


class PingPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(PingRoleSelect())
        self.add_item(ClearAllPingsButton())


class ClearAllPingsButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="❌ Minden ping kikapcsolása",
            style=discord.ButtonStyle.danger,
            custom_id="clear_all_pings"
        )

    @discord.ui.button(label="❌ Minden ping kikapcsolása", style=discord.ButtonStyle.danger, custom_id="clear_all_pings")
    async def callback(self, interaction: discord.Interaction):
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("Hiba: nem tag.", ephemeral=True)
            return

        guild = member.guild
        removed = []
        errors = []

        for gm, role_id in QUEUE_PING_ROLES.items():
            role = guild.get_role(role_id)
            if not role:
                continue
            has_role = any(r.id == role_id for r in member.roles)
            if has_role:
                try:
                    await member.remove_roles(role, reason="Ping preference clear all")
                    removed.append(role.name)
                except Exception as e:
                    errors.append(f"Nem sikerült eltávolítani {role.name}: {e}")

        parts = []
        if removed:
            parts.append(f"❌ Eltávolítva: {', '.join(removed)}")
        else:
            parts.append("Nincs bekapcsolva ping.")
        if errors:
            parts.append("\nHibák:\n" + "\n".join(errors))

        await interaction.response.send_message("\n".join(parts), ephemeral=True)


class QueueOpenSelect(discord.ui.Select):
    def __init__(self):
        options = []
        for label, key, _rid in TICKET_TYPES:
            if key in ACTIVE_QUEUES:
                continue
            options.append(
                discord.SelectOption(
                    label=label,
                    value=key,
                    description=f"Queue: {label}"
                )
            )
        # Always have at least one option
        if not options:
            options.append(discord.SelectOption(label="---", value="dummy"))
        super().__init__(
            placeholder="Válaszd ki a queue-t...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="queue_open"
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            member = interaction.user
            if not isinstance(member, discord.Member):
                await interaction.response.send_message("Hiba", ephemeral=True)
                return
            if not is_staff_member(member):
                await interaction.response.send_message("Nincs jogod", ephemeral=True)
                return
            mode_key = self.values[0]
            if mode_key == "dummy":
                await interaction.response.send_message("Mindegyik queue nyitva van", ephemeral=True)
                return
            if mode_key in ACTIVE_QUEUES:
                await interaction.response.send_message("Mar nyitva", ephemeral=True)
                return

            mode_display = get_gamemode_display_name(mode_key)
            ACTIVE_QUEUES[mode_key] = {"opened_by": member.id, "opened_at": time.time(), "players": [], "called_players": []}

            channel_id = QUEUE_CHANNELS.get(mode_key)
            if not channel_id:
                await interaction.response.send_message("Nincs channel", ephemeral=True)
                return

            channel = member.guild.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                await interaction.response.send_message("Channel nem talalt", ephemeral=True)
                return

            role = None
            ping_role_id = QUEUE_PING_ROLES.get(mode_key)
            if ping_role_id:
                role = member.guild.get_role(ping_role_id)
            ping_mention = role.mention if role else None

            embed = discord.Embed(title=f"{mode_display} Queue", description="Belepes/Kilepes", color=discord.Color.green())
            embed.add_field(name="Jatekosok", value="0", inline=False)
            embed.set_footer(text=f"NY: {member.display_name}")

            view = QueueUserView(mode_key)
            message = await channel.send(content=ping_mention, embed=embed, view=view)
            QUEUE_MESSAGE_IDS[message.id] = mode_key
            await interaction.response.send_message(f"Queue nyitva: {mode_display}", ephemeral=True)
        except Exception as e:
            print(f"open queue err: {e}")
            await interaction.response.send_message(f"Hiba: {e}", ephemeral=True)


class QueueOpenPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(QueueOpenSelect())


async def update_queue_message(gamemode: str):
    """Update the queue embed in its channel"""
    channel_id = QUEUE_CHANNELS.get(gamemode)
    if not channel_id:
        return

    channel = bot.get_channel(channel_id)
    if not channel or not isinstance(channel, discord.TextChannel):
        return

    msg_id = None
    for mid, gm in QUEUE_MESSAGE_IDS.items():
        if gm == gamemode:
            msg_id = mid
            break
    if not msg_id:
        return

    try:
        message = await channel.fetch_message(msg_id)
    except Exception:
        return

    queue = ACTIVE_QUEUES.get(gamemode)
    if not queue:
        embed = discord.Embed(
            title=f"🔴 {get_gamemode_display_name(gamemode)} Queue",
            description="A queue zárva van.",
            color=discord.Color.red()
        )
        try:
            await message.edit(embed=embed, view=None)
        except Exception:
            pass
        return

    player_lines = []
    for player in queue["players"]:
        member = channel.guild.get_member(player.discord_id)
        name = member.display_name if member else player.minecraft_name
        if is_staff_member(member):
            name = f"⭐ {name}"
        player_lines.append(f"{name} ({player.minecraft_name})")

    player_text = "\n".join(player_lines) if player_lines else "Még senki nincs a queue-ban."

    embed = discord.Embed(
        title=f"🟢 {get_gamemode_display_name(gamemode)} Queue",
        description=f"Játékosok a queue-ban: **{len(queue['players'])}**",
        color=discord.Color.green()
    )
    embed.add_field(name="Játékosok", value=player_text, inline=False)
    opener = channel.guild.get_member(queue["opened_by"])
    embed.set_footer(text=f"Nyitotta: {opener.display_name if opener else 'Unknown'}")

    view = QueueUserView(gamemode)
    try:
        await message.edit(embed=embed, view=view)
    except Exception as e:
        print(f"Queue update error [{gamemode}]: {e}")


async def queue_maintenance_task():
    """Periodically update all queue messages"""
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            await asyncio.sleep(30)
            for gm in list(ACTIVE_QUEUES.keys()):
                try:
                    await update_queue_message(gm)
                except Exception as e:
                    print(f"[QueueMaintenance] {gm}: {e}")
        except Exception as e:
            print(f"[QueueMaintenance] Fatal: {e}")


# Note: bot will be imported from main.py when initializing


def _choices_from_list(values):
    return [app_commands.Choice(name=v, value=v) for v in values]


@bot.tree.command(name="ticketpanel", description="Ticket panel üzenet kirakása.")
async def ticketpanel(interaction: discord.Interaction):
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

        # April Fools' funny ticket panel
        if APRIL_FOOLS_MODE:
            funny_descriptions = [
                "🎪 Üdvözöllek a cirkuszban! Válassz egy játékmódot! 🎪",
                "🤡 A bohóc várja a jelentkezésedet! 🤡",
                "🎭 A színpad készen áll! Válassz egy szerepet! 🎭",
                "🃏 A kártyák összekeveredtek! Válassz egyet! 🃏",
            ]
            description = random.choice(funny_descriptions)
        else:
            description = "Kattints egy alábbi gombra, hogy tudd tesztelni a gombon feltüntetett játékmódból."

        embed = discord.Embed(
            title="Teszt kérés",
            description=description,
            color=discord.Color.blurple()
        )

        # Add April Fools' message to footer
        if APRIL_FOOLS_MODE:
            embed.set_footer(text=get_april_fools_message())

        await interaction.channel.send(embed=embed, view=TicketPanelView())
        await interaction.followup.send("✅ Ticket panel kirakva.", ephemeral=True)

    except discord.Forbidden:
        await interaction.followup.send("❌ Nem tudok ide írni (Missing Permissions). Adj írás jogot a botnak ebben a csatornában.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


async def autocomplete_testresult_username(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    if not WEBSITE_URL:
        return []

    try:
        url = f"{WEBSITE_URL}/api/tests"
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=_auth_headers(), timeout=timeout) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                tests = data.get("tests", [])

                # Extract unique usernames
                usernames = set()
                for t in tests:
                    u = t.get("username")
                    if u:
                        usernames.add(u)

                # Filter by current input
                matches = [u for u in usernames if current.lower() in u.lower()]
                return [app_commands.Choice(name=u, value=u) for u in matches[:25]]
    except Exception:
        return []


@bot.tree.command(name="queuepanel", description="Queue panel üzenet kirakása (tesztelőknek)")
async def queuepanel(interaction: discord.Interaction):
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

        embed = discord.Embed(
            title="🔓 Queue Nyitás",
            description="Válaszd ki a queue-t amit meg szeretnél nyitni:",
            color=discord.Color.green()
        )

        await interaction.channel.send(embed=embed, view=QueueOpenPanelView())
        await interaction.followup.send("✅ Queue panel kirakva.", ephemeral=True)

    except discord.Forbidden:
        await interaction.followup.send("❌ Nem tudok ide írni (Missing Permissions).", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


@bot.tree.command(name="closequeue", description="Queue bezárása")
@app_commands.describe(
    gamemode="A queue amit be szeretnél zárni"
)
@app_commands.choices(
    gamemode=_choices_from_list(MODE_LIST)
)
async def closequeue(interaction: discord.Interaction, gamemode: app_commands.Choice[str]):
    """Close a queue (only owner or staff)"""
    await interaction.response.defer(ephemeral=True)

    try:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("Hiba.", ephemeral=True)
            return

        mode_key = gamemode.value.lower()
        mode_display = get_gamemode_display_name(mode_key)

        queue = ACTIVE_QUEUES.get(mode_key)
        if not queue:
            await interaction.followup.send(f"❌ A **{mode_display}** queue nincs nyitva.", ephemeral=True)
            return

        is_owner = queue["opened_by"] == interaction.user.id
        is_staff = is_staff_member(interaction.user)

        if not is_owner and not is_staff:
            await interaction.followup.send("❌ Csak a queue nyitói vagy tesztelők zárhatják be.", ephemeral=True)
            return

        del ACTIVE_QUEUES[mode_key]

        channel_id = QUEUE_CHANNELS.get(mode_key)
        if channel_id:
            channel = interaction.guild.get_channel(channel_id)
            if channel and isinstance(channel, discord.TextChannel):
                msg_id = None
                for mid, gm in QUEUE_MESSAGE_IDS.items():
                    if gm == mode_key:
                        msg_id = mid
                        break
                if msg_id:
                    try:
                        msg = await channel.fetch_message(msg_id)
                        embed = discord.Embed(
                            title=f"🔴 {mode_display} Queue",
                            description="A queue be lett zárva.",
                            color=discord.Color.red()
                        )
                        await msg.edit(content=None, embed=embed, view=None)
                        QUEUE_MESSAGE_IDS.pop(msg_id, None)
                    except Exception:
                        pass

        await interaction.followup.send(f"✅ **{mode_display}** queue bezárva!", ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


@bot.tree.command(name="pingpanel", description="Ping értesítések beállítása queue-okhoz")
async def pingpanel(interaction: discord.Interaction):
    """Set up ping notifications for queues"""
    await interaction.response.defer()

    try:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("Hiba: csak szerveren használható.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🔔 Ping Beállítások",
            description="Válaszd ki a queue-okat amikor értesíteni szeretnél:",
            color=discord.Color.blue()
        )
        view = PingPanelView()
        await interaction.followup.send(embed=embed, view=view)

    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


@bot.tree.command(name="tests", description="Tesztelői statisztikák")
async def tests_command(interaction: discord.Interaction):
    """Show how many players each tester has tested"""
    await interaction.response.defer(ephemeral=True)

    try:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("Hiba: csak szerveren használható.", ephemeral=True)
            return

        if not is_staff_member(interaction.user):
            await interaction.followup.send("Nincs jogosultságod ehhez a parancshoz.", ephemeral=True)
            return

        if not WEBSITE_URL:
            await interaction.followup.send("Hiba: WEBSITE_URL nincs beállítva.", ephemeral=True)
            return

        res = await api_get_all_tests()
        if res.get("status") != 200:
            await interaction.followup.send(f"Hiba az API híváskor: {res.get('data', {}).get('error', 'ismeretlen')}", ephemeral=True)
            return

        data = res.get("data", {})
        all_tests = data.get("tests", [])

        tester_counts: Dict[str, int] = {}
        tester_names: Dict[str, str] = {}

        for t in all_tests:
            tester_id = str(t.get("testerId", ""))
            tester_name = str(t.get("testerName", "Unknown"))
            if tester_id:
                tester_counts[tester_id] = tester_counts.get(tester_id, 0) + 1
                tester_names[tester_id] = tester_name

        if not tester_counts:
            await interaction.followup.send("Még nincs tesztelési adat.", ephemeral=True)
            return

        sorted_testers = sorted(tester_counts.items(), key=lambda x: x[1], reverse=True)

        lines = []
        total = sum(tester_counts.values())
        for tester_id, count in sorted_testers:
            name = tester_names.get(tester_id, "Unknown")
            lines.append(f"**{name}**: {count}")

        embed = discord.Embed(
            title="📊 Tesztelői statisztikák",
            description=f"Összesen: **{total}** teszt",
            color=discord.Color.blurple()
        )

        chunk_size = 10
        for i in range(0, len(lines), chunk_size):
            chunk = lines[i:i+chunk_size]
            embed.add_field(
                name="Tesztelők" if i == 0 else f"Tesztelők (folyt)" if chunk else "\u200b",
                value="\n".join(chunk) if chunk else "\u200b",
                inline=False
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


@bot.tree.command(name="testresult", description="Minecraft tier teszt eredmény embed + weboldal mentés.")
@app_commands.describe(
    username="Minecraft név (ebből lesz a skin a weboldalon)",
    tester="Tesztelő (Discord user)",
    gamemode="Játékmód",
    rank="Elért rank (pl. LT3 / HT3)"
)
@app_commands.autocomplete(username=autocomplete_testresult_username)
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
    import uuid
    execution_id = str(uuid.uuid4())[:8]
    print(f"[TESTRESULT {execution_id}] Command started for {username} by {interaction.user.id}")
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
        print(f"[TESTRESULT {execution_id}] Getting previous rank for {username} in {mode_val}...")
        if WEBSITE_URL:
            try:
                res = await api_get_tests(username=username, mode=mode_val)
                print(f"[TESTRESULT {execution_id}] Got previous rank response: {res.get('status')}")
                if res.get("status") == 200:
                    data = res.get("data", {})
                    # Handle single result (test) or list (tests)
                    test = data.get("test")
                    tests = data.get("tests", [])

                    target = test if test else (tests[0] if tests else None)

                    if target:
                        prev_rank = str(target.get("rank", "Unranked")) or "Unranked"
            except Exception:
                pass

        prev_points = POINTS.get(prev_rank, 0)
        new_points = POINTS.get(rank_val, 0)
        diff = new_points - prev_points

        # PUBLIC EMBED (everyone sees)
        skin_url = f"https://minotar.net/helm/{username}/128.png"

        # April Fools' effects
        display_username = username
        display_mode = mode_val
        display_prev_rank = get_funny_rank(prev_rank) if APRIL_FOOLS_MODE else prev_rank
        display_rank_val = get_funny_rank(rank_val) if APRIL_FOOLS_MODE else rank_val

        embed = discord.Embed(
            title=f"{display_username} teszt eredménye 🏆",
            color=discord.Color.dark_grey()
        )
        embed.set_thumbnail(url=skin_url)
        embed.add_field(name="Tesztelő:", value=tester.mention, inline=False)
        embed.add_field(name="Játékmód:", value=display_mode, inline=False)
        embed.add_field(name="Minecraft név:", value=display_username, inline=False)
        embed.add_field(name="Előző rang:", value=display_prev_rank, inline=False)
        embed.add_field(name="Elért rang:", value=display_rank_val, inline=False)

        # Add random April Fools' message
        if APRIL_FOOLS_MODE and random.random() < 0.3:
            embed.add_field(name="🎪 Áprilisi üzenet:", value=get_april_fools_message(), inline=False)

        # Only send to the results channel (eredmenyek), not the command channel
        # ALWAYS save to website first (UPsert)
        if not WEBSITE_URL:
            await interaction.followup.send("⚠️ WEBSITE_URL nincs beállítva, nem mentem webre.", ephemeral=True)
            return

        # Normalize mode to proper display name before saving
        mode_to_save = get_gamemode_display_name(mode_val)
        save = await api_post_test(username=username, mode=mode_to_save, rank=rank_val, tester=tester)
        save_status = save.get("status")
        save_data = save.get("data")
        save_ok = (save_status == 200 or save_status == 201)

        print(f"[TESTRESULT {execution_id}] DEBUG: save to website status: {save_status}, ok: {save_ok}")

        # Set cooldown for the tested player (ALWAYS do this after saving)
        channel = interaction.channel
        owner_id = None
        if channel and channel.topic:
            try:
                # Parse "owner=123456789"
                for part in channel.topic.split(" | "):
                    if part.startswith("owner="):
                        owner_id = int(part.split("=")[1])
                        break
            except Exception:
                pass

        if owner_id:
            set_last_closed(owner_id, mode_val, time.time())

        # Send to results channel if configured
        tier_channel_id_str = os.getenv("TIER_RESULTS_CHANNEL_ID", "0")
        try:
            tier_channel_id = int(tier_channel_id_str)
        except ValueError:
            tier_channel_id = 0

        if tier_channel_id:
            tier_channel = interaction.guild.get_channel(tier_channel_id)
            if tier_channel:
                print(f"[TESTRESULT {execution_id}] DEBUG: sending to channel {tier_channel.name}...")
                await tier_channel.send(embed=embed)
                print(f"[TESTRESULT {execution_id}] DEBUG: sent to results channel: {tier_channel.name}")
                await interaction.followup.send(
                    f"✅ Eredmény mentve!\nElőző: **{prev_rank}** → Elért: **{rank_val}** | "
                    f"{'+' if diff>=0 else ''}{diff} pont",
                    ephemeral=True
                )
                print(f"[TESTRESULT {execution_id}] DEBUG: followup sent, returning...")
                return
            else:
                print(f"[TESTRESULT {execution_id}] DEBUG: could not find results channel with ID: {tier_channel_id}")

        # Try fallback by name
        tier_channel = discord.utils.get(interaction.guild.text_channels, name="teszteredmenyek")
        if tier_channel:
            await tier_channel.send(embed=embed)
            return
        tier_channel = discord.utils.get(interaction.guild.text_channels, name="test-results")
        if tier_channel:
            await tier_channel.send(embed=embed)
            return

        # Fallback: send response if no results channel was found
        if save_ok:
            await interaction.followup.send(
                f"✅ Mentve + weboldal frissítve.\nElőző: **{prev_rank}** → Elért: **{rank_val}** | "
                f"{'+' if diff>=0 else ''}{diff} pont",
                ephemeral=True
            )
        else:
            # Truncate save_data to avoid Discord's 2000 character limit
            save_data_str = truncate_message(str(save_data), 1500)
            await interaction.followup.send(
                f"⚠️ Mentés hiba a weboldal felé (status {save_status}) | {save_data_str}",
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


@bot.tree.command(name="cooldown", description="Megnézed a cooldownidat egy játékmódban, vagy egy másik játékos cooldownját (staff).")
@app_commands.describe(
    user="Játékos (ha üres, a sajátodat nézed meg)"
)
async def cooldown(interaction: discord.Interaction, user: discord.User = None):
    await interaction.response.defer(ephemeral=True)

    try:
        member = interaction.user
        is_staff = False

        # Check if user is staff (for viewing others' cooldowns)
        if user is not None:
            if not interaction.guild or not isinstance(interaction.user, discord.Member):
                await interaction.followup.send("Hiba: Guild context szükséges más játékos cooldownjának megtekintéséhez.", ephemeral=True)
                return
            is_staff = is_staff_member(interaction.user)

            if not is_staff:
                await interaction.followup.send("Nincs jogosultságod más játékos cooldownjának megtekintéséhez.", ephemeral=True)
                return

            target_member = user
        else:
            # Check own cooldown - check if banned first
            target_member = member

        # Check if player is banned from testing
        if WEBSITE_URL:
            try:
                player_name = target_member.display_name
                if hasattr(target_member, 'nick') and target_member.nick:
                    player_name = target_member.nick

                url = f"{WEBSITE_URL}/api/tests/ban?username={player_name}"
                timeout = aiohttp.ClientTimeout(total=5)
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=_auth_headers(), timeout=timeout) as resp:
                        if resp.status == 200:
                            ban_data = await resp.json()
                            if ban_data.get("banned"):
                                reason = ban_data.get("reason", "")
                                await interaction.followup.send(
                                    f"❌ **{player_name}** ki van tiltva a tesztelésből!\n" +
                                    (f"**Ok:** {reason}" if reason else "Nincs megadva ok."),
                                    ephemeral=True
                                )
                                return
            except Exception:
                pass  # If ban check fails, continue

        # Check local ban (bot-side)
        if is_player_banned(target_member.display_name):
            ban_info = get_ban_info(target_member.display_name)
            if ban_info:
                expires_at = ban_info.get("expires_at", 0)
                if expires_at == 0:
                    await interaction.followup.send(
                        f"❌ **{target_member.display_name}** örökre ki van tiltva a tesztelésből!\n"
                        f"**Ok:** {ban_info.get('reason', 'Nincs megadva')}",
                        ephemeral=True
                    )
                else:
                    from datetime import datetime
                    exp_date = datetime.fromtimestamp(expires_at)
                    await interaction.followup.send(
                        f"❌ **{target_member.display_name}** ki van tiltva!\n"
                        f"**Lejárat:** {exp_date.strftime('%Y-%m-%d %H:%M')}\n"
                        f"**Ok:** {ban_info.get('reason', 'Nincs megadva')}",
                        ephemeral=True
                    )
                return

        # Build cooldown info for all modes
        data = _load_data()
        cooldowns = data.get("cooldowns", {}).get(str(target_member.id), {})

        # April Fools' funny title
        display_name = target_member.display_name

        embed = discord.Embed(
            title=f"⏳ Cooldown info - {display_name}",
            color=discord.Color.blurple()
        )

        mode_cooldowns = []
        for label, mode_key, _ in TICKET_TYPES:
            last_closed = float(cooldowns.get(mode_key, 0))
            if last_closed <= 0:
                # April Fools' funny cooldown messages
                if APRIL_FOOLS_MODE and random.random() < 0.2:
                    funny_ready = [
                        f"🎪 **{label}**: A cirkusz nyitva!",
                        f"🤡 **{label}**: A bohóc vár!",
                        f"🎭 **{label}**: A színpad készen áll!",
                    ]
                    mode_cooldowns.append(random.choice(funny_ready))
                else:
                    mode_cooldowns.append(f"✅ **{label}**: Nincs cooldown")
            else:
                left = int((last_closed + COOLDOWN_SECONDS) - time.time())
                if left <= 0:
                    if APRIL_FOOLS_MODE and random.random() < 0.2:
                        funny_ready = [
                            f"🎪 **{label}**: A cirkusz nyitva!",
                            f"🤡 **{label}**: A bohóc vár!",
                            f"🎭 **{label}**: A színpad készen áll!",
                        ]
                        mode_cooldowns.append(random.choice(funny_ready))
                    else:
                        mode_cooldowns.append(f"✅ **{label}**: Kész vagy, már nyithatsz ticketet!")
                else:
                    days = left // (24 * 3600)
                    hours = (left % (24 * 3600)) // 3600
                    minutes = (left % 3600) // 60

                    if days > 0:
                        time_str = f"{days} nap {hours} óra"
                    elif hours > 0:
                        time_str = f"{hours} óra {minutes} perc"
                    else:
                        time_str = f"{minutes} perc"

                    # April Fools' funny cooldown display
                    if APRIL_FOOLS_MODE and random.random() < 0.15:
                        funny_cooldown = [
                            f"🎪 **{label}**: {time_str} (a cirkusz zárva!)",
                            f"🤡 **{label}**: {time_str} (a bohóc alszik!)",
                            f"🎭 **{label}**: {time_str} (a színház szünetel!)",
                        ]
                        mode_cooldowns.append(random.choice(funny_cooldown))
                    else:
                        mode_cooldowns.append(f"⏳ **{label}**: {time_str}")

        # Add global cooldown info
        global_last = data.get("cooldowns", {}).get(str(target_member.id), {}).get("_global", 0)
        if global_last > 0:
            left = int((global_last + COOLDOWN_SECONDS) - time.time())
            if left > 0:
                days = left // (24 * 3600)
                hours = (left % (24 * 3600)) // 3600
                mode_cooldowns.append(f"\n🌐 **Globális cooldown**: {days} nap {hours} óra")

        embed.description = "\n".join(mode_cooldowns)

        # April Fools' footer
        if APRIL_FOOLS_MODE:
            embed.set_footer(text=f"Cooldown időtartam: 14 nap | 🎪 {get_april_fools_message()}")
        else:
            embed.set_footer(text=f"Cooldown időtartam: 14 nap")

        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)
