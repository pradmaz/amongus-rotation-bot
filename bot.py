import discord
from discord.ext import commands
from discord import app_commands
import random
import os

# ========================
# CONFIGURATION
# ========================

TOKEN = os.getenv("TOKEN")

PUBLIC_VC_ID = 1271597939730550885
CLOSED_VC_ID = 1331233909224247357

CODE_ROLE_ID = 1434466837243887687
WHITELIST_ROLE_ID = 1478003169232683008
BLACKLIST_ROLE_ID = 1478003080745451731

# ========================
# INTENTS
# ========================

intents = discord.Intents.default()
intents.members = True
intents.voice_states = True
intents.guilds = True
intents.message_content = True

# ========================
# BOT CLASS
# ========================

class Bot(commands.Bot):

    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents
        )

    async def setup_hook(self):
        await self.tree.sync()
        print("Global commands synced successfully")

bot = Bot()

# ========================
# STORAGE
# ========================

current_players = []

# ========================
# ROLE HELPERS
# ========================

def is_whitelisted(member):
    return discord.utils.get(member.roles, id=WHITELIST_ROLE_ID) is not None

def is_blacklisted(member):
    return discord.utils.get(member.roles, id=BLACKLIST_ROLE_ID) is not None

def has_code_role(member):
    return discord.utils.get(member.roles, id=CODE_ROLE_ID) is not None

# ========================
# READY EVENT
# ========================

@bot.event
async def on_ready():
    print(f"BotMaz is online as {bot.user}")

# ========================
# VOICE STATE UPDATE
# ========================

@bot.event
async def on_voice_state_update(member, before, after):

    if member.bot:
        return

    guild = member.guild

    public_vc = guild.get_channel(PUBLIC_VC_ID)
    closed_vc = guild.get_channel(CLOSED_VC_ID)

    code_role = guild.get_role(CODE_ROLE_ID)

    # WHITELIST: Always keep in Closed VC and always keep role
    if is_whitelisted(member):

        if after.channel == public_vc:

            try:
                await member.move_to(closed_vc)
            except:
                pass

        if code_role not in member.roles:

            try:
                await member.add_roles(code_role)
            except:
                pass

        return

    # NORMAL PLAYER: Remove role if leaves Closed VC
    if before.channel == closed_vc and after.channel != closed_vc:

        if has_code_role(member):

            try:
                await member.remove_roles(code_role)
            except:
                pass

# ========================
# GET PUBLIC PLAYERS
# ========================

def get_public_players(guild):

    public_vc = guild.get_channel(PUBLIC_VC_ID)

    players = []

    for member in public_vc.members:

        if member.bot:
            continue

        if is_blacklisted(member):
            continue

        if is_whitelisted(member):
            continue

        players.append(member)

    return players

# ========================
# QUEUE COMMAND
# ========================

@bot.tree.command(name="queue", description="Show public queue")

async def queue_cmd(interaction: discord.Interaction):

    guild = interaction.guild

    players = get_public_players(guild)

    if not players:

        await interaction.response.send_message("No players waiting.")
        return

    names = "\n".join(p.display_name for p in players)

    await interaction.response.send_message(
        f"Queue ({len(players)} players):\n{names}"
    )

# ========================
# PICK COMMAND
# ========================

@bot.tree.command(name="pick", description="Pick players")
@app_commands.describe(amount="Number of players")

async def pick_cmd(interaction: discord.Interaction, amount: int):

    global current_players

    await interaction.response.defer()

    guild = interaction.guild

    public_vc = guild.get_channel(PUBLIC_VC_ID)
    closed_vc = guild.get_channel(CLOSED_VC_ID)

    code_role = guild.get_role(CODE_ROLE_ID)

    # Move previous players back (except whitelist)
    for member in current_players:

        if is_whitelisted(member):
            continue

        try:
            await member.remove_roles(code_role)
        except:
            pass

        try:
            await member.move_to(public_vc)
        except:
            pass

    eligible = get_public_players(guild)

    if not eligible:

        await interaction.followup.send("No eligible players.")
        return

    if amount > len(eligible):
        amount = len(eligible)

    picked = random.sample(eligible, amount)

    current_players = picked.copy()

    for member in picked:

        try:
            await member.add_roles(code_role)
        except:
            pass

        try:
            await member.move_to(closed_vc)
        except:
            pass

    names = "\n".join(member.display_name for member in picked)

    await interaction.followup.send(
        f"Picked {len(picked)} players:\n{names}"
    )

# ========================
# RESET COMMAND
# ========================

@bot.tree.command(name="reset", description="Reset lobby safely")

async def reset_cmd(interaction: discord.Interaction):

    guild = interaction.guild

    public_vc = guild.get_channel(PUBLIC_VC_ID)
    closed_vc = guild.get_channel(CLOSED_VC_ID)

    code_role = guild.get_role(CODE_ROLE_ID)

    removed = 0
    moved = 0

    # Remove role from normal players only
    for member in guild.members:

        if member.bot:
            continue

        if is_whitelisted(member):
            continue

        if has_code_role(member):

            try:
                await member.remove_roles(code_role)
                removed += 1
            except:
                pass

    # Move normal players back
    for member in closed_vc.members:

        if member.bot:
            continue

        if is_whitelisted(member):
            continue

        try:
            await member.move_to(public_vc)
            moved += 1
        except:
            pass

    await interaction.response.send_message(
        f"Reset complete\nRoles removed: {removed}\nUsers moved: {moved}\nWhitelist untouched."
    )

# ========================
# RUN BOT
# ========================

bot.run(TOKEN)
