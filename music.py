import asyncio
import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from lyricsgenius import Genius
import re
import requests
from pytube import YouTube
import random
import datetime

# Bot configuration
TOKEN = 'MTI4OTU1OTA5MzY2MDQ4Nzc3Mw.GNnbhH.49bZBOSi-dfmrcm0PRb7lyCEc8obkiCGkXYf7k'
GUILD_ID = 1286329856761532478
SPOTIFY_CLIENT_ID = '5b2a977b13f648fa825bdebcb7519afc'
SPOTIFY_CLIENT_SECRET = 'a06b211758c046508ad0dccdc01a48c0'
GENIUS_ACCESS_TOKEN = 'd3hmehHD9py-UAy3xB5zZGutzZ4uY_9PQvHR_ATD-tHuwXmBkqPXDvMfso__mmS6'

# YouTube DL configuration
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'cookiefile': 'cookies.txt',
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'writesubtitles': True,
    'subtitleslangs': ['en'],
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)
sp = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET))
genius = Genius(GENIUS_ACCESS_TOKEN)

def create_now_playing_embed(song_title, artist, duration, current_time, thumbnail_url=None):
    embed = discord.Embed(title="Now Playing", color=discord.Color.blue())
    embed.add_field(name="Title", value=song_title, inline=False)
    embed.add_field(name="Artist", value=artist, inline=False)
    
    # Create progress bar
    bar_length = 20
    progress = int(current_time / duration * bar_length) if duration > 0 else 0
    progress_bar = "▬" * progress + "🔘" + "▬" * (bar_length - progress - 1)
    
    time_format = lambda t: str(datetime.timedelta(seconds=int(t)))
    embed.add_field(name="Progress", value=f"{progress_bar}\n{time_format(current_time)} / {time_format(duration)}", inline=False)
    
    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)
    
    return embed

class PlayerView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="⏮️", custom_id="restart")
    async def restart_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if bot.voice_client and bot.voice_client.is_playing():
            await seek(interaction, "0:00")
        await interaction.response.defer()

    @discord.ui.button(style=discord.ButtonStyle.primary, emoji="⏯️", custom_id="playpause")
    async def playpause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if bot.voice_client:
            if bot.voice_client.is_playing():
                bot.voice_client.pause()
            elif bot.voice_client.is_paused():
                bot.voice_client.resume()
        await interaction.response.defer()

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="⏭️", custom_id="skip")
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await skip(interaction)

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="🔀", custom_id="shuffle")
    async def shuffle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await shuffle_command(interaction)

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="🔁", custom_id="repeat")
    async def repeat_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Implement repeat functionality here
        await interaction.response.send_message("Repeat functionality not implemented yet.", ephemeral=True)

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="🎵", custom_id="lyrics")
    async def lyrics_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await lyrics(interaction)

def create_player_view():
    return PlayerView()


class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)
        self.voice_client = None
        self.current_song = None
        self.current_artist = None
        self.current_source = None
        self.queue = []
        self.skip_votes = set()
        self.volume = 0.5
        self.now_playing_message = None
        self.start_time = None
        self.current_duration = 0
        self.current_thumbnail = None

    async def setup_hook(self):
        await self.tree.sync(guild=discord.Object(id=GUILD_ID))
        self.loop.create_task(self.update_now_playing())

    def play_next(self):
        self.skip_votes.clear()
        if self.queue:
            next_song, next_title, next_artist, next_source = self.queue.pop(0)
            self.current_song = next_title
            self.current_artist = next_artist
            self.current_source = next_source
            # You might need to add logic here to get duration and thumbnail for the next song
            source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(next_song, **FFMPEG_OPTIONS))
            source.volume = self.volume
            self.voice_client.play(source, after=lambda e: play_next(self))
            self.start_time = discord.utils.utcnow()
            
            embed = create_now_playing_embed(next_title, next_artist, self.current_duration, 0, self.current_thumbnail)
            view = create_player_view()
            
            asyncio.create_task(self.now_playing_message.edit(embed=embed, view=view))
        else:
            self.current_song = None
            self.current_artist = None
            self.current_source = None
            self.current_duration = 0
            self.current_thumbnail = None
            self.now_playing_message = None
            self.start_time = None

    async def update_now_playing(self):
        while True:
            if self.voice_client and self.voice_client.is_playing() and self.now_playing_message:
                current_time = (discord.utils.utcnow() - self.start_time).total_seconds() if self.start_time else 0
                embed = create_now_playing_embed(self.current_song, self.current_artist, self.current_duration, current_time, self.current_thumbnail)
                view = create_player_view()
                await self.now_playing_message.edit(embed=embed, view=view)
            await asyncio.sleep(3)  # Update every 10 seconds


bot = MusicBot()

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')
    

