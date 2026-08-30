# 🎵 ShanMusic — Discord Music Bot (Python)

A simple, fast, and feature-packed Discord Music Bot built with **Python 3.12**, **discord.py**, and **yt-dlp**.

---

## 🌟 Features

- 🎶 **Play Music**: Stream audio directly from YouTube URLs or search queries.
- 📋 **Queue Management**: Full queue support with `!queue`, `!remove <pos>`, `!clear`, and `!shuffle`.
- 🔂 **Looping Modes**: Loop single track (`!loop track`), loop entire queue (`!loop queue`), or turn loop off (`!loop off`).
- 🔊 **Volume Control**: Change player volume dynamically from 0 to 100 (`!volume 70`).
- 🖼️ **Rich Embed Cards**: Beautiful embeds with thumbnails, song duration, and uploader info.
- ⚡ **No Java / No Lavalink**: Runs directly using `discord.py` and local FFmpeg.

---

## 📋 Commands

| Command | Syntax | Description |
|---|---|---|
| `!play` | `!play <song name or URL>` | Play a song or add it to the queue |
| `!skip` | `!skip` (or `!s`) | Skip the currently playing track |
| `!stop` | `!stop` (or `!dc`) | Stop music playback and leave voice channel |
| `!pause` | `!pause` (or `!pp`) | Pause playback |
| `!resume` | `!resume` (or `!r`) | Resume playback |
| `!volume` | `!volume <0-100>` | Adjust player volume |
| `!loop` | `!loop track/queue/off` | Set loop mode |
| `!queue` | `!queue` (or `!q`) | Display current queue |
| `!nowplaying` | `!nowplaying` (or `!np`) | Display current track info |
| `!shuffle` | `!shuffle` | Shuffle upcoming tracks in queue |
| `!remove` | `!remove <position>` | Remove a track from the queue |
| `!clear` | `!clear` | Clear all upcoming tracks in queue |
| `!help` | `!help` | Display interactive command embed |

---

## ⚙️ How to Run

### 🐳 Option A: Using Docker (Recommended)

1. Ensure Docker Desktop is running and `.env` has your `DISCORD_TOKEN`.
2. Start the container in background:
   ```bash
   docker compose up -d --build
   ```
3. View logs:
   ```bash
   docker compose logs -f
   ```
4. Stop container:
   ```bash
   docker compose down
   ```

---

### 🐍 Option B: Running Locally

1. Ensure Python 3.12+ is installed and dependencies are present:
   ```bash
   pip install -r requirements.txt
   ```

2. Add your Discord Bot Token to the `.env` file:
   ```env
   DISCORD_TOKEN=your_bot_token_here
   ```

3. Start the bot:
   ```bash
   python shanmusic.py
   ```
