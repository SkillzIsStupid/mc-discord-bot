import os
import subprocess
import discord
from discord.ext import commands, tasks
from discord import app_commands
from mcstatus import JavaServer
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
ADMIN_ROLE = os.getenv("ADMIN_ROLE_NAME")

STATUS_CHANNEL_ID = int(os.getenv("STATUS_CHANNEL_ID"))
ANNOUNCE_CHANNEL_ID = int(os.getenv("ANNOUNCE_CHANNEL_ID"))

MC_HOST = os.getenv("MC_HOST")
MC_PORT = int(os.getenv("MC_PORT"))

SERVER_PATH = os.getenv("SERVER_PATH")
START_COMMAND = os.getenv("START_COMMAND")

intents = discord.Intents.default()
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

server = JavaServer.lookup(f"{MC_HOST}:{MC_PORT}")

status_message = None
last_status = None
mc_process = None


# -------------------------
def is_admin(interaction: discord.Interaction):
    return any(role.name == ADMIN_ROLE for role in interaction.user.roles)


# -------------------------
def get_mc_status():
    try:
        status = server.status()
        players = []

        if status.players.sample:
            players = [p.name for p in status.players.sample]

        return True, players, status.players.online, status.players.max
    except:
        return False, [], 0, 0


# -------------------------
def build_embed(online, players, count, maxp):
    if not online:
        return discord.Embed(
            title="🔴 Server Offline",
            description="Minecraft server is currently down.",
            color=discord.Color.red()
        )

    embed = discord.Embed(
        title="🟢 Server Online",
        color=discord.Color.green()
    )

    embed.add_field(name="Players", value=f"{count}/{maxp}", inline=False)

    embed.add_field(
        name="Online Players",
        value="\n".join(players) if players else "No players online",
        inline=False
    )

    return embed


# -------------------------
@tasks.loop(seconds=30)
async def update_status():
    global status_message, last_status

    channel = bot.get_channel(STATUS_CHANNEL_ID)
    if not channel:
        return

    online, players, count, maxp = get_mc_status()
    embed = build_embed(online, players, count, maxp)

    if status_message is None:
        status_message = await channel.send(embed=embed)
    else:
        try:
            await status_message.edit(embed=embed)
        except:
            status_message = await channel.send(embed=embed)

    # Detect crash
    if last_status is True and online is False:
        role = discord.utils.get(channel.guild.roles, name=ADMIN_ROLE)
        if role:
            await channel.send(f"{role.mention} 🚨 Server is DOWN!")

    last_status = online


# -------------------------
@tree.command(name="status", description="Check Minecraft server status")
async def status(interaction: discord.Interaction):
    online, players, count, maxp = get_mc_status()
    await interaction.response.send_message(
        embed=build_embed(online, players, count, maxp)
    )


# -------------------------
@tree.command(name="start", description="Start Minecraft server")
async def start_server(interaction: discord.Interaction):
    global mc_process

    if not is_admin(interaction):
        await interaction.response.send_message("❌ Not allowed", ephemeral=True)
        return

    if mc_process:
        await interaction.response.send_message("⚠️ Server already running")
        return

    try:
        mc_process = subprocess.Popen(
            START_COMMAND,
            cwd=SERVER_PATH,
            shell=True
        )
        await interaction.response.send_message("🟢 Server starting...")
    except Exception as e:
        await interaction.response.send_message(f"Error: {e}")


# -------------------------
@tree.command(name="stop", description="Stop Minecraft server")
async def stop_server(interaction: discord.Interaction):
    global mc_process

    if not is_admin(interaction):
        await interaction.response.send_message("❌ Not allowed", ephemeral=True)
        return

    if not mc_process:
        await interaction.response.send_message("⚠️ Server not running")
        return

    try:
        mc_process.terminate()
        mc_process = None
        await interaction.response.send_message("🔴 Server stopped")
    except Exception as e:
        await interaction.response.send_message(f"Error: {e}")


# -------------------------
@tree.command(name="announce", description="Send announcement")
@app_commands.describe(message="Message to announce")
async def announce(interaction: discord.Interaction, message: str):

    if not is_admin(interaction):
        await interaction.response.send_message("❌ Not allowed", ephemeral=True)
        return

    channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if channel:
        await channel.send(f"📢 **Announcement:** {message}")

    # OPTIONAL: send to Minecraft via RCON
    try:
        from mcrcon import MCRcon
        rcon = MCRcon("localhost", "your_rcon_password", port=25575)
        rcon.connect()
        rcon.command(f"say {message}")
        rcon.disconnect()
    except:
        pass

    await interaction.response.send_message("✅ Announcement sent!", ephemeral=True)


# -------------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    try:
        synced = await bot.tree.sync()
        print(f"GLOBAL SYNC: {len(synced)} commands")
    except Exception as e:
        print(e)

    update_status.start()

# -------------------------
bot.run(TOKEN)
