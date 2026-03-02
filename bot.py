import discord
from discord import app_commands
from discord.ext import commands
import os
import random
import asyncio
import time

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

guild_obj = discord.Object(id=GUILD_ID)

current_match = set()

player_stats = {}
match_counter = 0

DAY_SECONDS = 86400


def now():
    return int(time.time())


def clean_old(user_id):
    if user_id not in player_stats:
        player_stats[user_id] = {
            "matches": [],
            "last_played": 0,
            "last_wait": 0
        }

    player_stats[user_id]["matches"] = [
        t for t in player_stats[user_id]["matches"]
        if now() - t <= DAY_SECONDS
    ]


def matches_last_24h(user_id):
    clean_old(user_id)
    return len(player_stats[user_id]["matches"])


def matches_waited(user_id):
    clean_old(user_id)
    return player_stats[user_id]["last_wait"]


def record_match(user_id):
    clean_old(user_id)
    player_stats[user_id]["matches"].append(now())


def record_wait(user_id):
    clean_old(user_id)
    player_stats[user_id]["last_wait"] += 1


def reset_wait(user_id):
    clean_old(user_id)
    player_stats[user_id]["last_wait"] = 0


async def safe_move(member, channel):
    try:
        if member.voice and member.voice.channel != channel:
            await member.move_to(channel)
            await asyncio.sleep(0.2)
    except:
        pass


def fairness_sort(members):

    scored = []

    for m in members:

        uid = m.id

        clean_old(uid)

        matches = matches_last_24h(uid)
        wait = matches_waited(uid)

        score = wait - (matches * 2)

        scored.append((score, random.random(), m))

    scored.sort(reverse=True)

    return [m for score, r, m in scored]


@bot.event
async def on_ready():

    await tree.sync(guild=guild_obj)

    print("BotMaz ready")


@tree.command(name="queue", description="Show queue", guild=guild_obj)
async def queue(interaction: discord.Interaction):

    await interaction.response.defer(ephemeral=True)

    public_vc = interaction.guild.get_channel(PUBLIC_VC_ID)

    members = [
        m for m in public_vc.members
        if not m.bot
    ]

    members = fairness_sort(members)

    lines = []

    for m in members[:25]:

        uid = m.id

        matches = matches_last_24h(uid)
        waited = matches_waited(uid)

        lines.append(
            f"{m.display_name} — matches:{matches} after:{waited}"
        )

    if not lines:
        msg = "Queue empty"
    else:
        msg = "\n".join(lines)

    await interaction.followup.send(msg, ephemeral=True)


@tree.command(name="reset", description="Reset roles", guild=guild_obj)
async def reset(interaction: discord.Interaction):

    await interaction.response.defer(ephemeral=True)

    guild = interaction.guild

    role = guild.get_role(CODE_ROLE_ID)
    whitelist = guild.get_role(WHITELIST_ROLE_ID)

    public_vc = guild.get_channel(PUBLIC_VC_ID)

    removed = 0
    failed = 0

    for member in guild.members:

        try:

            if role in member.roles and whitelist not in member.roles:

                await member.remove_roles(role)

                removed += 1

                if member.voice and member.voice.channel.id == CLOSED_VC_ID:

                    await safe_move(member, public_vc)

        except:

            failed += 1

    current_match.clear()

    await interaction.followup.send(
        f"Reset complete\nRemoved:{removed}\nFailed:{failed}",
        ephemeral=True
    )


@tree.command(name="pick", description="Pick players", guild=guild_obj)
@app_commands.describe(amount="Number of players")
async def pick(interaction: discord.Interaction, amount: int):

    global match_counter

    await interaction.response.defer()

    guild = interaction.guild

    public_vc = guild.get_channel(PUBLIC_VC_ID)
    closed_vc = guild.get_channel(CLOSED_VC_ID)

    code_role = guild.get_role(CODE_ROLE_ID)
    whitelist_role = guild.get_role(WHITELIST_ROLE_ID)
    blacklist_role = guild.get_role(BLACKLIST_ROLE_ID)

    removed = []

    for uid in list(current_match):

        member = guild.get_member(uid)

        if not member:
            continue

        if whitelist_role in member.roles:
            continue

        if code_role in member.roles:
            await member.remove_roles(code_role)

        await safe_move(member, public_vc)

        removed.append(member)

    current_match.clear()

    public_members = []

    for m in public_vc.members:

        if m.bot:
            continue

        if blacklist_role in m.roles:
            continue

        public_members.append(m)

    public_members = fairness_sort(public_members)

    picked = public_members[:amount]

    added = []

    for m in picked:

        await m.add_roles(code_role)

        await safe_move(m, closed_vc)

        current_match.add(m.id)

        record_match(m.id)

        reset_wait(m.id)

        added.append(m)

    for m in public_members[amount:]:

        record_wait(m.id)

    match_counter += 1

    lines = []

    for m in added:

        uid = m.id

        matches = matches_last_24h(uid)
        waited = matches_waited(uid)

        lines.append(
            f"{m.display_name} — matches:{matches} after:{waited}"
        )

    msg = f"MATCH {match_counter}\n\n" + "\n".join(lines)

    await interaction.followup.send(msg)


bot.run(TOKEN)
