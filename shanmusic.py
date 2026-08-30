from __future__ import annotations
import discord
from discord.ext import commands
from collections import deque
import yt_dlp
import asyncio
import os
import sys
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ─────────────────────────────────────────────
#  Load config from .env
# ─────────────────────────────────────────────
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    print("❌  DISCORD_TOKEN not found in .env — please add it.")
    exit(1)

# ─────────────────────────────────────────────
#  yt-dlp options  (stream only, no download)
# ─────────────────────────────────────────────
YDL_OPTIONS = {
    "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
    "format_sort": ["abr:desc", "asr:desc"],
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "extract_flat": False,
}

import shutil

FFMPEG_EXECUTABLE = (
    shutil.which("ffmpeg")
    or os.path.abspath("./bin/ffmpeg.exe")
    or "ffmpeg"
)

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn -ar 48000 -ac 2 -b:a 320k",
}

# ─────────────────────────────────────────────
#  Per-guild music state
# ─────────────────────────────────────────────
class GuildMusic:
    def __init__(self):
        self.queue: deque = deque()
        self.current: dict = None
        self.loop_track: bool = False
        self.loop_queue: bool = False
        self.volume: float = 0.5

guild_music: dict = {}

def get_state(guild_id: int) -> GuildMusic:
    if guild_id not in guild_music:
        guild_music[guild_id] = GuildMusic()
    return guild_music[guild_id]


# ─────────────────────────────────────────────
#  Helper: search / resolve via yt-dlp
# ─────────────────────────────────────────────
def fetch_track(query: str) -> dict:
    """Return track info dict, or None on failure."""
    # If not a URL, prefix with ytsearch:
    if not query.startswith("http"):
        query = f"ytsearch:{query}"
    try:
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(query, download=False)
            if "entries" in info:
                info = info["entries"][0]
            return {
                "title": info.get("title", "Unknown"),
                "url": info["url"],
                "webpage_url": info.get("webpage_url", ""),
                "duration": info.get("duration", 0),
                "thumbnail": info.get("thumbnail", ""),
                "uploader": info.get("uploader", "Unknown"),
            }
    except Exception as e:
        print(f"[yt-dlp] Error: {e}")
        return None


def fmt_duration(seconds: int) -> str:
    if not seconds:
        return "Live"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"


# ─────────────────────────────────────────────
#  Bot setup
# ─────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


# ─────────────────────────────────────────────
#  Playback engine
# ─────────────────────────────────────────────
async def play_next(ctx: commands.Context):
    state = get_state(ctx.guild.id)
    vc = ctx.voice_client

    if not vc or not vc.is_connected():
        return

    # Loop track
    if state.loop_track and state.current:
        track = state.current
    # Loop queue
    elif state.loop_queue and state.current:
        state.queue.append(state.current)
        track = state.queue.popleft() if state.queue else None
    # Normal: pop from queue
    else:
        track = state.queue.popleft() if state.queue else None

    if not track:
        state.current = None
        await ctx.send("✅ Queue finished. Leaving voice channel.", delete_after=15)
        await asyncio.sleep(1)
        await vc.disconnect()
        return

    state.current = track

    source = discord.FFmpegPCMAudio(track["url"], executable=FFMPEG_EXECUTABLE, **FFMPEG_OPTIONS)
    source = discord.PCMVolumeTransformer(source, volume=state.volume)

    def after_play(error):
        if error:
            print(f"[Player] Error: {error}")
        # Fire-and-forget next track on the event loop without blocking the thread with fut.result()
        asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)

    vc.play(source, after=after_play)

    # Now-playing embed
    embed = discord.Embed(
        title="🎵 Now Playing",
        description=f"**[{track['title']}]({track['webpage_url']})**",
        color=discord.Color.from_rgb(88, 101, 242),
    )
    embed.add_field(name="Duration", value=fmt_duration(track["duration"]), inline=True)
    embed.add_field(name="By", value=track["uploader"], inline=True)
    embed.add_field(
        name="Loop",
        value="🔂 Track" if state.loop_track else ("🔁 Queue" if state.loop_queue else "Off"),
        inline=True,
    )
    if track["thumbnail"]:
        embed.set_thumbnail(url=track["thumbnail"])
    embed.set_footer(text=f"Volume: {int(state.volume * 100)}%  |  Queue: {len(state.queue)} remaining")
    await ctx.send(embed=embed)


