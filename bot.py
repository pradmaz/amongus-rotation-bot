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

# ========= BOT EVENTS =========
@bot.event
async def on_ready():
    load_data()
    try:
        await bot.tree.sync()
        print(f"BotMaz Online: {bot.user}")
    except discord.Forbidden:
        print("CRITICAL: Missing 'applications.commands' scope.")

# ========= COMMANDS =========

@bot.tree.command(name="pick", description="Select players fairly and move whitelist from Public VC")
async def pick(interaction: discord.Interaction, amount: int):
    await interaction.response.defer()
    guild = interaction.guild
    
    public_vc = guild.get_channel(PUBLIC_VC_ID)
    closed_vc = guild.get_channel(CLOSED_VC_ID)
    code_role = guild.get_role(CODE_ROLE_ID)
    whitelist = guild.get_role(WHITELIST_ROLE_ID)
    blacklist = guild.get_role(BLACKLIST_ROLE_ID)

    # 1️⃣ CLEAN PREVIOUS MATCH (Parallelized)
    cleanup_tasks = []
    for uid in list(current_match):
        member = guild.get_member(uid)
        if not member or whitelist in member.roles:
            continue
        async def cleanup(m=member):
            try:
                if code_role in m.roles: await m.remove_roles(code_role)
                if m.voice and m.voice.channel.id == CLOSED_VC_ID:
                    await m.move_to(public_vc)
            except: pass
        cleanup_tasks.append(cleanup())
    
    if cleanup_tasks:
        await asyncio.gather(*cleanup_tasks)
    current_match.clear()

    # 2️⃣ BUILD ELIGIBLE LIST & DETECT WHITELIST IN PUBLIC VC
    eligible = []
    whitelist_to_move = []

    for m in public_vc.members:
        if m.bot or blacklist in m.roles:
            continue
        if whitelist in m.roles:
            whitelist_to_move.append(m)
            continue
        
        score = waited(m.id) - (matches_last_24h(m.id) * 2)
        eligible.append((score, m))

    # 3️⃣ SORT AND SELECT
    eligible.sort(key=lambda x: x[0], reverse=True)
    selected = [m for score, m in eligible[:amount]]

    if not selected and not whitelist_to_move:
        return await interaction.followup.send("No players found in Public VC.")

    # 4️⃣ EXECUTE MOVEMENTS (Parallelized)
    move_tasks = []
    lines = []

    # Handle Whitelist (Move from Public only, No stat change)
    for m in whitelist_to_move:
        current_match.add(m.id)
        async def move_wl(member=m):
            try:
                if code_role not in member.roles: await member.add_roles(code_role)
                await member.move_to(closed_vc)
            except: pass
        move_tasks.append(move_wl())

    # Handle Selected Players (Update stats + Move)
    for m in selected:
        current_match.add(m.id)
        uid_s = str(m.id)
        stats = player_stats.setdefault(uid_s, {"plays": [], "waited": 0})
        
        prev_wait = stats["waited"]
        stats["plays"].append(now())
        stats["waited"] = 0 
        
        async def move_sel(member=m):
            try:
                await member.add_roles(code_role)
                await member.move_to(closed_vc)
            except: pass
        
        move_tasks.append(move_sel())
        lines.append(f"✅ **{m.display_name}** (Matches: {len(stats['plays'])}, Waited: {prev_wait})")

    if move_tasks:
        await asyncio.gather(*move_tasks)

    # 5️⃣ UPDATE WAIT COUNTER
    for m in public_vc.members:
        if not m.bot and m.id not in current_match:
            player_stats.setdefault(str(m.id), {"plays": [], "waited": 0})["waited"] += 1

    save_data()

    # 6️⃣ FINAL OUTPUT
    move_msg = f"⭐ Moved {len(whitelist_to_move)} whitelisted players.\n" if whitelist_to_move else ""
    await interaction.followup.send(f"### Match Started!\n{move_msg}" + "\n".join(lines))

@bot.tree.command(name="queue", description="Display wait and match stats")
async def queue(interaction: discord.Interaction):
    public_vc = interaction.guild.get_channel(PUBLIC_VC_ID)
    if not public_vc or not public_vc.members:
        return await interaction.response.send_message("Public VC is empty.")
    report = [f"{m.display_name}: **{waited(m.id)}** waits, **{matches_last_24h(m.id)}** matches" for m in public_vc.members if not m.bot]
    await interaction.response.send_message("### Current Queue Status\n" + "\n".join(report))

@bot.tree.command(name="reset", description="Clear all roles and move players safely")
async def reset(interaction: discord.Interaction):
    await interaction.response.defer()
    guild = interaction.guild
    code_role = guild.get_role(CODE_ROLE_ID)
    public_vc = guild.get_channel(PUBLIC_VC_ID)
    closed_vc = guild.get_channel(CLOSED_VC_ID)
    
    tasks = []
    for m in closed_vc.members:
        async def do_reset(member=m):
            try:
                if code_role in member.roles: await member.remove_roles(code_role)
                await member.move_to(public_vc)
            except: pass
        tasks.append(do_reset())
    
    if tasks: await asyncio.gather(*tasks)
    current_match.clear()
    await interaction.followup.send(f"Reset complete. {len(tasks)} players moved.")

bot.run(TOKEN)
