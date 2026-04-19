import discord
from discord import app_commands

from shared_utils import *
from core_testing import lazy_command


@lazy_command(name="profile", description="Megnézed egy játékos tierjeit a tierlistáról.")
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
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=_auth_headers(), timeout=timeout) as resp:
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

                # Get global rank by fetching all tests and sorting
                all_url = f"{WEBSITE_URL}/api/tests"
                async with aiohttp.ClientSession() as session:
                    async with session.get(all_url, headers=_auth_headers(), timeout=timeout) as all_resp:
                        try:
                            all_data = await all_resp.json()
                        except Exception:
                            all_data = {}

                all_tests = all_data.get("tests", [])
                global_rank = None
                if all_tests:
                    # Group by username and sum points
                    player_totals = {}
                    for t in all_tests:
                        username = t.get("username", "")
                        points = t.get("points", 0)
                        if username in player_totals:
                            player_totals[username] += points
                        else:
                            player_totals[username] = points

                    # Sort by total points descending
                    sorted_players = sorted(player_totals.items(), key=lambda x: x[1], reverse=True)

                    # Find the player's position
                    player_username = tests[0].get("username", "")
                    player_total_points = player_totals.get(player_username, 0)

                    for idx, (name, pts) in enumerate(sorted_players, 1):
                        if name == player_username:
                            global_rank = idx
                            break

                # Build embed
                display_name = tests[0].get('username', name)

                embed = discord.Embed(
                    title=f"{display_name} profilja",
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
                    # April Fools' funny rank display
                    display_rank = get_funny_rank(r) if APRIL_FOOLS_MODE else r
                    mode_strs.append(f"**{m}**: {display_rank} ({p}pt)")

                embed.description = "\n".join(mode_strs)

                # Add rank info
                rank_info = f"**Összes pont:** {total_points}"
                if global_rank:
                    rank_info += f"\n**Globális rank:** #{global_rank}"

                # Add April Fools' message
                if APRIL_FOOLS_MODE:
                    rank_info += f"\n\n🎪 {get_april_fools_message()}"

                embed.add_field(name="Statisztika", value=rank_info, inline=False)

                # Skin
                skin_url = f"https://minotar.net/helm/{tests[0].get('username', name)}/128.png"
                embed.set_thumbnail(url=skin_url)

                await interaction.followup.send(embed=embed)

    except aiohttp.ClientError as e:
        await interaction.followup.send(f"⚠️ Web hiba: {type(e).__name__}: {e}", ephemeral=True)
    except asyncio.TimeoutError:
        await interaction.followup.send("⚠️ Web timeout (nem válaszolt 10 mp-en belül).", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


@lazy_command(name="porog", description="Kiválaszt egy véletlenszerű játékost a megadott gamemodból és tierből.")
@app_commands.describe(
    gamemode="A játékmód (pl. sword, pot, smp)",
    tier="A tier (pl. ht3, lt1)",
    sajat="Include self in roll (default: no)"
)
@app_commands.choices(
    gamemode=_choices_from_list(MODE_LIST),
    tier=_choices_from_list(RANKS)
)
async def porog(interaction: discord.Interaction, gamemode: app_commands.Choice[str], tier: app_commands.Choice[str], sajat: bool = False):
    await interaction.response.defer(ephemeral=False)

    try:
        if not is_staff_member(interaction.user):
            await interaction.followup.send("Nincs jogosultságod ehhez a parancshoz.", ephemeral=True)
            return

        if not WEBSITE_URL:
            await interaction.followup.send("⚠️ WEBSITE_URL nincs beállítva.", ephemeral=True)
            return

        # Try to exclude the ticket owner (unless sajat=True)
        exclude_user = None
        if not sajat:
            # Use Discord user's display name to exclude
            exclude_user = interaction.user.display_name.lower().replace(" ", "-")

        # Build URL with exclusion if we found someone
        url = f"{WEBSITE_URL}/api/tests?mode={gamemode.value}&tier={tier.value}"
        if exclude_user:
            url += f"&exclude={exclude_user}"

        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=_auth_headers(), timeout=timeout) as resp:
                try:
                    data = await resp.json()
                except Exception:
                    data = {}

                if resp.status != 200:
                    await interaction.followup.send(f"⚠️ Hiba a weboldal lekérésekor: {resp.status}", ephemeral=True)
                    return

                player = data.get("player")

                if not player:
                    await interaction.followup.send("❌ Nincs találat erre a gamemódra és tier-re.", ephemeral=False)
                    return

                username = player.get("username")
                rank = player.get("rank")

                # April Fools' funny porog embed
                if APRIL_FOOLS_MODE:
                    funny_titles = [
                        "🎪 Cirkuszi sorsolás",
                        "🤡 Bohóc sorsolás",
                        "🎭 Színházi sorsolás",
                        "🃏 Kártya sorsolás",
                    ]
                    title = random.choice(funny_titles)
                    display_rank = get_funny_rank(rank)
                else:
                    title = "🎲 Sorsolt játékos"
                    display_rank = rank

                embed = discord.Embed(
                    title=title,
                    description=f"**{username}** ({display_rank})",
                    color=discord.Color.gold()
                )

                skin_url = f"https://minotar.net/helm/{username}/128.png"
                embed.set_thumbnail(url=skin_url)

                # Add April Fools' message
                if APRIL_FOOLS_MODE and random.random() < 0.3:
                    embed.add_field(name="🎪 Áprilisi üzenet:", value=get_april_fools_message(), inline=False)

                await interaction.followup.send(embed=embed)

    except aiohttp.ClientError as e:
        await interaction.followup.send(f"⚠️ Web hiba: {type(e).__name__}: {e}", ephemeral=True)
    except asyncio.TimeoutError:
        await interaction.followup.send("⚠️ Web timeout (nem válaszolt 10 mp-en belül).", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


@lazy_command(name="tierlistnamechange", description="Játékos nevének megváltoztatása a tierlistán (admin csak)")
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

            # Also update linked_accounts in Supabase
            if USE_SUPABASE_API:
                try:
                    success = await supabase_update(
                        "linked_accounts",
                        {"minecraft_name": newname},
                        {"minecraft_name": oldname}
                    )
                    if success:
                        print(f"Updated linked_accounts: {oldname} -> {newname}")
                    else:
                        print(f"Warning: linked_accounts update returned False for {oldname} -> {newname}")
                except Exception as e:
                    print(f"Error updating linked_accounts: {e}")

            # April Fools' funny rename message
            if APRIL_FOOLS_MODE:
                funny_rename_messages = [
                    f"✅ Sikeresen átnevezve: **{oldname}** → **{newname}**\nFrissítve: {updated_count} db bejegyzés (összes gamemód)\n\n🎪 A cirkuszban is átneveztük!",
                    f"✅ Sikeresen átnevezve: **{oldname}** → **{newname}**\nFrissítve: {updated_count} db bejegyzés (összes gamemód)\n\n🤡 A bohóc is átnevezte!",
                    f"✅ Sikeresen átnevezve: **{oldname}** → **{newname}**\nFrissítve: {updated_count} db bejegyzés (összes gamemód)\n\n🎭 A színházban is átneveztük!",
                ]
                msg = random.choice(funny_rename_messages)
            else:
                msg = f"✅ Sikeresen átnevezve: **{oldname}** → **{newname}**\nFrissítve: {updated_count} db bejegyzés (összes gamemód)"

            await interaction.followup.send(msg, ephemeral=True)
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
            # Truncate data to avoid Discord's 2000 character limit
            data_str = truncate_message(str(data), 1500)
            await interaction.followup.send(
                f"⚠️ Hiba (status {status}): {data_str}",
                ephemeral=True
            )

    except aiohttp.ClientError as e:
        await interaction.followup.send(f"⚠️ Web hiba: {type(e).__name__}: {e}", ephemeral=True)
    except asyncio.TimeoutError:
        await interaction.followup.send("⚠️ Web timeout (nem válaszolt 10 mp-en belül).", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


@lazy_command(name="retire", description="Játékos nyugdíjazása egy gamemódban (admin csak, csak Tier 2).")
@app_commands.describe(
    name="A játékos neve a tierlistán",
    gamemode="A játékmód"
)
@app_commands.choices(
    gamemode=_choices_from_list(MODE_LIST)
)
async def retire(interaction: discord.Interaction, name: str, gamemode: app_commands.Choice[str]):
    await interaction.response.defer(ephemeral=True)

    try:
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("Nincs jogosultságod ehhez a parancshoz.", ephemeral=True)
            return

        if not WEBSITE_URL:
            await interaction.followup.send("⚠️ WEBSITE_URL nincs beállítva.", ephemeral=True)
            return

        # First, check the player's current rank to ensure they are Tier 2
        url = f"{WEBSITE_URL}/api/tests?username={name}&gamemode={gamemode.value}"
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=_auth_headers(), timeout=timeout) as resp:
                try:
                    data = await resp.json()
                except Exception:
                    data = {}

                if resp.status != 200:
                    await interaction.followup.send(f"⚠️ Hiba a weboldal lekérésekor: {resp.status}", ephemeral=True)
                    return

                test = data.get("test")
                if not test:
                    await interaction.followup.send(
                        f"❌ Játékos nem találva: **{name}** ezen a gamemódon ({gamemode.value}).",
                        ephemeral=True
                    )
                    return

                current_rank = test.get("rank", "")
                # Check if Tier 2
                if current_rank not in ["LT2", "HT2"]:
                    await interaction.followup.send(
                        f"❌ Csak Tier 2 (LT2/HT2) játékosok nyugdíjazhatók. **{name}** jelenleg: **{current_rank}**.",
                        ephemeral=True
                    )
                    return

        # Call the website API to retire (upsert with R prefix)
        retire_url = f"{WEBSITE_URL}/api/tests"
        payload = {
            "username": name,
            "gamemode": gamemode.value,
            "rank": f"R{current_rank}",
            "points": POINTS.get(current_rank, 0), # Keep same points
            "retired": True
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(retire_url, json=payload, headers=_auth_headers(), timeout=timeout) as retire_resp:
                try:
                    retire_data = await retire_resp.json()
                except Exception:
                    retire_data = {}

                if retire_resp.status == 200:
                    # April Fools' funny retire message
                    if APRIL_FOOLS_MODE:
                        funny_retire_messages = [
                            f"✅ Sikeres nyugdíjazás! **{name}** ({gamemode.value}) most **R{current_rank}**.\n\n🎪 A cirkuszba is nyugdíjaztuk!",
                            f"✅ Sikeres nyugdíjazás! **{name}** ({gamemode.value}) most **R{current_rank}**.\n\n🤡 A bohóc is nyugdíjazott!",
                            f"✅ Sikeres nyugdíjazás! **{name}** ({gamemode.value}) most **R{current_rank}**.\n\n🎭 A színházba is nyugdíjaztuk!",
                        ]
                        msg = random.choice(funny_retire_messages)
                    else:
                        msg = f"✅ Sikeres nyugdíjazás! **{name}** ({gamemode.value}) most **R{current_rank}**."

                    await interaction.followup.send(msg, ephemeral=True)
                else:
                    # Truncate retire_data to avoid Discord's 2000 character limit
                    retire_data_str = truncate_message(str(retire_data), 1500)
                    await interaction.followup.send(
                        f"⚠️ Hiba: {retire_resp.status} - {retire_data_str}",
                        ephemeral=True
                    )

    except aiohttp.ClientError as e:
        await interaction.followup.send(f"⚠️ Web hiba: {type(e).__name__}: {e}", ephemeral=True)
    except asyncio.TimeoutError:
        await interaction.followup.send("⚠️ Web timeout.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


@lazy_command(name="unretire", description="Játékos visszahozása nyugdíjból (admin csak).")
@app_commands.describe(
    name="A játékos neve a tierlistán",
    gamemode="A játékmód"
)
@app_commands.choices(
    gamemode=_choices_from_list(MODE_LIST)
)
async def unretire(interaction: discord.Interaction, name: str, gamemode: app_commands.Choice[str]):
    await interaction.response.defer(ephemeral=True)

    try:
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("Nincs jogosultságod ehhez a parancshoz.", ephemeral=True)
            return

        if not WEBSITE_URL:
            await interaction.followup.send("⚠️ WEBSITE_URL nincs beállítva.", ephemeral=True)
            return

        # First, get current rank to remove R prefix
        url = f"{WEBSITE_URL}/api/tests?username={name}&gamemode={gamemode.value}"
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=_auth_headers(), timeout=timeout) as resp:
                try:
                    data = await resp.json()
                except Exception:
                    data = {}

                if resp.status != 200:
                    await interaction.followup.send(f"⚠️ Hiba a weboldal lekérésekor: {resp.status}", ephemeral=True)
                    return

                test = data.get("test")
                if not test:
                    await interaction.followup.send(
                        f"❌ Játékos nem találva: **{name}** ezen a gamemódon ({gamemode.value}).",
                        ephemeral=True
                    )
                    return

                current_rank = test.get("rank", "")
                if not current_rank.startswith("R"):
                    await interaction.followup.send(
                        f"❌ A játékos nincs nyugdíjazva ebben a gamemódban.",
                        ephemeral=True
                    )
                    return

                original_rank = current_rank[1:] # Remove R prefix

        # Upsert back to original rank
        post_url = f"{WEBSITE_URL}/api/tests"
        payload = {
            "username": name,
            "gamemode": gamemode.value,
            "rank": original_rank,
            "points": POINTS.get(original_rank, 0)
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(post_url, json=payload, headers=_auth_headers(), timeout=timeout) as post_resp:
                try:
                    post_data = await post_resp.json()
                except Exception:
                    post_data = {}

                if post_resp.status == 200:
                    # April Fools' funny unretire message
                    if APRIL_FOOLS_MODE:
                        funny_unretire_messages = [
                            f"✅ Sikeres visszahozatal! **{name}** ({gamemode.value}) visszatért a tierlistára ({original_rank}).\n\n🎪 A cirkuszba is visszajött!",
                            f"✅ Sikeres visszahozatal! **{name}** ({gamemode.value}) visszatért a tierlistára ({original_rank}).\n\n🤡 A bohóc is visszajött!",
                            f"✅ Sikeres visszahozatal! **{name}** ({gamemode.value}) visszatért a tierlistára ({original_rank}).\n\n🎭 A színházba is visszajött!",
                        ]
                        msg = random.choice(funny_unretire_messages)
                    else:
                        msg = f"✅ Sikeres visszahozatal! **{name}** ({gamemode.value}) visszatért a tierlistára ({original_rank})."

                    await interaction.followup.send(msg, ephemeral=True)
                else:
                    # Truncate post_data to avoid Discord's 2000 character limit
                    post_data_str = truncate_message(str(post_data), 1500)
                    await interaction.followup.send(
                        f"⚠️ Hiba: {post_resp.status} - {post_data_str}",
                        ephemeral=True
                    )

    except aiohttp.ClientError as e:
        await interaction.followup.send(f"⚠️ Web hiba: {type(e).__name__}: {e}", ephemeral=True)
    except asyncio.TimeoutError:
        await interaction.followup.send("⚠️ Web timeout.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


@lazy_command(name="tierlistban", description="Játékos kitiltása a tesztelésből (admin csak).")
@app_commands.describe(
    name="A játékos neve a tierlistán",
    days="Kitiltás időtartama napokban (0 = örök ban)",
    reason="Kitiltás oka (opcionális)"
)
async def tierlistban(interaction: discord.Interaction, name: str, days: int, reason: str = ""):
    await interaction.response.defer(ephemeral=True)

    try:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("Hiba.", ephemeral=True)
            return
        if not is_staff_member(interaction.user):
            await interaction.followup.send("Nincs jogosultságod ehhez a parancshoz.", ephemeral=True)
            return

        # Check if already banned
        if is_player_banned(name):
            ban_info = get_ban_info(name)
            if ban_info:
                expires_at = ban_info.get("expires_at", 0)
                if expires_at == 0:
                    await interaction.followup.send(
                        f"❌ **{name}** már örökkitiltás alatt áll.",
                        ephemeral=True
                    )
                else:
                    from datetime import datetime
                    exp_date = datetime.fromtimestamp(expires_at)
                    await interaction.followup.send(
                        f"❌ **{name}** már kitiltva. Lejárat: {exp_date.strftime('%Y-%m-%d %H:%M')}",
                        ephemeral=True
                    )
            return

        # Ban the player in bot
        ban_player(name, days, reason)

        # Sync ban to website
        expires_at = 0 if days == 0 else int(time.time() + (days * 24 * 60 * 60))
        if WEBSITE_URL:
            await api_set_ban(username=name, banned=True, expires_at=expires_at, reason=reason)

        # Build response message
        if days == 0:
            msg = f"✅ **{name}** örökre ki lett tiltva a tesztelésből."
        else:
            msg = f"✅ **{name}** ki lett tiltva {days} napra a tesztelésből."

        if reason:
            msg += f"\n**Ok:** {reason}"

        # Add April Fools' message
        if APRIL_FOOLS_MODE:
            funny_ban_messages = [
                "\n\n🎪 A cirkuszból is kitiltottuk!",
                "\n\n🤡 A bohóc is elfelejtette!",
                "\n\n🎭 A színházból is kitiltottuk!",
                "\n\n🃏 A kártyákat is elvettük!",
            ]
            msg += random.choice(funny_ban_messages)

        await interaction.followup.send(msg, ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


@lazy_command(name="tierlistunban", description="Játékos visszavétele a tesztelésbe (admin csak).")
@app_commands.describe(
    name="A játékos neve a tierlistán"
)
async def tierlistunban(interaction: discord.Interaction, name: str):
    await interaction.response.defer(ephemeral=True)

    try:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("Hiba.", ephemeral=True)
            return
        if not is_staff_member(interaction.user):
            await interaction.followup.send("Nincs jogosultságod ehhez a parancshoz.", ephemeral=True)
            return

        # Check if actually banned
        if not is_player_banned(name):
            await interaction.followup.send(
                f"❌ **{name}** nincs kitiltva.",
                ephemeral=True
            )
            return

        # Unban from bot
        unban_player(name)

        # Sync unban to website
        if WEBSITE_URL:
            await api_set_ban(username=name, banned=False)

        # April Fools' funny unban message
        if APRIL_FOOLS_MODE:
            funny_unban_messages = [
                f"✅ **{name}** vissza lett engedve a tesztelésbe.\n\n🎪 A cirkuszba is visszajöhet!",
                f"✅ **{name}** vissza lett engedve a tesztelésbe.\n\n🤡 A bohóc is visszajöhet!",
                f"✅ **{name}** vissza lett engedve a tesztelésbe.\n\n🎭 A színházba is visszajöhet!",
                f"✅ **{name}** vissza lett engedve a tesztelésbe.\n\n🃏 A kártyákat is visszakapta!",
            ]
            msg = random.choice(funny_unban_messages)
        else:
            msg = f"✅ **{name}** vissza lett engedve a tesztelésbe."

        await interaction.followup.send(msg, ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


# Confirmation view for remove tierlist
class ConfirmRemoveView(discord.ui.View):
    def __init__(self, username: str, actual_username: str, moderator: discord.Member):
        super().__init__(timeout=60)
        self.username = username  # What the user typed
        self.actual_username = actual_username  # What's in the database
        self.moderator = moderator
        self.confirmed = False

    @discord.ui.button(label="Igen, törlöm", style=discord.ButtonStyle.danger, custom_id="confirm_remove_yes")
    async def confirm_yes(self, interaction: discord.Interaction, _button: discord.ui.Button):
        # Only the moderator who started the command can confirm
        if interaction.user.id != self.moderator.id:
            await interaction.response.send_message("❌ Csak a parancs indítója erősítheti meg.", ephemeral=True)
            return

        self.confirmed = True
        await interaction.response.defer()

        try:
            # Call the API to remove the player - use actual username from DB
            result = await api_remove_player(username=self.actual_username)
            status = result.get("status")
            data = result.get("data", {})

            if status == 200:
                removed_count = data.get("removedCount", 1)
                modes = data.get("modes", "")
                details = data.get("details", "")

                # Truncate if too long for embed
                desc = f"**{self.username}** sikeresen törölve lett a tierlistáról.\nMód: {modes}"
                if details:
                    if len(desc) + len(details) > 1500:
                        details = details[:1500 - len(desc)] + "..."
                    desc += f"\n{details}"

                # April Fools' funny remove message
                if APRIL_FOOLS_MODE:
                    funny_remove_messages = [
                        "\n\n🎪 A cirkuszból is eltávolítottuk!",
                        "\n\n🤡 A bohóc is elfelejtette!",
                        "\n\n🎭 A színházból is eltávolítottuk!",
                        "\n\n🃏 A kártyákat is elvettük!",
                    ]
                    desc += random.choice(funny_remove_messages)

                embed = discord.Embed(
                    title="✅ Játékos eltávolítva a tierlistáról",
                    description=desc,
                    color=discord.Color.green()
                )
                embed.set_footer(text=f"Moderátor: {self.moderator.display_name}")

                await interaction.followup.send(embed=embed)
            else:
                error_msg = data.get("error", "Ismeretlen hiba")
                # Truncate error_msg to avoid Discord's 2000 character limit
                error_msg_str = truncate_message(str(error_msg), 1500)
                await interaction.followup.send(
                    f"❌ Hiba a törléskor: {error_msg_str}",
                    ephemeral=True
                )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Hiba: {type(e).__name__}: {e}",
                ephemeral=True
            )

        self.stop()

    @discord.ui.button(label="Mégse", style=discord.ButtonStyle.secondary, custom_id="confirm_remove_no")
    async def confirm_no(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Only the moderator who started the command can cancel
        if interaction.user.id != self.moderator.id:
            await interaction.response.send_message("❌ Csak a parancs indítója mondhat le.", ephemeral=True)
            return

        await interaction.response.send_message("❌ Törlés megszüntetve.", ephemeral=True)
        self.stop()


@lazy_command(name="removetierlist", description="Játékos eltávolítása a tierlistáról (admin csak, DANGER!)")
@app_commands.describe(
    name="A játékos neve a tierlistán (Minecraft név)"
)
async def removetierlist(interaction: discord.Interaction, name: str):
    await interaction.response.defer(ephemeral=True)

    try:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("Hiba.", ephemeral=True)
            return
        if not is_staff_member(interaction.user):
            await interaction.followup.send("Nincs jogosultságod ehhez a parancshoz.", ephemeral=True)
            return

        if not WEBSITE_URL:
            await interaction.followup.send("⚠️ WEBSITE_URL nincs beállítva.", ephemeral=True)
            return

        # First, check if the player exists in the tierlist (case-sensitive)
        url = f"{WEBSITE_URL}/api/tests?username={name}"
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=_auth_headers(), timeout=timeout) as resp:
                try:
                    data = await resp.json()
                except Exception:
                    data = {}

                if resp.status != 200:
                    await interaction.followup.send(f"⚠️ Hiba a weboldal lekérésekor: {resp.status}", ephemeral=True)
                    return

                tests = data.get("tests", [])

                # Filter for exact case-sensitive match
                exact_match_tests = [t for t in tests if t.get("username", "") == name]

                # If no exact match, check if there's a similar name with different case
                if not exact_match_tests:
                    similar = [t for t in tests if t.get("username", "").lower() == name.lower()]
                    if similar:
                        similar_names = ", ".join([f"`{t.get('username')}`" for t in similar])
                        await interaction.followup.send(
                            f"❌ **{name}** nincs a tierlistán.\n\n"
                            f"Hasonló név(ek) talált: {similar_names}\n"
                            f"Kérlek írd be a pontos nevet (a nagybetűk számítanak)!",
                            ephemeral=True
                        )
                    else:
                        await interaction.followup.send(
                            f"❌ **{name}** nincs a tierlistán.",
                            ephemeral=True
                        )
                    return

                # Use exact match
                tests = exact_match_tests
                actual_username = tests[0].get("username", "")

            # Show info about the player (limit to 1500 chars to avoid embed limits)
            modes_info = "\n".join([f"• **{t.get('gamemode', '?')}**: {t.get('rank', '?')} ({t.get('points', 0)}pt)" for t in tests])
            if len(modes_info) > 1500:
                modes_info = modes_info[:1500] + "\n... (több is van)"

        # Create confirmation embed
        embed = discord.Embed(
            title="⚠️ FIGYELMEZTETÉS - Törlés előtt!",
            description=f"Biztosan eltávolítod **{name}**-t a tierlistáról?\n\n"
                        f"**Jelenlegi tierlist bejegyzések:**\n{modes_info}\n\n"
                        f"❗ **EZ EGY VÉGÉGES MŰVELET!** A játékos minden gamemód-beli eredménye törlésre kerül.",
            color=discord.Color.red()
        )
        embed.set_footer(text=f"Kéri: {interaction.user.display_name}")

        # Send confirmation view
        view = ConfirmRemoveView(username=name, actual_username=name, moderator=interaction.user)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    except aiohttp.ClientError as e:
        await interaction.followup.send(f"⚠️ Web hiba: {type(e).__name__}: {e}", ephemeral=True)
    except asyncio.TimeoutError:
        await interaction.followup.send("⚠️ Web timeout (nem válaszolt 10 mp-en belül).", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


@lazy_command(name="bulkimport", description="Bulk import test results from file (admin only)")
@app_commands.describe(
    file="Text file with test results (one per line: username mode rank)"
)
async def bulkimport(interaction: discord.Interaction, file: discord.Attachment):
    """Bulk import test results from a text file - format: username mode rank (one per line)"""
    await interaction.response.defer(ephemeral=True)

    # Check if admin
    if not interaction.user.guild_permissions.administrator:
        await interaction.followup.send("Nincs jogosultságod ehhez.", ephemeral=True)
        return

    if not WEBSITE_URL:
        await interaction.followup.send("⚠️ WEBSITE_URL nincs beállítva.", ephemeral=True)
        return

    # Read file content
    try:
        content = await file.read()
        data = content.decode('utf-8')
    except Exception as e:
        await interaction.followup.send(f"❌ Hiba a fájl olvasásakor: {e}", ephemeral=True)
        return

    lines = data.strip().split('\n')
    success_count = 0
    error_count = 0
    errors = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        parts = line.split()
        if len(parts) < 3:
            error_count += 1
            errors.append(f"Invalid format: {line}")
            continue

        username = parts[0]
        mode = parts[1].lower()
        rank = parts[2].upper()

        # Get proper display name for mode
        mode_display = get_gamemode_display_name(mode)

        # Get tester (use bot as tester)
        tester = interaction.user

        try:
            save = await api_post_test(username=username, mode=mode_display, rank=rank, tester=tester)
            if save.get("status") in [200, 201]:
                success_count += 1
            else:
                error_count += 1
                errors.append(f"Failed: {username} {mode} {rank}")
        except Exception as e:
            error_count += 1
            errors.append(f"Error: {username} - {str(e)[:50]}")

    result_msg = f"✅ Sikeres import: {success_count}\n❌ Sikertelen: {error_count}"
    if errors:
        result_msg += "\n\nHibák:\n" + "\n".join(errors[:10])
        if len(errors) > 10:
            result_msg += f"\n... és még {len(errors) - 10} hiba"

    # Add April Fools' message
    if APRIL_FOOLS_MODE:
        funny_import_messages = [
            "\n\n🎪 A cirkuszba is importáltuk!",
            "\n\n🤡 A bohóc is importált!",
            "\n\n🎭 A színházba is importáltuk!",
            "\n\n🃏 A kártyákat is importáltuk!",
        ]
        result_msg += random.choice(funny_import_messages)

    await interaction.followup.send(result_msg, ephemeral=True)


@lazy_command(name="link", description="Összekapcsolod a Minecraft fiókodat a Discord fiókoddal.")
@app_commands.describe(
    code="A Minecraftban kapott összekapcsolási kód (opcionális, ha még nincs kódod)"
)
async def link(interaction: discord.Interaction, code: str = None):
    await interaction.response.defer(ephemeral=True)

    # If no code provided (or empty), or if code doesn't belong to user, generate a new one
    code_valid = False
    if code and code != "":
        code_valid = await validate_link_code_for_user(interaction.user.id, code)

    if code is None or code == "" or not code_valid:
        try:
            # Check if user is already linked (try async first, then sync fallback)
            existing_link = get_linked_minecraft_name(interaction.user.id)
            if existing_link:
                # April Fools' funny link message
                if APRIL_FOOLS_MODE:
                    funny_descriptions = [
                        f"**Minecraft:** `{existing_link}`\n**Discord:** {interaction.user.mention}\n\n🎪 A cirkusz már össze van kapcsolva!",
                        f"**Minecraft:** `{existing_link}`\n**Discord:** {interaction.user.mention}\n\n🤡 A bohóc már össze van kapcsolva!",
                        f"**Minecraft:** `{existing_link}`\n**Discord:** {interaction.user.mention}\n\n🎭 A színház már össze van kapcsolva!",
                    ]
                    description = random.choice(funny_descriptions)
                else:
                    description = f"**Minecraft:** `{existing_link}`\n**Discord:** {interaction.user.mention}\n\nA kettős fiók már össze van kapcsolva!"
                embed = discord.Embed(
                    title="⚠️ Már össze van kapcsolva!",
                    description=description,
                    color=discord.Color.orange()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Check if user already has a pending code - if so, remove it and generate new one
            existing_code = await get_pending_link_code_async(interaction.user.id)
            if existing_code:
                embed = discord.Embed(
                    title="⏳ Már van egy kódod!",
                    description=f"A meglévő kódod: `{existing_code}`\n\n"
                                f"**Minecraft szerver:** `45.140.164.183:25942`\n"
                                f"Ezt használd: `/link {existing_code}` a Minecraftban!\n"
                                f"Vagy várd meg amíg lejár és generálj újat.",
                    color=discord.Color.orange()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Generate new code
            new_code = await generate_link_code_async(interaction.user.id)

            # Send code via DM
            try:
                await interaction.user.send(
                    f"🎮 **Összekapcsolási kód:** `{new_code}`\n\n"
                    f"**Minecraft szerver:** `45.140.164.183:25942`\n"
                    f"Írd be a Minecraftban: `/link {new_code}`\n"
                    f"A kód {LINK_CODE_EXPIRY_MINUTES} percig érvényes."
                )
                dm_sent = True
            except:
                dm_sent = False

            # April Fools' funny link code embed
            if APRIL_FOOLS_MODE:
                funny_titles = [
                    "🎪 Cirkuszi kód generálva!",
                    "🤡 Bohóc kód generálva!",
                    "🎭 Színházi kód generálva!",
                    "🃏 Kártya kód generálva!",
                ]
                title = random.choice(funny_titles)
            else:
                title = "✅ Kód generálva!"

            embed = discord.Embed(
                title=title,
                description=f"```\n{new_code}\n```\n"
                            f"**Minecraft szerver:** `45.140.164.183:25942`\n"
                            f"Írd be a Minecraftban: `/link {new_code}`\n"
                            f"A kód **{LINK_CODE_EXPIRY_MINUTES} percig** érvényes.",
                color=discord.Color.green()
            )
            if dm_sent:
                embed.add_field(
                    name="📬 DM elküldve!",
                    value="A kódot elküldtem privát üzenetben is!",
                    inline=False
                )
            else:
                embed.add_field(
                    name="⚠️ DM nem sikerült",
                    value="A kód itt látható, másold ki!",
                    inline=False
                )

            # Add April Fools' message
            if APRIL_FOOLS_MODE and random.random() < 0.3:
                embed.add_field(name="🎪 Áprilisi üzenet:", value=get_april_fools_message(), inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        except Exception as e:
            # Log the error for debugging
            print(f"[LINK ERROR] {type(e).__name__}: {e}")
            await interaction.followup.send(
                f"❌ Hiba történt. Kérlek, próbáld újra!\n"
                f"Ha a hiba továbbra is fennáll, jelentsd a hibát.",
                ephemeral=True
            )
            return

    # If code IS provided and valid - show success!
    if code_valid:
        linked_name = get_linked_minecraft_name(interaction.user.id)
        embed = discord.Embed(
            title="✅ Fiók összekapcsolva!",
            description=f"**Minecraft:** `{linked_name}`\n"
                        f"**Discord:** {interaction.user.mention}\n\n"
                        f"A fiókok sikeresen össze lettek kapcsolva!",
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    # Code was provided but is invalid
    await interaction.followup.send(
        "❌ Érvénytelen kód!\n"
        f"Használd `/link` parancsot új kód generálásához.",
        ephemeral=True
    )


@lazy_command(name="unlink", description="Leválasztod a Minecraft fiókodat a Discord fiókodról.")
async def unlink(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    try:
        # Check if linked
        existing = get_linked_minecraft_name(interaction.user.id)
        if not existing:
            await interaction.followup.send(
                "❌ Nincs összekapcsolva Minecraft fiók!\n"
                "Használd: `/link <név>` hogy összekapcsold.",
                ephemeral=True
            )
            return

        # Unlink
        unlink_minecraft_account(interaction.user.id)

        # April Fools' funny unlink embed
        if APRIL_FOOLS_MODE:
            funny_titles = [
                "🎪 Cirkuszi leválasztás sikeres!",
                "🤡 Bohóc leválasztás sikeres!",
                "🎭 Színházi leválasztás sikeres!",
                "🃏 Kártya leválasztás sikeres!",
            ]
            title = random.choice(funny_titles)
        else:
            title = "✅ Sikeres leválasztás!"

        embed = discord.Embed(
            title=title,
            description=f"A Minecraft fiókod (**{existing}**) le lett választva a Discord fiókodról.",
            color=discord.Color.green()
        )

        # Add April Fools' message
        if APRIL_FOOLS_MODE and random.random() < 0.3:
            embed.add_field(name="🎪 Áprilisi üzenet:", value=get_april_fools_message(), inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)


@lazy_command(name="mylink", description="Megnézed az összekapcsolt Minecraft fiókodat.")
async def mylink(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    try:
        linked = get_linked_minecraft_name(interaction.user.id)

        if not linked:
            await interaction.followup.send(
                "❌ Nincs összekapcsolva Minecraft fiók!\n"
                "Használd: `/link <név>` hogy összekapcsold.",
                ephemeral=True
            )
            return

        # April Fools' funny mylink embed
        if APRIL_FOOLS_MODE:
            funny_titles = [
                "🎪 Cirkuszi fiók",
                "🤡 Bohóc fiók",
                "🎭 Színházi fiók",
                "🃏 Kártya fiók",
            ]
            title = random.choice(funny_titles)
        else:
            title = "📋 Összekapcsolt fiók"

        embed = discord.Embed(
            title=title,
            description=f"**Discord:** {interaction.user.mention}\n"
                        f"**Minecraft:** {linked}",
            color=discord.Color.blurple()
        )

        # Add April Fools' message
        if APRIL_FOOLS_MODE and random.random() < 0.3:
            embed.add_field(name="🎪 Áprilisi üzenet:", value=get_april_fools_message(), inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)