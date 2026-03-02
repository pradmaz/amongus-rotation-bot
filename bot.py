import discord
from discord.ext import commands
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

# ========= DATA PERSISTENCE =========
def save_data():
    with open("stats.json", "w") as f:
        json.dump(player_stats, f)

def load_data():
    global player_stats
    if os.path.exists("stats.json"):
        with open("stats.json", "r") as f:
            player_stats = json.load(f)

# ========= FAIRNESS LOGIC =========
def now():
    return int(time.time())

def clean_old(uid):
    uid = str(uid)
    if uid not in player_stats:
        player_stats[uid] = {"plays": [], "waited": 0}
        return
    cutoff = now() - DAY_SECONDS
    player_stats[uid]["plays"] = [t for t in player_stats[uid]["plays"] if t > cutoff]

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
        print(f"🚀 BotMaz Speed-Optimized: {bot.user}")
    except discord.Forbidden:
        print("❌ CRITICAL: Missing 'applications.commands' scope.")

@bot.event
async def on_voice_state_update(member, before, after):
    """Instant Auto-Cleanup when leaving Closed VC."""
    if before.channel and before.channel.id == CLOSED_VC_ID:
        if after.channel is None or after.channel.id != CLOSED_VC_ID:
            code_role = member.guild.get_role(CODE_ROLE_ID)
            whitelist = member.guild.get_role(WHITELIST_ROLE_ID)
            if code_role in member.roles and whitelist not in member.roles:
                try:
                    await member.remove_roles(code_role)
                except:
                    pass

# ========= SPEED-OPTIMIZED COMMANDS =========

@bot.tree.command(name="pick", description="High-speed fair player selection")
async def pick(interaction: discord.Interaction, amount: int):
    await interaction.response.defer()
    guild = interaction.guild
    
    # 1️⃣ Cache variables for speed
    public_vc = guild.get_channel(PUBLIC_VC_ID)
    closed_vc = guild.get_channel(CLOSED_VC_ID)
    code_role = guild.get_role(CODE_ROLE_ID)
    whitelist = guild.get_role(WHITELIST_ROLE_ID)
    blacklist = guild.get_role(BLACKLIST_ROLE_ID)

    # 2️⃣ Parallel Cleanup of old match
    cleanup_tasks = []
    for uid in list(current_match):
        member = guild.get_member(uid)
        if member and whitelist not in member.roles:
            async def fast_cleanup(m=member):
                try:
                    if code_role in m.roles: await m.remove_roles(code_role)
                    if m.voice and m.voice.channel.id == CLOSED_VC_ID: await m.move_to(public_vc)
                except: pass
            cleanup_tasks.append(fast_cleanup())
    
    if cleanup_tasks:
        await asyncio.gather(*cleanup_tasks)
    current_match.clear()

    # 3️⃣ Build Eligible lists
    eligible = []
    wl_to_move = []
    for m in public_vc.members:
        if m.bot or blacklist in m.roles: continue
        if whitelist in m.roles:
            wl_to_move.append(m)
            continue
        score = waited(m.id) - (matches_last_24h(m.id) * 2)
        eligible.append((score, m))

    # 4️⃣ Select and Setup Tasks
    eligible.sort(key=lambda x: x[0], reverse=True)
    selected = [m for score, m in eligible[:amount]]
    
    if not selected and not wl_to_move:
        return await interaction.followup.send("No players found in Public VC.")

    exec_tasks = []
    lines = []

    # Prepare Whitelist moves
    for m in wl_to_move:
        current_match.add(m.id)
        async def wl_task(member=m):
            try:
                if code_role not in member.roles: await member.add_roles(code_role)
                await member.move_to(closed_vc)
            except: pass
        exec_tasks.append(wl_task())

    # Prepare Selected Player moves/stats
    for m in selected:
        current_match.add(m.id)
        uid_s = str(m.id)
        stats = player_stats.setdefault(uid_s, {"plays": [], "waited": 0})
        prev_wait = stats["waited"]
        stats["plays"].append(now())
        stats["waited"] = 0
        
        async def sel_task(member=m):
            try:
                await member.add_roles(code_role)
                await member.move_to(closed_vc)
            except: pass
        exec_tasks.append(sel_task())
        lines.append(f"✅ **{m.display_name}** (Matches: {len(stats['plays'])}, Wait: {prev_wait})")

    # 5️⃣ FIRE ALL API REQUESTS IN PARALLEL
    if exec_tasks:
        await asyncio.gather(*exec_tasks)

    # 6️⃣ Update Remaining Stats
    for m in public_vc.members:
        if not m.bot and m.id not in current_match:
            player_stats.setdefault(str(m.id), {"plays": [], "waited": 0})["waited"] += 1

    save_data()
    wl_msg = f"⭐ Moved {len(wl_to_move)} Whitelisted players.\n" if wl_to_move else ""
    await interaction.followup.send(f"### Match Started!\n{wl_msg}" + "\n".join(lines))

@bot.tree.command(name="reset", description="Instant reset of all match roles/channels")
async def reset(interaction: discord.Interaction):
    await interaction.response.defer()
    guild = interaction.guild
    code_role = guild.get_role(CODE_ROLE_ID)
    public_vc = guild.get_channel(PUBLIC_VC_ID)
    closed_vc = guild.get_channel(CLOSED_VC_ID)
    
    tasks = []
    for m in closed_vc.members:
        async def reset_task(member=m):
            try:
                if code_role in member.roles: await member.remove_roles(code_role)
                await member.move_to(public_vc)
            except: pass
        tasks.append(reset_task())
    
    if tasks:
        await asyncio.gather(*tasks)
    
    current_match.clear()
    await interaction.followup.send(f"✅ Reset complete. Cleared {len(tasks)} players.")

bot.run(TOKEN)
