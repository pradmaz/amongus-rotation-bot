import discord
from discord.ext import commands
from discord import app_commands
import random
import os
import time

# ========================
# CONFIGURATION
# ========================

TOKEN = os.getenv("TOKEN")

PUBLIC_VC_ID = 1271597939730550885
CLOSED_VC_ID = 1331233909224247357

CODE_ROLE_ID = 1434466837243887687
WHITELIST_ROLE_ID = 1478003169232683008
BLACKLIST_ROLE_ID = 1478003080745451731

DAY_SECONDS = 86400  # 24 hours rolling window

# ========================
# INTENTS
# ========================

intents = discord.Intents.default()
intents.members = True
intents.voice_states = True
intents.guilds = True
intents.message_content = True

# ========================
# BOT CLASS
# ========================

class Bot(commands.Bot):

    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents
        )

    async def setup_hook(self):
        await self.tree.sync()
        print("Global commands synced")

bot = Bot()

# ========================
# MATCH TRACKING
# ========================

current_players = []
match_counter = 0

# player_stats structure:
# {
#   user_id: {
#       "plays": [timestamps in last 24h],
#       "last_match": match_number
#   }
# }
player_stats = {}

# ========================
# ROLE HELPERS
# ========================

def is_whitelisted(member):
    return discord.utils.get(member.roles, id=WHITELIST_ROLE_ID) is not None

def is_blacklisted(member):
    return discord.utils.get(member.roles, id=BLACKLIST_ROLE_ID) is not None

def has_code_role(member):
    return discord.utils.get(member.roles, id=CODE_ROLE_ID) is not None

# ========================
# READY EVENT
# ========================

@bot.event
async def on_ready():
    print(f"BotMaz online as {bot.user}")

# ========================
# VOICE STATE UPDATE
# ========================

@bot.event
async def on_voice_state_update(member, before, after):

    if member.bot:
        return

    guild = member.guild

    public_vc = guild.get_channel(PUBLIC_VC_ID)
    closed_vc = guild.get_channel(CLOSED_VC_ID)

    code_role = guild.get_role(CODE_ROLE_ID)

    # WHITELIST: Always stay in closed VC
    if is_whitelisted(member):

        if after.channel == public_vc:

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

    # NORMAL PLAYER: remove role if leaving closed VC
    if before.channel == closed_vc and after.channel != closed_vc:

        if has_code_role(member):

            try:
                await member.remove_roles(code_role)
            except:
                pass

# ========================
# GET PUBLIC PLAYERS
# ========================

def get_public_players(guild):

    public_vc = guild.get_channel(PUBLIC_VC_ID)

    players = []

    for member in public_vc.members:

        if member.bot:
            continue

        if is_blacklisted(member):
            continue

        if is_whitelisted(member):
            continue

        players.append(member)

    return players

# ========================
# QUEUE COMMAND
# ========================

@bot.tree.command(name="queue", description="Show queue")

async def queue_cmd(interaction: discord.Interaction):

    players = get_public_players(interaction.guild)

    if not players:

        await interaction.response.send_message("Queue empty.")
        return

    msg = "Queue:\n\n"

    for p in players:
        msg += f"{p.display_name}\n"

    msg += f"\nTotal: {len(players)} players"

    await interaction.response.send_message(msg)

# ========================
# PICK COMMAND
# ========================

@bot.tree.command(name="pick", description="Pick players fairly")
@app_commands.describe(amount="Number of players")

async def pick_cmd(interaction: discord.Interaction, amount: int):

    global current_players
    global match_counter
    global player_stats

    await interaction.response.defer()

    guild = interaction.guild

    public_vc = guild.get_channel(PUBLIC_VC_ID)
    closed_vc = guild.get_channel(CLOSED_VC_ID)

    code_role = guild.get_role(CODE_ROLE_ID)

    match_counter += 1

    # ========================
    # MOVE WHITELIST TO CLOSED VC
    # ========================

    whitelist_moved = 0

    for member in public_vc.members:

        if member.bot:
            continue

        if is_whitelisted(member):

            if not has_code_role(member):

                try:
                    await member.add_roles(code_role)
                except:
                    pass

            try:
                await member.move_to(closed_vc)
                whitelist_moved += 1
            except:
                pass

    # ========================
    # MOVE OLD PLAYERS BACK
    # ========================

    for member in current_players:

        if is_whitelisted(member):
            continue

        try:
            await member.remove_roles(code_role)
        except:
            pass

        try:
            await member.move_to(public_vc)
        except:
            pass

    # ========================
    # PICK NEW PLAYERS
    # ========================

    eligible = get_public_players(guild)

    if not eligible:

        await interaction.followup.send("No eligible players.")
        return

    if amount > len(eligible):
        amount = len(eligible)

    picked = random.sample(eligible, amount)

    current_players = picked.copy()

    result_lines = []

    now = time.time()

    for member in picked:

        try:
            await member.add_roles(code_role)
        except:
            pass

        try:
            await member.move_to(closed_vc)
        except:
            pass

        uid = member.id

        if uid not in player_stats:

            player_stats[uid] = {
                "plays": [],
                "last_match": 0
            }

        # Remove plays older than 24h
        player_stats[uid]["plays"] = [
            t for t in player_stats[uid]["plays"]
            if now - t <= DAY_SECONDS
        ]

        plays_count = len(player_stats[uid]["plays"])

        last_match = player_stats[uid]["last_match"]

        wait = (
            None
            if last_match == 0
            else match_counter - last_match
        )

        # Add new play
        player_stats[uid]["plays"].append(now)
        player_stats[uid]["last_match"] = match_counter

        wait_text = (
            "First match"
            if wait is None
            else f"Waited {wait} matches"
        )

        result_lines.append(
            f"{member.display_name} — Played {plays_count+1} in last 24h | {wait_text}"
        )

    msg = (
        f"Match #{match_counter}\n\n"
        f"Whitelist moved: {whitelist_moved}\n"
        f"Picked {len(picked)} players:\n\n"
        + "\n".join(result_lines)
    )

    await interaction.followup.send(msg)

# ========================
# RESET COMMAND
# ========================

@bot.tree.command(name="reset", description="Reset lobby safely")

async def reset_cmd(interaction: discord.Interaction):

    guild = interaction.guild

    public_vc = guild.get_channel(PUBLIC_VC_ID)
    closed_vc = guild.get_channel(CLOSED_VC_ID)

    code_role = guild.get_role(CODE_ROLE_ID)

    removed = 0
    moved = 0

    for member in guild.members:

        if member.bot:
            continue

        if is_whitelisted(member):
            continue

        if has_code_role(member):

            try:
                await member.remove_roles(code_role)
                removed += 1
            except:
                pass

    for member in closed_vc.members:

        if member.bot:
            continue

        if is_whitelisted(member):
            continue

        try:
            await member.move_to(public_vc)
            moved += 1
        except:
            pass

    await interaction.response.send_message(
        f"Reset complete\n"
        f"Roles removed: {removed}\n"
        f"Users moved: {moved}\n"
        f"Whitelist untouched"
    )

# ========================
# RUN BOT
# ========================

bot.run(TOKEN)
