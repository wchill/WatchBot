import discord
import asyncio
import ffmpy
from pymediainfo import MediaInfo

import os
import sys
import threading

import ruamel.yaml

CONFIG_FILE = 'config.yml'

with open(CONFIG_FILE, 'r') as f:
    config = ruamel.yaml.load(f.read(), ruamel.yaml.RoundTripLoader)

DISCORD_CLIENT_KEY = config['login']['discord_client_key']

STREAM_URL = config['stream']['stream_url']
RTMP_ENDPOINT = config['stream']['rtmp_endpoint']
MEDIA_DIRECTORY = config['stream']['media_directory']
CHANNEL_WHITELIST = config['channels']['whitelist']
FONT_FILE = config['ffmpeg']['font_file']


client = discord.Client()
ffmpeg_process = None

def is_safe_path(basedir, path, follow_symlinks=True):
    # resolves symbolic links
    if follow_symlinks:
        return os.path.realpath(path).startswith(basedir)

    return os.path.abspath(path).startswith(basedir)


def generate_game_from_file(filename):
    filename_no_ext = os.path.splitext(filename)[0]
    return discord.Game(name=filename_no_ext, url=STREAM_URL, type=1)


async def set_bot_presence(path):
    if path:
        filename = os.path.basename(path)
        bot_game = generate_game_from_file(filename)
        await client.change_presence(game=bot_game, status=None, afk=False)
    else:
        await client.change_presence(game=None, status=None, afk=False)


def get_track_info(filename):
    mi = MediaInfo.parse(filename)
    audio_tracks, subtitle_tracks = [], []
    for track in mi.tracks:
        if track.track_type == 'Audio':
            audio_tracks.append(track)
        elif track.track_type == 'Text':
            subtitle_tracks.append(track)

    audio_track_desc = [
        '#{num}: {name} ({lang}, {codec} - {channels})'.format(
            num=track.stream_identifier + 1,
            name=track.title or 'Untitled',
            lang=track.other_language[0] or 'Unknown language',
            codec=track.format or 'Unknown codec',
            channels=(str(track.channel_s) or 'Unknown') + ' channels'
        ) for track in audio_tracks
    ]

    subtitle_track_desc = [
        '#{num}: {name} ({lang})'.format(
            num=track.stream_identifier + 1,
            name=track.title or 'Untitled',
            lang=track.language or 'Unknown language'
        ) for track in subtitle_tracks
    ]

    return audio_track_desc, subtitle_track_desc


async def stop_video(notify_channel=None, finished=False):
    # TODO: Locking
    global ffmpeg_process
    if ffmpeg_process is not None:
        ffmpeg_process.process.terminate()
        ffmpeg_process = None
        if finished and notify_channel:
            await client.send_message(notify_channel, 'Stream finished.')
        elif notify_channel:
            await client.send_message(notify_channel, 'Stream stopped.')
    await set_bot_presence(None)


async def play_video(file_path, audio_track=1, subtitle_track=None, seek_time=0, notify_channel=None):

    output_params = [
        '-ss', str(seek_time),
        '-i', file_path,
        '-map', '0:v:0',
        '-map', '0:a:{}'.format(audio_track - 1)
    ]

    vf_str = 'setpts=PTS+{}/TB,'.format(seek_time)
    if subtitle_track is not None:
        vf_str += 'subtitles=\'{}\':si={},'.format(file_path, subtitle_track - 1)
    vf_str += 'drawtext=\'fontfile={}: fontcolor=white: x=0: y=h-line_h-5: fontsize=24: boxcolor=black@0.5: box=1: text=%{{pts\\:hms}}\''.format(FONT_FILE)

    # TODO: make these more configurable
    output_params += [
        '-vf', vf_str,
        '-vcodec', 'libx264',
        '-preset', 'veryfast',
        '-maxrate', '4500k',
        '-bufsize', '1125k',
        '-pix_fmt', 'yuv420p',
        '-g', '24',
        '-c:a', 'libfdk_aac', '-ab', '128k',
        '-ac', '2',
        '-ar', '44100',
        '-probesize', '32',
        '-analyzeduration', '500000',
        '-flush_packets', '1',
        '-f', 'flv'
    ]

    ff = ffmpy.FFmpeg(
        global_options=['-re'],
        inputs={file_path: None},
        outputs={RTMP_ENDPOINT: output_params}
    )

    loop = asyncio.get_event_loop()

    await stop_video(notify_channel=notify_channel)
    await set_bot_presence(file_path)

    if notify_channel:
        await client.send_message(notify_channel, 'Stream started.')

    ffmpeg_process = ff
    await loop.run_in_executor(None, ff.run)
    await stop_video(notify_channel=notify_channel, finished=True)


@client.event
async def on_ready():
    print('Logged in as')
    print(client.user.name)
    print(client.user.id)
    print('------')


@client.event
async def on_message(message):
    if not message.channel.is_private and message.channel.name in CHANNEL_WHITELIST:
        if message.content.startswith('!stream '):
            params = message.content.partition(' ')[2]
            file_path = os.path.join(MEDIA_DIRECTORY, params)

            # prevent path traversal
            if not is_safe_path(MEDIA_DIRECTORY, file_path, follow_symlinks=False):
                print(MEDIA_DIRECTORY)
                print(file_path)
                print(os.path.realpath(file_path))
                await client.send_message(message.channel, 'Nice try')
                return

            if not os.path.exists(file_path):
                print(MEDIA_DIRECTORY)
                print(file_path)
                print(os.path.realpath(file_path))
                await client.send_message(message.channel, 'File does not exist.')
                return

            audio_tracks, subtitle_tracks = get_track_info(file_path)
            audio_track = 1
            subtitle_track = 1 if len(subtitle_tracks) > 0 else None

            def check(num, msg):
                s = msg.content
                return s.isdigit() and int(s) > 0 and int(s) <= num

            # Ask user to select audio track if multiple present
            if len(audio_tracks) > 1:
                await client.send_message(message.channel, 'Please select an audio track:\n' + '\n'.join(audio_tracks))
                message = await client.wait_for_message(timeout=30, author=message.author, check=lambda x: check(len(audio_tracks), x))
                if message is None:
                    await client.send_message(message.channel, 'No response received within 30 seconds. Cancelling stream.')
                    return
                audio_track = int(message.content)

            # Ask user to select subtitle track if multiple present
            if len(subtitle_tracks) > 1:
                await client.send_message(message.channel, 'Please select a subtitle track:\n' + '\n'.join(subtitle_tracks))
                message = await client.wait_for_message(timeout=30, author=message.author, check=lambda x: check(len(subtitle_tracks), x))
                if message is None:
                    await client.send_message(message.channel, 'No response received within 30 seconds. Cancelling stream.')
                    return
                subtitle_track = int(message.content)

            await play_video(file_path, audio_track, subtitle_track, 0.0, notify_channel=message.channel)


client.run(DISCORD_CLIENT_KEY)
