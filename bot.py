import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import time
from collections import defaultdict
import os

TOKEN = os.getenv("TOKEN")

GUILD_ID = 844092170524688394

PUBLIC_VC_ID = 1271597939730550885
CLOSED_VC_ID = 1331233909224247357

CODE_ROLE_ID = 1434466837243887687
WHITELIST_ROLE_ID = 1478003169232683008
BLACKLIST_ROLE_ID = 1478003080745451731

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ================= DATA =================

current_match = set()
match_history = defaultdict(list)
last_played_match_number = {}
global_match_counter = 0

# ================= UTILS =================

def now():
    return time.time()

def clean_old(user_id):
    cutoff = now() - 86400
    match_history[user_id] = [
        t for t in match_history[user_id] if t > cutoff
    ]

def matches_last_24h(user_id):
    clean_old(user_id)
    return len(match_history[user_id])

def matches_waited(user_id):
    last = last_played_match_number.get(user_id, 0)
    return global_match_counter - last

async def safe_move(member, channel):
    if member.voice and member.voice.channel != channel:
        try:
            await member.move_to(channel)
        except:
            pass

# ================= EVENTS =================

@bot.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    print("BotMaz ready")

@bot.event
async def on_voice_state_update(member, before, after):

    whitelist = member.guild.get_role(WHITELIST_ROLE_ID)

    if whitelist not in member.roles:
        return

    # Whitelist only auto-move if joining PUBLIC VC
    if after.channel and after.channel.id == PUBLIC_VC_ID:
        closed = member.guild.get_channel(CLOSED_VC_ID)
        await safe_move(member, closed)

# ================= PICK =================

@tree.command(name="pick", description="Pick players")
@app_commands.describe(amount="Number of players")
async def pick(interaction: discord.Interaction, amount: int):

    global global_match_counter

    await interaction.response.defer()

    guild = interaction.guild
    public_vc = guild.get_channel(PUBLIC_VC_ID)
    closed_vc = guild.get_channel(CLOSED_VC_ID)

    code_role = guild.get_role(CODE_ROLE_ID)
    whitelist_role = guild.get_role(WHITELIST_ROLE_ID)
    blacklist_role = guild.get_role(BLACKLIST_ROLE_ID)

    # ---- REMOVE OLD MATCH ----

    for user_id in list(current_match):

        member = guild.get_member(user_id)
        if not member:
            continue

        if whitelist_role in member.roles:
            continue

        try:
            await member.remove_roles(code_role)
        except:
            pass

        await safe_move(member, public_vc)

    current_match.clear()

    global_match_counter += 1

    # ---- ELIGIBLE PLAYERS ----

    candidates = []

    for member in public_vc.members:

        if member.bot:
            continue

        if blacklist_role in member.roles:
            continue

        if whitelist_role in member.roles:
            continue

        candidates.append(member)

    # ---- WEIGHTED FAIRNESS ----

    def score(member):
        played = matches_last_24h(member.id)
        waited = matches_waited(member.id)

        # fewer matches = better
        # more waited = better
        return (played, -waited)

    candidates.sort(key=score)

    selected = candidates[:amount]

    # ---- FORCE WHITELIST INTO CLOSED IF IN PUBLIC ----

    for member in public_vc.members:
        if whitelist_role in member.roles:
            await safe_move(member, closed_vc)

    # ---- ASSIGN NEW MATCH ----

    reply_lines = []

    for member in selected:

        try:
            await member.add_roles(code_role)
        except:
            pass

        await safe_move(member, closed_vc)

        current_match.add(member.id)

        match_history[member.id].append(now())
        last_played_match_number[member.id] = global_match_counter

        matches = matches_last_24h(member.id)
        waited = matches_waited(member.id)

        reply_lines.append(
            f"{member.display_name} — matches: {matches} after: {waited}"
        )

    if not reply_lines:
        msg = "No eligible players."
    else:
        msg = f"MATCH {global_match_counter}\n\n" + "\n".join(reply_lines)

    await interaction.followup.send(msg)

# ================= RESET =================

@tree.command(name="reset", description="Reset roles")
async def reset(interaction: discord.Interaction):

    await interaction.response.defer()

    guild = interaction.guild
    role = guild.get_role(CODE_ROLE_ID)
    whitelist = guild.get_role(WHITELIST_ROLE_ID)

    removed = 0

    for member in guild.members:

        if role in member.roles and whitelist not in member.roles:
            try:
                await member.remove_roles(role)
                removed += 1
            except:
                pass

    current_match.clear()

    await interaction.followup.send(
        f"Reset complete. Removed role from {removed} users."
    )

# ================= QUEUE =================

@tree.command(name="queue", description="Show queue")
async def queue(interaction: discord.Interaction):

    await interaction.response.defer()

    guild = interaction.guild
    public_vc = guild.get_channel(PUBLIC_VC_ID)

    members = [
        m for m in public_vc.members
        if not m.bot
    ]

    if not members:
        await interaction.followup.send("Queue empty")
        return

    members.sort(
        key=lambda m: matches_waited(m.id),
        reverse=True
    )

    lines = []

    for m in members:
        lines.append(
            f"{m.display_name} — matches: {matches_last_24h(m.id)} after: {matches_waited(m.id)}"
        )

    # Prevent 2000 char crash
    chunk = ""
    for line in lines:
        if len(chunk) + len(line) > 1900:
            await interaction.followup.send(chunk)
            chunk = ""
        chunk += line + "\n"

    if chunk:
        await interaction.followup.send(chunk)

bot.run(TOKEN)
