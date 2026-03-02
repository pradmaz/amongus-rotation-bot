import discord
from discord.ext import commands
from discord import app_commands
import random
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'Bot is running')

def run_server():
    server = HTTPServer(('0.0.0.0', 8080), Handler)
    server.serve_forever()

threading.Thread(target=run_server, daemon=True).start()

TOKEN = os.getenv("TOKEN")

PUBLIC_VC_ID = 1271597939730550885
CLOSED_VC_ID = 1331233909224247357
ROLE_ID = 1434466837243887687

GUILD_ID = 844092170524688394

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
        print("Commands synced")

bot = Bot()

current_batch = []
last_batch = []

def get_public_members(guild):
    vc = guild.get_channel(PUBLIC_VC_ID)
    return [m for m in vc.members if not m.bot]

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.tree.command(name="pick")
@app_commands.describe(amount="Number of players")
async def pick(interaction: discord.Interaction, amount: int):

    global current_batch, last_batch

    guild = interaction.guild
    public_vc = guild.get_channel(PUBLIC_VC_ID)
    closed_vc = guild.get_channel(CLOSED_VC_ID)
    role = guild.get_role(ROLE_ID)

    await interaction.response.defer()

    for member in current_batch:
        try:
            await member.remove_roles(role)
            await member.move_to(public_vc)
        except:
            pass

    last_batch = current_batch.copy()
    current_batch = []

    waiting = get_public_members(guild)

    selected = []

    if len(waiting) >= amount:
        selected = random.sample(waiting, amount)
    else:
        selected = waiting.copy()

        remaining = amount - len(selected)

        eligible = [m for m in last_batch if m not in selected]

        if eligible:
            refill = random.sample(
                eligible,
                min(remaining, len(eligible))
            )
            selected.extend(refill)

    for member in selected:
        try:
            await member.add_roles(role)
            await member.move_to(closed_vc)
        except:
            pass

    current_batch = selected

    await interaction.followup.send(f"Picked {len(selected)} players.")


bot.run(TOKEN)

