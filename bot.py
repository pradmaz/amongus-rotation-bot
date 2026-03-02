import discord
from discord.ext import commands
from discord import app_commands
import random
import os

# ========================
# CONFIG
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
# QUEUE STORAGE
# ========================

queue = []
current_players = []


# ========================
# HELPERS
# ========================

def get_role(member, role_id):
    return discord.utils.get(member.roles, id=role_id)


def is_whitelisted(member):
    return get_role(member, WHITELIST_ROLE_ID) is not None


def is_blacklisted(member):
    return get_role(member, BLACKLIST_ROLE_ID) is not None


def get_public_members(guild):
    vc = guild.get_channel(PUBLIC_VC_ID)
    if not vc:
        return []

    members = []

    for m in vc.members:
        if m.bot:
            continue

        if is_blacklisted(m):
            continue

        members.append(m)

    return members


# ========================
# EVENTS
# ========================

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


# ========================
# COMMAND: QUEUE
# ========================

@bot.tree.command(name="queue", description="Show queue")
async def queue_cmd(interaction: discord.Interaction):

    guild = interaction.guild

    public_members = get_public_members(guild)

    names = [m.display_name for m in public_members]

    text = "\n".join(names) if names else "No one waiting"

    await interaction.response.send_message(
        f"Queue ({len(names)}):\n{text}",
        ephemeral=True
    )


# ========================
# COMMAND: RESET
# ========================

@bot.tree.command(name="reset", description="Reset lobby")
async def reset_cmd(interaction: discord.Interaction):

    global current_players, queue

    guild = interaction.guild

    public_vc = guild.get_channel(PUBLIC_VC_ID)
    closed_vc = guild.get_channel(CLOSED_VC_ID)

    role = guild.get_role(CODE_ROLE_ID)

    for member in closed_vc.members:

        if member.bot:
            continue

        if is_whitelisted(member):
            continue

        try:
            await member.remove_roles(role)
        except:
            pass

        try:
            await member.move_to(public_vc)
        except:
            pass

    current_players.clear()
    queue.clear()

    await interaction.response.send_message("Reset complete")


# ========================
# COMMAND: PICK
# ========================

@bot.tree.command(name="pick", description="Pick players")
@app_commands.describe(amount="Number of players")
async def pick_cmd(interaction: discord.Interaction, amount: int):

    global current_players

    guild = interaction.guild

    public_vc = guild.get_channel(PUBLIC_VC_ID)
    closed_vc = guild.get_channel(CLOSED_VC_ID)

    role = guild.get_role(CODE_ROLE_ID)

    await interaction.response.defer()

    # ========================
    # REMOVE OLD PLAYERS
    # ========================

    for member in current_players:

        if is_whitelisted(member):
            continue

        try:
            await member.remove_roles(role)
        except:
            pass

        try:
            await member.move_to(public_vc)
        except:
            pass

    # ========================
    # BUILD FAIR QUEUE
    # ========================

    public_members = get_public_members(guild)

    eligible = [m for m in public_members if m not in current_players]

    if len(eligible) < amount:
        eligible = public_members

    if not eligible:
        await interaction.followup.send("No eligible players")
        return

    picked = random.sample(eligible, min(amount, len(eligible)))

    current_players = picked.copy()

    # ========================
    # MOVE AND GIVE ROLE
    # ========================

    for member in picked:

        try:
            await member.add_roles(role)
        except:
            pass

        try:
            await member.move_to(closed_vc)
        except:
            pass

    names = "\n".join([m.display_name for m in picked])

    await interaction.followup.send(
        f"Picked {len(picked)} players:\n{names}"
    )


# ========================
# START BOT
# ========================

bot.run(TOKEN)
