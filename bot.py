import discord
from discord.ext import commands
from discord import app_commands
import random
import os
import time

TOKEN = os.getenv("TOKEN")

# CHANNEL IDS
PUBLIC_VC_ID = 1271597939730550885
CLOSED_VC_ID = 1331233909224247357

# ROLE IDS
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


# ---------------- HELPERS ----------------

def is_whitelisted(member):
    return discord.utils.get(member.roles, id=WHITELIST_ROLE_ID)


def is_blacklisted(member):
    return discord.utils.get(member.roles, id=BLACKLIST_ROLE_ID)


def has_code_role(member):
    return discord.utils.get(member.roles, id=CODE_ROLE_ID)


def clean_old(uid):
    if uid not in player_stats:
        return

    now = time.time()

    player_stats[uid]["plays"] = [
        t for t in player_stats[uid]["plays"]
        if now - t < DAY_SECONDS
    ]


def matches_last_24h(uid):
    if uid not in player_stats:
        return 0

    clean_old(uid)
    return len(player_stats[uid]["plays"])


def get_wait(uid):
    if uid not in player_stats:
        return match_counter

    return match_counter - player_stats[uid]["last"]


def get_public_players(guild):

    vc = guild.get_channel(PUBLIC_VC_ID)

    players = []

    for m in vc.members:

        if m.bot:
            continue

        if is_blacklisted(m):
            continue

        if is_whitelisted(m):
            continue

        players.append(m)

    return players


async def safe_send(interaction, text):

    chunks = [text[i:i+1900] for i in range(0, len(text), 1900)]

    for chunk in chunks:
        await interaction.followup.send(chunk)


# ---------------- READY ----------------

@bot.event
async def on_ready():
    print("BotMaz ready")


# ---------------- VOICE UPDATE ----------------

@bot.event
async def on_voice_state_update(member, before, after):

    if member.bot:
        return

    guild = member.guild
    closed_vc = guild.get_channel(CLOSED_VC_ID)

    # WHITELIST LOGIC
    if is_whitelisted(member):

        # Only auto-move if joining PUBLIC VC
        if after.channel and after.channel.id == PUBLIC_VC_ID:

            try:
                await member.move_to(closed_vc)
            except:
                pass

        return

    # NORMAL USERS
    # DO NOTHING if they leave closed VC
    # Role removal only happens during /pick


# ---------------- QUEUE ----------------

@bot.tree.command(name="queue", description="Show queue stats")
async def queue(interaction: discord.Interaction):

    await interaction.response.defer()

    players = get_public_players(interaction.guild)

    queue_data = []

    for p in players:

        uid = p.id
        matches = matches_last_24h(uid)
        wait = get_wait(uid)

        queue_data.append((p, matches, wait))

    queue_data.sort(key=lambda x: x[2], reverse=True)

    msg = "QUEUE STATUS\n\n"

    for p, matches, wait in queue_data:
        msg += f"{p.display_name} — matches: {matches} after: {wait}\n"

    await safe_send(interaction, msg)


# ---------------- PICK ----------------

@bot.tree.command(name="pick", description="Pick players fairly")
async def pick(interaction: discord.Interaction, amount: int):

    global current_players
    global match_counter

    await interaction.response.defer()

    guild = interaction.guild
    public_vc = guild.get_channel(PUBLIC_VC_ID)
    closed_vc = guild.get_channel(CLOSED_VC_ID)
    code_role = guild.get_role(CODE_ROLE_ID)

    match_counter += 1

    # REMOVE OLD BATCH
    for m in list(current_players):

        if m.bot:
            continue

        if is_whitelisted(m):
            continue

        try:
            if has_code_role(m):
                await m.remove_roles(code_role)

            if m.voice and m.voice.channel and m.voice.channel.id == CLOSED_VC_ID:
                await m.move_to(public_vc)

        except:
            pass

    current_players.clear()

    eligible = get_public_players(guild)

    scored = []

    for p in eligible:

        uid = p.id
        matches = matches_last_24h(uid)
        wait = get_wait(uid)

        score = wait * 10 - matches * 5 + random.uniform(0, 5)

        scored.append((p, score, matches, wait))

    scored.sort(key=lambda x: x[1], reverse=True)

    picked = scored[:amount]

    msg = f"MATCH {match_counter}\n\n"

    now = time.time()

    for player, score, matches, wait in picked:

        uid = player.id

        if uid not in player_stats:
            player_stats[uid] = {"plays": [], "last": 0}

        player_stats[uid]["plays"].append(now)
        player_stats[uid]["last"] = match_counter

        try:
            await player.add_roles(code_role)

            if player.voice and player.voice.channel:
                await player.move_to(closed_vc)

        except:
            pass

        current_players.append(player)

        msg += f"{player.display_name} — matches: {matches} after: {wait}\n"

    await safe_send(interaction, msg)


# ---------------- RESET ----------------

@bot.tree.command(name="reset", description="Reset lobby safely")
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

            if m.voice and m.voice.channel and m.voice.channel.id == CLOSED_VC_ID:
                await m.move_to(public_vc)
                moved += 1

        except:
            pass

    current_players.clear()

    await interaction.followup.send(
        f"RESET COMPLETE\nRemoved roles: {removed}\nMoved users: {moved}"
    )


bot.run(TOKEN)
