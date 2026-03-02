import discord
from discord.ext import commands
import os
import time
import json
import asyncio

# ========= CONFIGURATION (HARDCODED IDS) =========
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
        print(f"🚀 BotMaz Online: {bot.user}")
    except discord.Forbidden:
        print("❌ Sync Error: Bot lacks 'applications.commands' scope.")

@bot.event
async def on_voice_state_update(member, before, after):
    """Auto-remove role if a non-whitelist player leaves the match room mid-game."""
    if before.channel and before.channel.id == CLOSED_VC_ID:
        if after.channel is None or after.channel.id != CLOSED_VC_ID:
            code_role = member.guild.get_role(CODE_ROLE_ID)
            whitelist = member.guild.get_role(WHITELIST_ROLE_ID)

            if code_role and code_role in member.roles and whitelist not in member.roles:
                try:
                    await member.remove_roles(code_role)
                except:
                    pass

# ========= COMMANDS =========

@bot.tree.command(name="pick", description="Wipes old roles and picks new players fairly")
async def pick(interaction: discord.Interaction, amount: int):
    await interaction.response.defer()

    guild = interaction.guild
    public_vc = guild.get_channel(PUBLIC_VC_ID)
    closed_vc = guild.get_channel(CLOSED_VC_ID)
    code_role = guild.get_role(CODE_ROLE_ID)
    whitelist = guild.get_role(WHITELIST_ROLE_ID)
    blacklist = guild.get_role(BLACKLIST_ROLE_ID)

    # 1️⃣ GLOBAL RESET (Merges /reset into /pick)
    # Scans every member in the server to ensure NO ONE has the role except staff
    reset_tasks = []
    for m in guild.members:
        # If they have the code role and aren't Whitelisted, they lose it
        if code_role in m.roles and (not whitelist or whitelist not in m.roles):
            async def strip_role(member=m):
                try:
                    await member.remove_roles(code_role)
                    # Move them back to public if they are still lingering in Closed VC
                    if member.voice and member.voice.channel and member.voice.channel.id == CLOSED_VC_ID:
                        await member.move_to(public_vc)
                except: pass
            reset_tasks.append(strip_role())

    if reset_tasks:
        await asyncio.gather(*reset_tasks)
    
    current_match.clear()

    # 2️⃣ BUILD ELIGIBLE LISTS
    eligible = []
    wl_to_move = []

    for m in public_vc.members:
        if m.bot or (blacklist and blacklist in m.roles):
            continue
        if whitelist and whitelist in m.roles:
            wl_to_move.append(m)
            continue
        
        # Priority logic
        score = waited(m.id) - (matches_last_24h(m.id) * 2)
        eligible.append((score, m))

    eligible.sort(key=lambda x: x[0], reverse=True)
    selected = [m for score, m in eligible[:amount]]

    if not selected and not wl_to_move:
        return await interaction.followup.send("No players in Public VC.")

    # 3️⃣ EXECUTE NEW MATCH (Parallel)
    tasks = []
    lines = []

    # Whitelist Move
    for m in wl_to_move:
        async def wl_task(member=m):
            try:
                if code_role not in member.roles: await member.add_roles(code_role)
                if member.voice and member.voice.channel and member.voice.channel.id == PUBLIC_VC_ID:
                    await member.move_to(closed_vc)
            except: pass
        tasks.append(wl_task())

    # Selected Players Move & Stat Update
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
                if member.voice and member.voice.channel and member.voice.channel.id == PUBLIC_VC_ID:
                    await member.move_to(closed_vc)
            except: pass
        tasks.append(sel_task())
        
        lines.append(f"✅ **{m.display_name}** (Games: {len(stats['plays'])}, Waited: {prev_wait})")

    if tasks:
        await asyncio.gather(*tasks)

    # 4️⃣ UPDATE WAIT COUNTERS
    for m in public_vc.members:
        if not m.bot and m.id not in current_match:
            player_stats.setdefault(str(m.id), {"plays": [], "waited": 0})["waited"] += 1

    save_data()
    
    wl_msg = f"⭐ Moved {len(wl_to_move)} Whitelisted players.\n" if wl_to_move else ""
    await interaction.followup.send(f"### New Match Started!\n{wl_msg}" + "\n".join(lines))

@bot.tree.command(name="reset", description="Manual force reset")
async def reset(interaction: discord.Interaction):
    await interaction.response.defer()
    # Logic remains same but simplified since it's now part of /pick
    guild = interaction.guild
    public_vc = guild.get_channel(PUBLIC_VC_ID)
    closed_vc = guild.get_channel(CLOSED_VC_ID)
    code_role = guild.get_role(CODE_ROLE_ID)
    whitelist = guild.get_role(WHITELIST_ROLE_ID)

    tasks = []
    for m in guild.members:
        if code_role in m.roles and (not whitelist or whitelist not in m.roles):
            async def manual_reset(member=m):
                try:
                    await member.remove_roles(code_role)
                    if member.voice and member.voice.channel and member.voice.channel.id == CLOSED_VC_ID:
                        await member.move_to(public_vc)
                except: pass
            tasks.append(manual_reset())

    if tasks: await asyncio.gather(*tasks)
    current_match.clear()
    await interaction.followup.send(f"✅ Reset complete. Cleared roles/positions.")

bot.run(TOKEN)