# ─────────────────────────────────────────────
#  Events
# ─────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅  Logged in as {bot.user} ({bot.user.id})")
    print(f"    Prefix: !   |   Guilds: {len(bot.guilds)}")
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening, name="!play | !help"
    ))


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return

    # Unwrap CommandInvokeError to get the actual underlying exception
    if isinstance(error, commands.CommandInvokeError):
        error = error.original

    # Suppress transient network/voice Gateway timeout messages
    if isinstance(error, (asyncio.TimeoutError, TimeoutError)):
        print(f"[Info] Suppressed transient TimeoutError: {error}")
        return

    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument — try `!help {ctx.command}`", delete_after=10)
    else:
        await ctx.send(f"❌ Error: {error}", delete_after=15)


# ─────────────────────────────────────────────
#  Commands
# ─────────────────────────────────────────────

@bot.command(name="play", aliases=["p"], help="Play a song by name or URL")
async def play(ctx, *, query: str):
    # Join voice channel
    if not ctx.author.voice:
        return await ctx.send("❌ You must be in a voice channel!", delete_after=10)

    vc = ctx.voice_client
    if vc and vc.channel != ctx.author.voice.channel:
        return await ctx.send("❌ I'm already in a different voice channel!", delete_after=10)

    if not vc:
        vc = await ctx.author.voice.channel.connect()

    state = get_state(ctx.guild.id)

    async with ctx.typing():
        track = await asyncio.to_thread(fetch_track, query)

    if not track:
        return await ctx.send("❌ Could not find anything for that query.", delete_after=10)

    state.queue.append(track)

    if not vc.is_playing() and not vc.is_paused():
        await play_next(ctx)
    else:
        embed = discord.Embed(
            title="➕ Added to Queue",
            description=f"**[{track['title']}]({track['webpage_url']})**",
            color=discord.Color.green(),
        )
        embed.add_field(name="Duration", value=fmt_duration(track["duration"]))
        embed.add_field(name="Position", value=f"#{len(state.queue)}")
        if track["thumbnail"]:
            embed.set_thumbnail(url=track["thumbnail"])
        await ctx.send(embed=embed)


@bot.command(name="skip", aliases=["s"], help="Skip the current song")
async def skip(ctx):
    vc = ctx.voice_client
    if not vc or not vc.is_playing():
        return await ctx.send("❌ Nothing is playing.", delete_after=8)
    state = get_state(ctx.guild.id)
    state.loop_track = False  # skip overrides track loop
    vc.stop()
    await ctx.send("⏭️ Skipped!", delete_after=8)


@bot.command(name="stop", aliases=["dc"], help="Stop music and leave the voice channel")
async def stop(ctx):
    vc = ctx.voice_client
    if not vc:
        return await ctx.send("❌ Not in a voice channel.", delete_after=8)
    state = get_state(ctx.guild.id)
    state.queue.clear()
    state.current = None
    state.loop_track = False
    state.loop_queue = False
    await vc.disconnect()
    await ctx.send("⏹️ Stopped and left the voice channel.")


@bot.command(name="pause", aliases=["pp"], help="Pause playback")
async def pause(ctx):
    vc = ctx.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await ctx.send("⏸️ Paused.", delete_after=8)
    else:
        await ctx.send("❌ Nothing is playing.", delete_after=8)


@bot.command(name="resume", aliases=["r"], help="Resume playback")
async def resume(ctx):
    vc = ctx.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await ctx.send("▶️ Resumed.", delete_after=8)
    else:
        await ctx.send("❌ Nothing is paused.", delete_after=8)


@bot.command(name="volume", aliases=["vol"], help="Set volume 0–100  (e.g. !volume 70)")
async def volume(ctx, level: int):
    if not 0 <= level <= 100:
        return await ctx.send("❌ Volume must be between 0 and 100.", delete_after=8)
    state = get_state(ctx.guild.id)
    state.volume = level / 100
    vc = ctx.voice_client
    if vc and vc.source:
        vc.source.volume = state.volume
    await ctx.send(f"🔊 Volume set to **{level}%**", delete_after=8)


@bot.command(name="loop", aliases=["l"], help="Loop: !loop track | !loop queue | !loop off")
async def loop(ctx, mode: str = "track"):
    state = get_state(ctx.guild.id)
    mode = mode.lower()
    if mode in ("track", "song", "t"):
        state.loop_track = True
        state.loop_queue = False
        await ctx.send("🔂 Looping **current track**.", delete_after=10)
    elif mode in ("queue", "q", "all"):
        state.loop_queue = True
        state.loop_track = False
        await ctx.send("🔁 Looping **entire queue**.", delete_after=10)
    elif mode in ("off", "none", "0"):
        state.loop_track = False
        state.loop_queue = False
        await ctx.send("➡️ Loop **off**.", delete_after=10)
    else:
        await ctx.send("❌ Usage: `!loop track` | `!loop queue` | `!loop off`", delete_after=10)


