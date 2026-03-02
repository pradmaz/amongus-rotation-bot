import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import random
import os
import time

TOKEN = os.getenv("TOKEN")

PUBLIC_VC_ID = 1271597939730550885
CLOSED_VC_ID = 1331233909224247357

CODE_ROLE_ID = 1434466837243887687
WHITELIST_ROLE_ID = 1478003169232683008
BLACKLIST_ROLE_ID = 1478003080745451731

intents = discord.Intents.default()
intents.members = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

current_match = set()
player_stats = {}
DAY_SECONDS = 86400


# ================= SAFE MOVE =================

async def safe_move(member, channel):
    try:
        if member.voice and member.voice.channel != channel:
            await member.move_to(channel)
            await asyncio.sleep(0.15)
    except:
        pass


# ================= CLEANUP =================

def cleanup():
    now = time.time()
    for uid in list(player_stats.keys()):
        player_stats[uid]["plays"] = [
            t for t in player_stats[uid]["plays"]
            if now - t < DAY_SECONDS
        ]


def get_weight(uid):
    cleanup()
    if uid not in player_stats:
        return 100
    plays = len(player_stats[uid]["plays"])
    waited = player_stats[uid]["waited"]
    return waited * 10 - plays * 5


# ================= READY =================

@bot.event
async def on_ready():
    await bot.tree.sync()
    print("Commands synced globally")
    print("BotMaz ready")


# ================= QUEUE =================

@bot.tree.command(name="queue", description="Show waiting queue")
async def queue(interaction: discord.Interaction):

    await interaction.response.defer()

    guild = interaction.guild
    public_vc = guild.get_channel(PUBLIC_VC_ID)

    players = []

    for m in public_vc.members:

        if any(r.id == BLACKLIST_ROLE_ID for r in m.roles):
            continue

        stats = player_stats.get(m.id, {"plays": [], "waited": 0})

        players.append(
            f"{m.display_name} — matches:{len(stats['plays'])} after:{stats['waited']}"
        )

    if not players:
        await interaction.followup.send("Queue empty")
        return

    await interaction.followup.send("\n".join(players[:25]))


# ================= PICK =================

@bot.tree.command(name="pick", description="Pick players")
async def pick(interaction: discord.Interaction, amount: int):

    await interaction.response.defer()

    guild = interaction.guild

    public_vc = guild.get_channel(PUBLIC_VC_ID)
    closed_vc = guild.get_channel(CLOSED_VC_ID)

    role = guild.get_role(CODE_ROLE_ID)
    whitelist = guild.get_role(WHITELIST_ROLE_ID)
    blacklist = guild.get_role(BLACKLIST_ROLE_ID)

    cleanup()

    # REMOVE OLD
    for uid in list(current_match):
        member = guild.get_member(uid)
        if not member:
            continue
        if whitelist in member.roles:
            continue
        try:
            await member.remove_roles(role)
            await safe_move(member, public_vc)
        except:
            pass

    current_match.clear()

    eligible = []

    for m in public_vc.members:
        if m.bot:
            continue
        if blacklist in m.roles:
            continue
        if whitelist in m.roles:
            continue
        weight = get_weight(m.id)
        eligible.append((m, weight))

    if not eligible:
        await interaction.followup.send("No eligible players")
        return

    pool = []
    for m, weight in eligible:
        pool.extend([m] * max(1, weight))

    picked = []
    while len(picked) < amount and pool:
        m = random.choice(pool)
        if m not in picked:
            picked.append(m)
        pool = [x for x in pool if x != m]

    results = []

    for m in picked:
        await m.add_roles(role)
        await safe_move(m, closed_vc)
        current_match.add(m.id)

        if m.id not in player_stats:
            player_stats[m.id] = {"plays": [], "waited": 0}

        waited = player_stats[m.id]["waited"]
        player_stats[m.id]["plays"].append(time.time())
        player_stats[m.id]["waited"] = 0

        results.append(
            f"{m.display_name} — matches:{len(player_stats[m.id]['plays'])} after:{waited}"
        )

    for m in public_vc.members:
        if m.id not in current_match:
            if m.id not in player_stats:
                player_stats[m.id] = {"plays": [], "waited": 0}
            player_stats[m.id]["waited"] += 1

    await interaction.followup.send("Picked:\n" + "\n".join(results))


# ================= RESET =================

@bot.tree.command(name="reset", description="Reset roles")
async def reset(interaction: discord.Interaction):

    await interaction.response.defer()

    guild = interaction.guild

    role = guild.get_role(CODE_ROLE_ID)
    whitelist = guild.get_role(WHITELIST_ROLE_ID)
    public_vc = guild.get_channel(PUBLIC_VC_ID)

    removed = 0

    for member in guild.members:
        if role in member.roles and whitelist not in member.roles:
            try:
                await member.remove_roles(role)
                await safe_move(member, public_vc)
                removed += 1
            except:
                pass

    current_match.clear()

    await interaction.followup.send(
        f"Reset complete. Removed role from {removed} users."
    )


bot.run(TOKEN)