async def ensure_voice_client(interaction: discord.Interaction):
    if interaction.user.voice is None:
        await interaction.response.send_message("You're not in a voice channel!")
        return False
    if bot.voice_client is None:
        bot.voice_client = await interaction.user.voice.channel.connect()
    elif bot.voice_client.channel != interaction.user.voice.channel:
        await bot.voice_client.move_to(interaction.user.voice.channel)
    return True

@bot.tree.command(name="playyt", description="Play a song from YouTube", guild=discord.Object(id=GUILD_ID))
async def play(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    if not await ensure_voice_client(interaction):
        return
    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))
        if 'entries' in data:
            data = data['entries'][0]
        song = data['url']
        title = data['title']
        artist = data.get('artist', 'Unknown Artist')
        if bot.voice_client.is_playing():
            bot.queue.append((song, title, artist, 'youtube'))
            await interaction.followup.send(f"Added to queue: {title}")
        else:
            bot.current_song = title
            bot.current_artist = artist
            bot.current_source = 'youtube'
            bot.current_thumbnail = data.get('thumbnail', None)
            source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(song, **FFMPEG_OPTIONS))
            source.volume = bot.volume
            bot.current_duration = data.get('duration', 0)
            embed = create_now_playing_embed(title, artist, bot.current_duration, 0, bot.current_thumbnail)
            view = create_player_view()

            bot.voice_client.play(source, after=lambda e: bot.play_next())
            bot.start_time = discord.utils.utcnow()
            bot.now_playing_message = await interaction.followup.send(embed=embed, view=view)
    except Exception as e:
        await interaction.followup.send(f"An error occurred: {str(e)}")

@bot.tree.command(name="play", description="Play a song from Spotify (URL or search)", guild=discord.Object(id=GUILD_ID))
async def playspotify(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    if not await ensure_voice_client(interaction):
        return
    try:
        if query.startswith('https://open.spotify.com/track/'):
            track_id = query.split('/')[-1].split('?')[0]
            track_info = sp.track(track_id)
        else:
            results = sp.search(q=query, type='track', limit=1)
            if not results['tracks']['items']:
                await interaction.followup.send("No Spotify tracks found.")
                return
            track_info = results['tracks']['items'][0]

        title = track_info['name']
        artist = track_info['artists'][0]['name']
        query = f"{title} {artist}"

        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch:{query}", download=False))

        if 'entries' in data:
            song = data['entries'][0]['url']
            if bot.voice_client.is_playing():
                bot.queue.append((song, title, artist, 'spotify'))
                await interaction.followup.send(f"Added to queue: {title} - {artist}")
            else:
                bot.current_song = title
                bot.current_artist = artist
                bot.current_source = 'spotify'
                bot.current_thumbnail = track_info['album']['images'][0]['url'] if track_info['album']['images'] else None
                source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(song, **FFMPEG_OPTIONS))
                source.volume = bot.volume
                bot.current_duration = track_info['duration_ms'] / 1000
                embed = create_now_playing_embed(title, artist, bot.current_duration, 0, bot.current_thumbnail)
                view = create_player_view()

                bot.voice_client.play(source, after=lambda e: bot.play_next())
                bot.start_time = discord.utils.utcnow()
                bot.now_playing_message = await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.followup.send("No results found.")
    except Exception as e:
        await interaction.followup.send(f"An error occurred: {str(e)}")

@bot.tree.command(name="skip", description="Skip the current song (requires 'Skipper' role)", guild=discord.Object(id=GUILD_ID))
async def skip(interaction: discord.Interaction):
    if bot.voice_client is None or not bot.voice_client.is_playing():
        await interaction.response.send_message("Nothing is playing right now.")
        return

    skipper_role = discord.utils.get(interaction.guild.roles, name="Skipper")
    if skipper_role in interaction.user.roles:
        bot.voice_client.stop()
        await interaction.response.send_message("Skipped the current song.")
    else:
        await voteskip(interaction)

@bot.tree.command(name="voteskip", description="Vote to skip the current song", guild=discord.Object(id=GUILD_ID))
async def voteskip(interaction: discord.Interaction):
    if bot.voice_client is None or not bot.voice_client.is_playing():
        await interaction.response.send_message("Nothing is playing right now.")
        return

    if interaction.user.voice is None or interaction.user.voice.channel != bot.voice_client.channel:
        await interaction.response.send_message("You need to be in the same voice channel to vote skip.")
        return

    bot.skip_votes.add(interaction.user.id)
    required_votes = len([m for m in bot.voice_client.channel.members if not m.bot]) // 2

    if len(bot.skip_votes) >= required_votes:
        bot.voice_client.stop()
        bot.skip_votes.clear()
        await interaction.response.send_message("Vote skip successful. Skipped the current song.")
    else:
        await interaction.response.send_message(f"Vote skip added. {len(bot.skip_votes)}/{required_votes} votes needed to skip.")

