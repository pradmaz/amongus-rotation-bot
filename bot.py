import discord
from discord.ext import commands
from discord import app_commands
import random
import os
import time

# ========================
# CONFIG
# ========================

TOKEN = os.getenv("TOKEN")

PUBLIC_VC_ID = 1271597939730550885
CLOSED_VC_ID = 1331233909224247357

CODE_ROLE_ID = 1434466837243887687
WHITELIST_ROLE_ID = 1478003169232683008
BLACKLIST_ROLE_ID = 1478003080745451731

DAY_SECONDS = 86400

# ========================
# INTENTS
# ========================

intents = discord.Intents.default()
intents.members = True
intents.voice_states = True
intents.guilds = True

# ========================
# BOT
# ========================

class Bot(commands.Bot):

    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()

bot = Bot()

# ========================
# DATA
# ========================

current_players = []
match_counter = 0

player_stats = {}

# structure:
# player_stats[user_id] =
# {
#   "plays": [timestamps],
#   "last_match": int
# }

# ========================
# HELPERS
# ========================

def is_whitelisted(member):
    return discord.utils.get(member.roles, id=WHITELIST_ROLE_ID)

def is_blacklisted(member):
    return discord.utils.get(member.roles, id=BLACKLIST_ROLE_ID)

def has_code_role(member):
    return discord.utils.get(member.roles, id=CODE_ROLE_ID)

def clean_old_plays(user_id):

    now = time.time()

    if user_id not in player_stats:
        return

    player_stats[user_id]["plays"] = [
        t for t in player_stats[user_id]["plays"]
        if now - t <= DAY_SECONDS
    ]

def get_wait_matches(user_id):

    if user_id not in player_stats:
        return match_counter

    last = player_stats[user_id]["last_match"]

    if last == 0:
        return match_counter

    return match_counter - last

def get_hours_since_last(user_id):

    if user_id not in player_stats:
        return 999

    plays = player_stats[user_id]["plays"]

    if not plays:
        return 999

    return (time.time() - plays[-1]) / 3600

def get_priority_text(wait):

    if wait >= 5:
        return "HIGHEST"
    elif wait >= 3:
        return "HIGH"
    elif wait >= 2:
        return "MEDIUM"
    else:
        return "LOW"

# ========================
# READY
# ========================

@bot.event
async def on_ready():
    print("BotMaz ready")

# ========================
# VOICE UPDATE
# ========================

@bot.event
async def on_voice_state_update(member, before, after):

    if member.bot:
        return

    guild = member.guild

    public_vc = guild.get_channel(PUBLIC_VC_ID)
    closed_vc = guild.get_channel(CLOSED_VC_ID)

    code_role = guild.get_role(CODE_ROLE_ID)

    if is_whitelisted(member):

        if after.channel == public_vc:

            await member.move_to(closed_vc)

        if code_role not in member.roles:
            await member.add_roles(code_role)

        return

    if before.channel == closed_vc and after.channel != closed_vc:

        if code_role in member.roles:
            await member.remove_roles(code_role)

# ========================
# GET ELIGIBLE
# ========================

def get_public_players(guild):

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

# ========================
# QUEUE COMMAND
# ========================

@bot.tree.command(name="queue", description="Show queue with fairness stats")

async def queue(interaction: discord.Interaction):

    players = get_public_players(interaction.guild)

    if not players:

        await interaction.response.send_message("Queue empty")
        return

    msg = "Queue:\n\n"

    for p in players:

        uid = p.id

        wait = get_wait_matches(uid)

        hours = get_hours_since_last(uid)

        priority = get_priority_text(wait)

        if hours == 999:
            hours_text = "Never played"
        else:
            hours_text = f"{hours:.1f}h ago"

        msg += (
            f"{p.display_name} — "
            f"Waited {wait} matches | "
            f"Last played: {hours_text} | "
            f"Priority: {priority}\n"
        )

    await interaction.response.send_message(msg)

# ========================
# PICK WITH WEIGHTED FAIRNESS
# ========================

@bot.tree.command(name="pick")

async def pick(interaction: discord.Interaction, amount: int):

    global match_counter
    global current_players

    await interaction.response.defer()

    guild = interaction.guild

    public_vc = guild.get_channel(PUBLIC_VC_ID)
    closed_vc = guild.get_channel(CLOSED_VC_ID)

    code_role = guild.get_role(CODE_ROLE_ID)

    match_counter += 1

    # move old players back
    for m in current_players:

        if is_whitelisted(m):
            continue

        await m.remove_roles(code_role)
        await m.move_to(public_vc)

    eligible = get_public_players(guild)

    if not eligible:

        await interaction.followup.send("No eligible players")
        return

    # calculate weighted scores
    scored = []

    for p in eligible:

        uid = p.id

        wait = get_wait_matches(uid)

        hours = get_hours_since_last(uid)

        score = (
            wait * 10 +
            hours * 2 +
            random.uniform(0, 5)
        )

        scored.append((p, score, wait, hours))

    scored.sort(key=lambda x: x[1], reverse=True)

    picked = scored[:amount]

    current_players = [p[0] for p in picked]

    msg = f"Match #{match_counter}\n\nPicked players:\n\n"

    for player, score, wait, hours in picked:

        uid = player.id

        if uid not in player_stats:
            player_stats[uid] = {"plays": [], "last_match": 0}

        clean_old_plays(uid)

        player_stats[uid]["plays"].append(time.time())
        player_stats[uid]["last_match"] = match_counter

        await player.add_roles(code_role)
        await player.move_to(closed_vc)

        reason = (
            f"Waited {wait} matches, "
            f"{hours:.1f}h since last match, "
            f"Fairness score {score:.1f}"
        )

        msg += f"{player.display_name} — {reason}\n"

    await interaction.followup.send(msg)

# ========================
# RESET
# ========================

@bot.tree.command(name="reset")

async def reset(interaction: discord.Interaction):

    guild = interaction.guild

    public_vc = guild.get_channel(PUBLIC_VC_ID)
    closed_vc = guild.get_channel(CLOSED_VC_ID)

    code_role = guild.get_role(CODE_ROLE_ID)

    removed = 0

    for m in guild.members:

        if is_whitelisted(m):
            continue

        if has_code_role(m):

            await m.remove_roles(code_role)
            removed += 1

    for m in closed_vc.members:

        if is_whitelisted(m):
            continue

        await m.move_to(public_vc)

    await interaction.response.send_message(
        f"Reset complete. Removed role from {removed} users."
    )

# ========================
# RUN
# ========================

bot.run(TOKEN)
