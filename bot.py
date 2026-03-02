import discord
from discord.ext import commands
from discord import app_commands
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# =========================
# KEEP ALIVE SERVER (Railway fix)
# =========================

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'BotMaz running')

def run_server():
    server = HTTPServer(('0.0.0.0', 8080), Handler)
    server.serve_forever()

threading.Thread(target=run_server, daemon=True).start()

# =========================
# CONFIGURATION
# =========================

TOKEN = os.getenv("TOKEN")

GUILD_ID = 844092170524683894

PUBLIC_VC_ID = 1271597939730550885
CLOSED_VC_ID = 1331233909224247357

ROLE_ID = 1434466837243887687  # Among us Code
WHITELIST_ROLE_ID = 1478003169232683008  # Among us Whitelist
BLACKLIST_ROLE_ID = 1478003080745451731  # Among us Blacklist

# =========================
# BOT SETUP
# =========================

intents = discord.Intents.default()
intents.members = True
intents.voice_states = True
intents.guilds = True

class Bot(commands.Bot):

    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):

        guild = discord.Object(id=GUILD_ID)

        self.tree.copy_global_to(guild=guild)

        await self.tree.sync(guild=guild)

        print("Commands synced instantly")

bot = Bot()

# =========================
# QUEUE STORAGE
# =========================

current_batch = []
queue_order = []
last_pick_amount = 0

# =========================
# READY EVENT
# =========================

@bot.event
async def on_ready():

    print(f"Logged in as {bot.user}")

# =========================
# PICK COMMAND (Fair Queue)
# =========================

@bot.tree.command(name="pick", description="Pick players fairly")
@app_commands.describe(amount="Number of players")

async def pick(interaction: discord.Interaction, amount: int):

    global current_batch, queue_order, last_pick_amount

    await interaction.response.defer()

    guild = interaction.guild

    public_vc = guild.get_channel(PUBLIC_VC_ID)

    closed_vc = guild.get_channel(CLOSED_VC_ID)

    code_role = guild.get_role(ROLE_ID)

    whitelist_role = guild.get_role(WHITELIST_ROLE_ID)

    blacklist_role = guild.get_role(BLACKLIST_ROLE_ID)

    # STEP 1: Move previous batch back (except whitelist)

    returning = []

    for member in current_batch:

        if whitelist_role in member.roles:
            continue

        try:
            await member.remove_roles(code_role)

            await member.move_to(public_vc)

            returning.append(member)

        except:
            pass

    queue_order.extend(returning)

    current_batch = []

    # STEP 2: Add eligible public players to queue

    public_members = [

        m for m in public_vc.members

        if not m.bot and blacklist_role not in m.roles

    ]

    for member in public_members:

        if member not in queue_order:

            queue_order.append(member)

    # Remove invalid members

    queue_order = [

        m for m in queue_order

        if m in public_vc.members and blacklist_role not in m.roles

    ]

    # STEP 3: Select fairly

    selected = queue_order[:amount]

    queue_order = queue_order[amount:]

    # STEP 4: Assign role and move

    for member in selected:

        try:

            await member.add_roles(code_role)

            await member.move_to(closed_vc)

        except:
            pass

    current_batch = selected

    last_pick_amount = amount

    await interaction.followup.send(

        f"✅ Picked {len(selected)} players\n"

        f"👥 Remaining in queue: {len(queue_order)}"

    )

# =========================
# QUEUE COMMAND
# =========================

@bot.tree.command(name="queue", description="Show queue size")

async def queue(interaction: discord.Interaction):

    await interaction.response.defer()

    await interaction.followup.send(

        f"👥 Players waiting in queue: {len(queue_order)}"

    )

# =========================
# RESET COMMAND
# =========================

@bot.tree.command(name="reset", description="Reset queue system")

async def reset(interaction: discord.Interaction):

    global current_batch, queue_order

    await interaction.response.defer()

    guild = interaction.guild

    public_vc = guild.get_channel(PUBLIC_VC_ID)

    code_role = guild.get_role(ROLE_ID)

    whitelist_role = guild.get_role(WHITELIST_ROLE_ID)

    moved = 0

    for member in current_batch:

        if whitelist_role in member.roles:
            continue

        try:

            await member.remove_roles(code_role)

            await member.move_to(public_vc)

            moved += 1

        except:
            pass

    current_batch = []

    queue_order = []

    await interaction.followup.send(

        f"🔄 Reset complete. Moved {moved} players."

    )

# =========================
# RUN BOT
# =========================

bot.run(TOKEN)