@bot.tree.command(name="queue", description="Show the current queue", guild=discord.Object(id=GUILD_ID))
async def queue(interaction: discord.Interaction):
    if not bot.queue:
        await interaction.response.send_message("The queue is empty.")
        return

    queue_list = "\n".join([f"{i+1}. {title} - {artist}" for i, (_, title, artist, _) in enumerate(bot.queue)])
    await interaction.response.send_message(f"Current queue:\n{queue_list}")

@bot.tree.command(name="leave", description="Leave the voice channel", guild=discord.Object(id=GUILD_ID))
async def leave(interaction: discord.Interaction):
    if bot.voice_client is None:
        await interaction.response.send_message("I'm not in a voice channel!")
        return

    await bot.voice_client.disconnect()
    bot.voice_client = None
    bot.queue.clear()
    bot.skip_votes.clear()
    await interaction.response.send_message("Left the voice channel")

@bot.tree.command(name="volume", description="Set the volume (0-100)", guild=discord.Object(id=GUILD_ID))
async def volume(interaction: discord.Interaction, volume: int):
    if volume < 0 or volume > 100:
        await interaction.response.send_message("Volume must be between 0 and 100.")
        return

    bot.volume = volume / 100
    if bot.voice_client and bot.voice_client.source:
        bot.voice_client.source.volume = bot.volume
    await interaction.response.send_message(f"Volume set to {volume}%")

@bot.tree.command(name="lyrics", description="Get lyrics for the current song or search for lyrics", guild=discord.Object(id=GUILD_ID))
async def lyrics(interaction: discord.Interaction, query: str = None):
    if query is None and bot.current_song is None:
        await interaction.response.send_message("No song is currently playing. Use /lyrics to search for lyrics.")
        return

    await interaction.response.defer()
    try:
        if query is None:
            # Try to get lyrics from the current song
            if bot.current_source == 'youtube':
                lyrics = await get_youtube_lyrics(bot.current_song)
            elif bot.current_source == 'spotify':
                lyrics = await get_spotify_lyrics(bot.current_song, bot.current_artist)
            else:
                lyrics = None

            if not lyrics:
                lyrics = await get_genius_lyrics(bot.current_song, bot.current_artist)

            if not lyrics:
                await interaction.followup.send(f"Couldn't find lyrics for {bot.current_song}. Try searching manually with /lyrics ")
                return

            song_info = f"{bot.current_song} by {bot.current_artist}"
        else:
            # Search for lyrics using the provided query
            lyrics = await get_genius_lyrics(query)
            song_info = query

        if lyrics:
            # Create an embed for better formatting
            embed = discord.Embed(title=f"Lyrics for {song_info}", color=discord.Color.blue())
            # Split lyrics into chunks of 4096 characters (Discord embed description limit)
            chunks = [lyrics[i:i+4096] for i in range(0, len(lyrics), 4096)]
            embed.description = chunks[0]
            if len(chunks) > 1:
                embed.add_field(name="\u200b", value=chunks[1], inline=False)
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(f"Couldn't find lyrics for {song_info}")
    except Exception as e:
        await interaction.followup.send(f"An error occurred while fetching lyrics: {str(e)}")

async def get_youtube_lyrics(song_title):
    try:
        search_url = f"https://www.youtube.com/results?search_query={song_title}+lyrics"
        html = await asyncio.to_thread(requests.get, search_url)
        video_ids = re.findall(r"watch\?v=(\S{11})", html.text)
        if video_ids:
            video_url = f"https://www.youtube.com/watch?v={video_ids[0]}"
            video = await asyncio.to_thread(YouTube, video_url)
            caption = video.captions.get_by_language_code('en')
            if caption:
                return caption.generate_srt_captions()
    except Exception:
        pass
    return None

async def get_spotify_lyrics(song_title, artist):
    try:
        track = sp.search(q=f"track:{song_title} artist:{artist}", type='track', limit=1)
        if track and track['tracks']['items']:
            track_id = track['tracks']['items'][0]['id']
            lyrics = sp.track_lyrics(track_id)
            if lyrics and 'lyrics' in lyrics:
                # Remove metadata and clean up the lyrics
                cleaned_lyrics = re.sub(r'^\d+\s*Contributors.*?Lyrics', '', lyrics['lyrics'], flags=re.DOTALL)
                cleaned_lyrics = re.sub(r'\d+Embed$', '', cleaned_lyrics, flags=re.DOTALL)
                cleaned_lyrics = re.sub(r'\[.*?\]', '', cleaned_lyrics)  # Remove [Verse], [Chorus], etc.
                return cleaned_lyrics.strip()
    except Exception:
        pass
    return None

