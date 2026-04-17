import discord
from discord.ext import commands
from discord import app_commands
import os
import time
import json
import asyncio

# ========= CONFIGURATION =========
TOKEN = os.getenv("TOKEN")

PUBLIC_VC_ID = 1271597939730550885
CLOSED_VC_ID = 1331233909224247357
CODE_ROLE_ID = 1434466837243887687
WHITELIST_ROLE_ID = 1478003169232683008
BLACKLIST_ROLE_ID = 1478003080745451731
PRADMAZ_ROLE_ID = 844092555679105034

DAY_SECONDS = 86400

# ========= INITIALIZATION =========
intents = discord.Intents.default()
intents.members = True
intents.voice_states = True
intents.guilds = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
current_match = set()
player_stats = {}

# ========= ROLE CHECK =========
def is_pradmaz():
    async def predicate(interaction: discord.Interaction):
        return any(role.id == PRADMAZ_ROLE_ID for role in interaction.user.roles)
    return app_commands.check(predicate)

# ========= DATA PERSISTENCE =========
def save_data():
    with open("stats.json", "w") as f:
        json.dump(player_stats, f, indent=4)

def load_data():
    global player_stats
    if os.path.exists("stats.json"):
        with open("stats.json", "r") as f:
            player_stats = json.load(f)

def now():
    return int(time.time())

def clean_old(uid):
    uid = str(uid)
    if uid not in player_stats:
        player_stats[uid] = {"plays": [], "waited": 0}
        return

    cutoff = now() - DAY_SECONDS
    player_stats[uid]["plays"] = [
        t for t in player_stats[uid]["plays"] if t > cutoff
    ]

def matches_last_24h(uid):
    clean_old(uid)
    return len(player_stats[str(uid)]["plays"])

def waited(uid):
    clean_old(uid)
    return player_stats[str(uid)]["waited"]

# ========= EVENTS =========
@bot.event
async def on_ready():
    load_data()
    try:
        await bot.tree.sync()
        print(f"🚀 BotMaz Online: {bot.user}")
    except discord.Forbidden:
        print("❌ Slash command sync failed.")

# ========= ERROR HANDLING =========
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.CheckFailure):
        await interaction.response.send_message(
            "❌ Only **PradMaz role** can use this command.",
            ephemeral=True
        )
    else:
        raise error

# ========= COMMAND =========
@bot.tree.command(name="pick", description="Global reset and sticky-role selection")
@is_pradmaz()  # 🔒 Restriction applied here
async def pick(interaction: discord.Interaction, amount: int):
    await interaction.response.defer()

    guild = interaction.guild
    public_vc = guild.get_channel(PUBLIC_VC_ID)
    closed_vc = guild.get_channel(CLOSED_VC_ID)
    code_role = guild.get_role(CODE_ROLE_ID)
    whitelist = guild.get_role(WHITELIST_ROLE_ID)
    blacklist = guild.get_role(BLACKLIST_ROLE_ID)

    # ✅ Safety check
    if not public_vc or not closed_vc or not code_role:
        return await interaction.followup.send("❌ Setup error: Channels or roles not found.")

    # ========= 1. GLOBAL ROLE RESET =========
    reset_tasks = []

    async def strip_role(member):
        try:
            await member.remove_roles(code_role)
            if member.voice and member.voice.channel and member.voice.channel.id == CLOSED_VC_ID:
                await member.move_to(public_vc)
        except Exception as e:
            print(f"Reset error for {member}: {e}")

    for m in guild.members:
        if code_role in m.roles and (not whitelist or whitelist not in m.roles):
            reset_tasks.append(strip_role(m))

    if reset_tasks:
        await asyncio.gather(*reset_tasks)

    current_match.clear()

    # ========= 2. BUILD ELIGIBLE LIST =========
    eligible = []
    wl_to_move = []

    for m in public_vc.members:
        if m.bot:
            continue
        if blacklist and blacklist in m.roles:
            continue

        if whitelist and whitelist in m.roles:
            wl_to_move.append(m)
            continue

        score = waited(m.id) - (matches_last_24h(m.id) * 2)
        eligible.append((score, m))

    eligible.sort(key=lambda x: x[0], reverse=True)
    selected = [m for score, m in eligible[:amount]]

    if not selected and not wl_to_move:
        return await interaction.followup.send("❌ No players in Public VC.")

    # ========= 3. EXECUTE MATCH =========
    tasks = []
    lines = []

    async def move_player(member):
        try:
            if code_role not in member.roles:
                await member.add_roles(code_role)

            if member.voice and member.voice.channel and member.voice.channel.id == PUBLIC_VC_ID:
                await member.move_to(closed_vc)

        except Exception as e:
            print(f"Move error for {member}: {e}")

    # Whitelist first
    for m in wl_to_move:
        tasks.append(move_player(m))

    # Selected players
    for m in selected:
        current_match.add(m.id)

        uid_s = str(m.id)
        stats = player_stats.setdefault(uid_s, {"plays": [], "waited": 0})

        prev_wait = stats["waited"]
        stats["plays"].append(now())
        stats["waited"] = 0

        tasks.append(move_player(m))

        lines.append(
            f"✅ **{m.display_name}** (Games: {len(stats['plays'])}, Waited: {prev_wait})"
        )

    if tasks:
        await asyncio.gather(*tasks)

    # ========= 4. UPDATE WAIT COUNTERS =========
    for m in public_vc.members:
        if not m.bot and m.id not in current_match:
            player_stats.setdefault(str(m.id), {"plays": [], "waited": 0})["waited"] += 1

    save_data()

    wl_msg = f"⭐ Moved {len(wl_to_move)} whitelisted players.\n" if wl_to_move else ""

    await interaction.followup.send(
        f"### 🎮 New Match Started!\n{wl_msg}" + "\n".join(lines)
    )

# ========= RUN =========
bot.run(TOKEN)