@bot.command(name="queue", aliases=["q"], help="Show the current queue")
async def queue(ctx):
    state = get_state(ctx.guild.id)
    if not state.current and not state.queue:
        return await ctx.send("📭 The queue is empty.", delete_after=10)

    lines = []
    if state.current:
        lines.append(f"**Now Playing:**\n🎵 {state.current['title']} `{fmt_duration(state.current['duration'])}`\n")

    if state.queue:
        lines.append("**Up Next:**")
        for i, track in enumerate(list(state.queue)[:15], 1):
            lines.append(f"`{i}.` {track['title']} `{fmt_duration(track['duration'])}`")
        if len(state.queue) > 15:
            lines.append(f"... and {len(state.queue) - 15} more tracks")

    loop_status = "🔂 Track" if state.loop_track else ("🔁 Queue" if state.loop_queue else "Off")
    embed = discord.Embed(
        title="📋 Queue",
        description="\n".join(lines),
        color=discord.Color.from_rgb(88, 101, 242),
    )
    embed.set_footer(text=f"Loop: {loop_status}  |  Volume: {int(state.volume * 100)}%")
    await ctx.send(embed=embed)


@bot.command(name="nowplaying", aliases=["np"], help="Show the currently playing song")
async def nowplaying(ctx):
    state = get_state(ctx.guild.id)
    if not state.current:
        return await ctx.send("❌ Nothing is currently playing.", delete_after=10)
    track = state.current
    embed = discord.Embed(
        title="🎵 Now Playing",
        description=f"**[{track['title']}]({track['webpage_url']})**",
        color=discord.Color.from_rgb(88, 101, 242),
    )
    embed.add_field(name="Duration", value=fmt_duration(track["duration"]))
    embed.add_field(name="By", value=track["uploader"])
    if track["thumbnail"]:
        embed.set_thumbnail(url=track["thumbnail"])
    await ctx.send(embed=embed)


@bot.command(name="shuffle", help="Shuffle the queue")
async def shuffle(ctx):
    state = get_state(ctx.guild.id)
    if len(state.queue) < 2:
        return await ctx.send("❌ Not enough songs in the queue to shuffle.", delete_after=8)
    import random
    q_list = list(state.queue)
    random.shuffle(q_list)
    state.queue = deque(q_list)
    await ctx.send(f"🔀 Shuffled **{len(state.queue)}** songs in the queue!")


@bot.command(name="remove", aliases=["rm"], help="Remove a song from the queue by position  (e.g. !remove 2)")
async def remove(ctx, position: int):
    state = get_state(ctx.guild.id)
    if not state.queue:
        return await ctx.send("❌ The queue is empty.", delete_after=8)
    if not 1 <= position <= len(state.queue):
        return await ctx.send(f"❌ Invalid position. Queue has {len(state.queue)} songs.", delete_after=8)
    q_list = list(state.queue)
    removed = q_list.pop(position - 1)
    state.queue = deque(q_list)
    await ctx.send(f"🗑️ Removed **{removed['title']}** from the queue.", delete_after=10)


@bot.command(name="clear", help="Clear the entire queue (keeps current song playing)")
async def clear(ctx):
    state = get_state(ctx.guild.id)
    state.queue.clear()
    await ctx.send("🗑️ Queue cleared.", delete_after=8)


@bot.command(name="help", help="Show all commands")
async def help_cmd(ctx):
    embed = discord.Embed(
        title="🎵 ShanMusic — Commands",
        color=discord.Color.from_rgb(88, 101, 242),
    )
    cmds = [
        ("!play  `<song / URL>`",    "Play a song (YouTube, search query, or URL)"),
        ("!skip  `(or !s)`",         "Skip the current song"),
        ("!stop  `(or !dc)`",        "Stop music and leave voice channel"),
        ("!pause `(or !pp)`",        "Pause playback"),
        ("!resume `(or !r)`",        "Resume playback"),
        ("!volume `<0-100>`",        "Set playback volume"),
        ("!loop `track/queue/off`",  "Toggle looping mode"),
        ("!queue `(or !q)`",         "Show the current queue"),
        ("!nowplaying `(or !np)`",   "Show the currently playing song"),
        ("!shuffle",                 "Shuffle the queue"),
        ("!remove `<position>`",     "Remove a song from the queue"),
        ("!clear",                   "Clear all songs from the queue"),
    ]
    for name, value in cmds:
        embed.add_field(name=name, value=value, inline=False)
    embed.set_footer(text="ShanMusic Bot | Powered by yt-dlp + discord.py")
    await ctx.send(embed=embed)


# ─────────────────────────────────────────────
#  Run
# ─────────────────────────────────────────────
bot.run(TOKEN)