async def get_genius_lyrics(song_title, artist=None):
    try:
        if artist:
            song = genius.search_song(song_title, artist)
        else:
            song = genius.search_song(song_title)
        if song:
            return song.lyrics
    except Exception:
        pass
    return None

@bot.tree.command(name="shuffle", description="Shuffle the current queue (requires Skipper role)", guild=discord.Object(id=GUILD_ID))
async def shuffle(interaction: discord.Interaction):
    skipper_role = discord.utils.get(interaction.guild.roles, name="Skipper")
    if skipper_role in interaction.user.roles:
        random.shuffle(bot.queue)
        await interaction.response.send_message("Queue shuffled!")
    else:
        await interaction.response.send_message("You need the Skipper role to shuffle the queue.", ephemeral=True)

@bot.tree.command(name="pause", description="Pause the currently playing song", guild=discord.Object(id=GUILD_ID))
async def pause(interaction: discord.Interaction):
    if bot.voice_client is None or not bot.voice_client.is_playing():
        await interaction.response.send_message("Nothing is playing right now.")
        return
    bot.voice_client.pause()
    await interaction.response.send_message("Paused the current song.")

@bot.tree.command(name="resume", description="Resume the paused song", guild=discord.Object(id=GUILD_ID))
async def resume(interaction: discord.Interaction):
    if bot.voice_client is None or not bot.voice_client.is_paused():
        await interaction.response.send_message("No song is paused right now.")
        return
    bot.voice_client.resume()
    await interaction.response.send_message("Resumed the paused song.")

@bot.tree.command(name="seek", description="Seek to a specific timestamp in the current song", guild=discord.Object(id=GUILD_ID))
async def seek(interaction: discord.Interaction, timestamp: str):
    if bot.voice_client is None or not bot.voice_client.is_playing():
        await interaction.response.send_message("No song is currently playing.")
        return

    try:
        # Convert timestamp to seconds
        time_parts = timestamp.split(':')
        if len(time_parts) == 2:
            minutes, seconds = map(int, time_parts)
            total_seconds = minutes * 60 + seconds
        elif len(time_parts) == 3:
            hours, minutes, seconds = map(int, time_parts)
            total_seconds = hours * 3600 + minutes * 60 + seconds
        else:
            raise ValueError("Invalid timestamp format. Use MM:SS or HH:MM:SS.")

        await interaction.response.defer()

        # Get the current song URL
        if bot.current_source == 'youtube':
            url = bot.current_song
        elif bot.current_source == 'spotify':
            # Perform a YouTube search for the Spotify song
            query = f"{bot.current_song} {bot.current_artist}"
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch:{query}", download=False))
            if 'entries' in data:
                url = data['entries'][0]['url']
            else:
                raise ValueError("Couldn't find a YouTube URL for the current Spotify song.")
        else:
            raise ValueError("Unknown audio source.")

        # Stop the current playback
        bot.voice_client.stop()

        # Create new FFMPEG options with seek
        seek_options = FFMPEG_OPTIONS.copy()
        seek_options['before_options'] = f"-ss {total_seconds} " + seek_options['before_options']

        # Create a new source with the seek option
        new_source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(url, **seek_options))
        new_source.volume = bot.volume

        # Play the new source
        bot.voice_client.play(new_source, after=lambda e: bot.play_next())

        await interaction.followup.send(f"Seeked to {timestamp}")

    except ValueError as e:
        await interaction.followup.send(str(e))
    except Exception as e:
        await interaction.followup.send(f"An error occurred while seeking: {str(e)}")

def seek_to_timestamp(voice_client, timestamp):
    """Seek or play the song from a specific timestamp."""
    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()  # Stop the current playback to seek to the new timestamp
    source = discord.FFmpegPCMAudio(voice_client.source.original.url, options=f'-ss {timestamp}')
    voice_client.play(source)  # Play from the specific timestamp

def play_next(self):
    self.skip_votes.clear()
    if self.queue:
        next_song, next_title, next_artist, next_source = self.queue.pop(0)
        self.current_song = next_title
        self.current_artist = next_artist
        self.current_source = next_source
        # You might need to add logic here to get duration and thumbnail for the next song
        source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(next_song, **FFMPEG_OPTIONS))
        source.volume = self.volume
        self.voice_client.play(source, after=lambda e: play_next())
        self.start_time = discord.utils.utcnow()
        
        embed = create_now_playing_embed(next_title, next_artist, self.current_duration, 0, self.current_thumbnail)
        view = create_player_view(self)
        
        asyncio.create_task(self.now_playing_message.edit(embed=embed, view=view))
    else:
        self.current_song = None
        self.current_artist = None
        self.current_source = None
        self.current_duration = 0
        self.current_thumbnail = None
        self.now_playing_message = None
        self.start_time = None

bot.run(TOKEN)
