import discord
from discord.ext import commands
import os
import time
import json

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
intents.members = True          # Required for queue tracking [cite: 14]
intents.voice_states = True     # Required for VC movement [cite: 15]
intents.guilds = True
intents.message_content = True  # Added to fix Log Warning [cite: 1, 5, 9]

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
    # Tracks matches played in last 24 hours only [cite: 15]
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
        # Global sync to avoid Discord sync issues [cite: 16]
        await bot.tree.sync()
        print(f"BotMaz Online: {bot.user}")
    except discord.Forbidden:
        print("CRITICAL: Missing 'applications.commands' scope. Re-invite the bot.")

# ========= COMMANDS =========

@bot.tree.command(name="pick", description="Select players fairly for the next round")
async def pick(interaction: discord.Interaction, amount: int):
    """Fairly selects players based on wait time and recent games."""
    await interaction.response.defer()
    
    guild = interaction.guild
    public_vc = guild.get_channel(PUBLIC_VC_ID)
    closed_vc = guild.get_channel(CLOSED_VC_ID)
    code_role = guild.get_role(CODE_ROLE_ID)
    whitelist = guild.get_role(WHITELIST_ROLE_ID)
    blacklist = guild.get_role(BLACKLIST_ROLE_ID)

    # 1️⃣ Clean previous match participants
    for uid in list(current_match):
        member = guild.get_member(uid)
        # Whitelist players are never removed [cite: 15, 16]
        if member and whitelist not in member.roles:
            try:
                if code_role in member.roles:
                    await member.remove_roles(code_role)
                if member.voice and member.voice.channel.id == CLOSED_VC_ID:
                    await member.move_to(public_vc)
            except Exception:
                pass
    current_match.clear()

    # 2️⃣ Identify eligible players (Exclude bot, blacklisted, or whitelisted) [cite: 15]
    eligible = []
    for m in public_vc.members:
        if m.bot or blacklist in m.roles or whitelist in m.roles:
            continue
        # Weighted queue system: Priority = wait - (matches * 2) [cite: 15]
        score = waited(m.id) - (matches_last_24h(m.id) * 2)
        eligible.append((score, m))

    if not eligible:
        return await interaction.followup.send("No eligible players in Public VC.")

    # 3️⃣ Sort and select top players [cite: 15]
    eligible.sort(key=lambda x: x[0], reverse=True)
    selected = [m for score, m in eligible[:amount]]

    # 4️⃣ Move selected players and update stats [cite: 16]
    lines = []
    for m in selected:
        current_match.add(m.id)
        uid_s = str(m.id)
        stats = player_stats.setdefault(uid_s, {"plays": [], "waited": 0})
        
        prev_wait = stats["waited"]
        stats["plays"].append(now())
        stats["waited"] = 0 # Reset wait counter [cite: 15]

        try:
            await m.add_roles(code_role)
            if m.voice and m.voice.channel.id == PUBLIC_VC_ID:
                await m.move_to(closed_vc)
            lines.append(f"✅ **{m.display_name}** (Games: {len(stats['plays'])}, Waited: {prev_wait})")
        except Exception:
            lines.append(f"⚠️ **{m.display_name}** (Failed movement/role)")

    # 5️⃣ Increment wait counter for those left behind [cite: 15]
    for m in public_vc.members:
        if not m.bot and m.id not in current_match:
            player_stats.setdefault(str(m.id), {"plays": [], "waited": 0})["waited"] += 1

    save_data()
    await interaction.followup.send(f"### Selection Complete\n" + "\n".join(lines))

@bot.tree.command(name="queue", description="Display current queue stats")
async def queue(interaction: discord.Interaction):
    """Displays wait/match stats for everyone currently in Public VC[cite: 16]."""
    public_vc = interaction.guild.get_channel(PUBLIC_VC_ID)
    if not public_vc.members:
        return await interaction.response.send_message("Public VC is empty.")

    report = []
    for m in public_vc.members:
        if m.bot: continue
        report.append(f"{m.display_name}: **{waited(m.id)}** waits, **{matches_last_24h(m.id)}** matches")
    
    await interaction.response.send_message("### Queue Status\n" + "\n".join(report))

@bot.tree.command(name="reset", description="Clear all roles and move players safely")
async def reset(interaction: discord.Interaction):
    """Safely clears roles and moves players back to public[cite: 16]."""
    await interaction.response.defer()
    guild = interaction.guild
    code_role = guild.get_role(CODE_ROLE_ID)
    public_vc = guild.get_channel(PUBLIC_VC_ID)
    closed_vc = guild.get_channel(CLOSED_VC_ID)
    
    count = 0
    for m in closed_vc.members:
        if code_role in m.roles:
            await m.remove_roles(code_role)
            await m.move_to(public_vc)
            count += 1
    
    current_match.clear()
    await interaction.followup.send(f"Reset complete. Moved {count} players.")

bot.run(TOKEN)
