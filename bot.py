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
# HELPERS
# ========================

def is_whitelisted(member):
    return discord.utils.get(member.roles, id=WHITELIST_ROLE_ID) is not None

def is_blacklisted(member):
    return discord.utils.get(member.roles, id=BLACKLIST_ROLE_ID) is not None

def has_code_role(member):
    return discord.utils.get(member.roles, id=CODE_ROLE_ID) is not None

def get_public_members(guild):

    vc = guild.get_channel(PUBLIC_VC_ID)

    if not vc:
        return []

    valid = []

    for member in vc.members:

        if member.bot:
            continue

        if is_blacklisted(member):
            continue

        valid.append(member)

    return valid

# ========================
# EVENTS
# ========================

@bot.event
async def on_ready():
    print(f"BotMaz is online as {bot.user}")

# AUTO REMOVE ROLE IF LEAVE CLOSED VC

@bot.event
async def on_voice_state_update(member, before, after):

    if member.bot:
        return

    closed_vc = member.guild.get_channel(CLOSED_VC_ID)

    if before.channel == closed_vc and after.channel != closed_vc:

        if has_code_role(member):

            try:
                role = member.guild.get_role(CODE_ROLE_ID)
                await member.remove_roles(role)
                print(f"Removed code role from {member.display_name}")
            except:
                pass

# ========================
# COMMAND: QUEUE
# ========================

@bot.tree.command(name="queue", description="Show players in public VC")

async def queue_cmd(interaction: discord.Interaction):

    guild = interaction.guild

    members = get_public_members(guild)

    if not members:
        await interaction.response.send_message("No players waiting.")
        return

    names = "\n".join(m.display_name for m in members)

    await interaction.response.send_message(
        f"Queue ({len(members)} players):\n{names}"
    )

# ========================
# COMMAND: PICK
# ========================

@bot.tree.command(name="pick", description="Pick players fairly")
@app_commands.describe(amount="Number of players")

async def pick_cmd(interaction: discord.Interaction, amount: int):

    global current_players

    await interaction.response.defer()

    guild = interaction.guild

    public_vc = guild.get_channel(PUBLIC_VC_ID)
    closed_vc = guild.get_channel(CLOSED_VC_ID)

    code_role = guild.get_role(CODE_ROLE_ID)

    # MOVE OLD PLAYERS BACK

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

    # GET NEW PLAYERS

    eligible = get_public_members(guild)

    if not eligible:

        await interaction.followup.send("No eligible players.")
        return

    if amount > len(eligible):
        amount = len(eligible)

    picked = random.sample(eligible, amount)

    current_players = picked.copy()

    # ASSIGN ROLE AND MOVE

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
# COMMAND: RESET
# ========================

@bot.tree.command(name="reset", description="Reset and remove ALL code roles")

async def reset_cmd(interaction: discord.Interaction):

    guild = interaction.guild

    public_vc = guild.get_channel(PUBLIC_VC_ID)
    closed_vc = guild.get_channel(CLOSED_VC_ID)

    code_role = guild.get_role(CODE_ROLE_ID)

    removed = 0
    moved = 0

    # REMOVE ROLE FROM EVERYONE

    for member in guild.members:

        if member.bot:
            continue

        if has_code_role(member):

            try:
                await member.remove_roles(code_role)
                removed += 1
            except:
                pass

    # MOVE EVERYONE FROM CLOSED VC

    for member in closed_vc.members:

        if member.bot:
            continue

        try:
            await member.move_to(public_vc)
            moved += 1
        except:
            pass

    # VERIFY CLEAN

    remaining = []

    for member in guild.members:

        if has_code_role(member):
            remaining.append(member.display_name)

    msg = (
        f"Reset complete\n\n"
        f"Roles removed: {removed}\n"
        f"Users moved: {moved}\n"
    )

    if remaining:
        msg += f"WARNING: Still has role: {', '.join(remaining)}"
    else:
        msg += "SUCCESS: No one has the code role"

    await interaction.response.send_message(msg)

# ========================
# RUN BOT
# ========================

bot.run(TOKEN)
