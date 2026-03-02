import discord
from discord.ext import commands
from discord import app_commands
import random
import os
import time

TOKEN = os.getenv("TOKEN")

PUBLIC_VC_ID = 1271597939730550885
CLOSED_VC_ID = 1331233909224247357

CODE_ROLE_ID = 1434466837243887687
WHITELIST_ROLE_ID = 1478003169232683008
BLACKLIST_ROLE_ID = 1478003080745451731

DAY_SECONDS = 86400

intents = discord.Intents.default()
intents.members = True
intents.voice_states = True
intents.guilds = True
intents.message_content = True


class Bot(commands.Bot):

    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print("Commands synced")


bot = Bot()

current_players = []
match_counter = 0

player_stats = {}


def is_whitelisted(member):
    return discord.utils.get(member.roles, id=WHITELIST_ROLE_ID)


def is_blacklisted(member):
    return discord.utils.get(member.roles, id=BLACKLIST_ROLE_ID)


def has_code_role(member):
    return discord.utils.get(member.roles, id=CODE_ROLE_ID)


def clean_old(user_id):

    if user_id not in player_stats:
        return

    now = time.time()

    player_stats[user_id]["plays"] = [
        t for t in player_stats[user_id]["plays"]
        if now - t < DAY_SECONDS
    ]


def get_wait(user_id):

    if user_id not in player_stats:
        return match_counter

    return match_counter - player_stats[user_id]["last"]


def get_hours(user_id):

    if user_id not in player_stats:
        return 999

    if not player_stats[user_id]["plays"]:
        return 999

    return (time.time() - player_stats[user_id]["plays"][-1]) / 3600


def get_public(guild):

    vc = guild.get_channel(PUBLIC_VC_ID)

    result = []

    for m in vc.members:

        if m.bot:
            continue

        if is_blacklisted(m):
            continue

        if is_whitelisted(m):
            continue

        result.append(m)

    return result


@bot.event
async def on_ready():
    print("BotMaz ready")


@bot.event
async def on_voice_state_update(member, before, after):

    if member.bot:
        return

    guild = member.guild

    public_vc = guild.get_channel(PUBLIC_VC_ID)
    closed_vc = guild.get_channel(CLOSED_VC_ID)

    code_role = guild.get_role(CODE_ROLE_ID)

    if is_whitelisted(member):

        if member.voice and member.voice.channel != closed_vc:

            try:
                await member.move_to(closed_vc)
            except:
                pass

        if code_role not in member.roles:

            try:
                await member.add_roles(code_role)
            except:
                pass

        return

    if before.channel == closed_vc and after.channel != closed_vc:

        if has_code_role(member):

            try:
                await member.remove_roles(code_role)
            except:
                pass


# SAFE SEND FUNCTION
async def safe_send(interaction, text):

    chunks = [text[i:i+1900] for i in range(0, len(text), 1900)]

    for i, chunk in enumerate(chunks):

        if i == 0:
            await interaction.followup.send(chunk)
        else:
            await interaction.followup.send(chunk)


@bot.tree.command(name="queue")
async def queue(interaction: discord.Interaction):

    await interaction.response.defer()

    players = get_public(interaction.guild)

    msg = "Queue:\n\n"

    for p in players:

        uid = p.id

        wait = get_wait(uid)
        hours = get_hours(uid)

        msg += f"{p.display_name} | waited {wait} matches | {hours:.1f}h\n"

    await safe_send(interaction, msg)


@bot.tree.command(name="pick")
async def pick(interaction: discord.Interaction, amount: int):

    global current_players
    global match_counter

    await interaction.response.defer()

    guild = interaction.guild

    public_vc = guild.get_channel(PUBLIC_VC_ID)
    closed_vc = guild.get_channel(CLOSED_VC_ID)

    code_role = guild.get_role(CODE_ROLE_ID)

    match_counter += 1

    # move old players back safely
    for m in current_players:

        if is_whitelisted(m):
            continue

        try:

            if has_code_role(m):
                await m.remove_roles(code_role)

            if m.voice and m.voice.channel:
                await m.move_to(public_vc)

        except:
            pass

    eligible = get_public(guild)

    scored = []

    for p in eligible:

        uid = p.id

        clean_old(uid)

        wait = get_wait(uid)
        hours = get_hours(uid)

        score = wait*10 + hours*2 + random.uniform(0, 5)

        scored.append((p, score, wait, hours))

    scored.sort(key=lambda x: x[1], reverse=True)

    picked = scored[:amount]

    current_players = [x[0] for x in picked]

    msg = f"Match {match_counter}\n\n"

    now = time.time()

    for player, score, wait, hours in picked:

        uid = player.id

        if uid not in player_stats:

            player_stats[uid] = {

                "plays": [],
                "last": 0

            }

        player_stats[uid]["plays"].append(now)
        player_stats[uid]["last"] = match_counter

        try:

            await player.add_roles(code_role)

            if player.voice and player.voice.channel:
                await player.move_to(closed_vc)

        except:
            pass

        msg += f"{player.display_name} | waited {wait} matches | {hours:.1f}h\n"

    await safe_send(interaction, msg)


@bot.tree.command(name="reset")
async def reset(interaction: discord.Interaction):

    await interaction.response.defer()

    guild = interaction.guild

    public_vc = guild.get_channel(PUBLIC_VC_ID)

    code_role = guild.get_role(CODE_ROLE_ID)

    removed = 0
    moved = 0

    for m in guild.members:

        if m.bot:
            continue

        if is_whitelisted(m):
            continue

        try:

            if has_code_role(m):

                await m.remove_roles(code_role)
                removed += 1

            if m.voice and m.voice.channel:

                await m.move_to(public_vc)
                moved += 1

        except:
            pass

    await interaction.followup.send(

        f"Reset complete\n"
        f"Removed roles: {removed}\n"
        f"Moved users: {moved}"

    )


bot.run(TOKEN)
