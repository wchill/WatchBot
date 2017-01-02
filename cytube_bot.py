import os
import asyncio
import collections

import discord
from discord.ext import commands

from utils import ask_for_int, parse_timestamp, escape_code_block, format_file_entry, format_dir_entry
import media_player
import file_explorer


class CytubeBot(object):
    def __init__(self, bot, stream_url, rtmp_endpoint, media_directory, channel_whitelist):
        self._bot = bot

        self._stream_url = stream_url
        self._rtmp_endpoint = rtmp_endpoint
        self._channel_whitelist = channel_whitelist

        self._file_explorer = file_explorer.FileExplorer(media_directory)
        self._media_player = media_player.DiscordMediaPlayer(self._rtmp_endpoint)

        self._last_ls_cache = (None, None)

        # Start the media queue
        self._media_queue = collections.deque()
        asyncio.ensure_future(self._process_media_queue())

        self._backup_queue = None

    async def set_bot_presence(self, name=None):
        bot_game = None

        if name:
            bot_game = discord.Game(name=name, url=self._stream_url, type=1)

        await self._bot.change_presence(game=bot_game, status=None, afk=False)

    async def on_ready(self):
        print('Logged in as {}'.format(self._bot.user.name))
        print('--------------')

    async def _start_stream(self, relative_path: str):
        await self._bot.say('Selected file: `{}`.'.format(escape_code_block(os.path.basename(relative_path))))
        absolute_path = self._file_explorer.get_complete_path(relative_path)

        audio_tracks, subtitle_tracks = self._media_player.get_human_readable_track_info(absolute_path)
        audio_track = 1
        subtitle_track = 1 if len(subtitle_tracks) > 0 else None

        # Ask user to select audio track if multiple present
        if len(audio_tracks) > 1:
            ask_str = 'Please select an audio track:\n```{}```'.format(escape_code_block('\n'.join(audio_tracks)))
            audio_track = await ask_for_int(self._bot, ask_str, lower_bound=1,
                                            upper_bound=len(audio_tracks) + 1, default=1)

        # Ask user to select subtitle track if multiple present
        if len(subtitle_tracks) > 1:
            ask_str = 'Please select a subtitle track:\n```{}```'.format(escape_code_block('\n'.join(subtitle_tracks)))
            subtitle_track = await ask_for_int(self._bot, ask_str, lower_bound=1,
                                               upper_bound=len(subtitle_tracks) + 1, default=1)

        await self._bot.say('Added to queue (#{}).'.format(len(self._media_queue) + 1))

        self._media_queue.append(
            media_player.Video(absolute_path, audio_track=audio_track, subtitle_track=subtitle_track))

    async def _process_media_queue(self):
        while True:
            video = None
            while video is None:
                try:
                    video = self._media_queue.popleft()
                except IndexError:
                    await asyncio.sleep(1)
            await self.set_bot_presence(video.name)
            await self._media_player.play_video(video)
            await self.set_bot_presence()

    @commands.group(name='stream', pass_context=True, no_pm=True)
    async def stream(self, ctx):
        if ctx.invoked_subcommand is None:
            await self._bot.say('Invalid stream command passed.')

    @stream.command(name='play', no_pm=True)
    async def start_stream(self, *, file: str):
        try:
            num = int(file)
            _, files = self._last_ls_cache

            if files is None:
                _, files = self.get_sorted_files_and_dirs()

            if num < 1 or num > len(files):
                await self._bot.say('Invalid option.')
                return

            file = files[num - 1].name
        except ValueError:
            pass

        if not self._file_explorer.file_exists(file):
            await self._bot.say('File does not exist.')
            return

        await self._start_stream(file)

    @stream.command(name='skip', no_pm=True)
    async def skip_stream(self):
        if not self._media_player.is_video_playing():
            await self._bot.say('Stream not currently playing.')
            return
        await self._bot.say('Skipping current video.')
        await self._media_player.stop_video()

    @stream.command(name='pause', no_pm=True)
    async def pause_stream(self):
        if not self._media_player.is_video_playing():
            await self._bot.say('Stream not currently playing.')
            return

        self._backup_queue = collections.deque()
        self._backup_queue.extend(self._media_queue)
        self._media_queue.clear()

        video = self._media_player.get_current_video()
        video.seek_time, _ = self._media_player.get_video_time()
        self._backup_queue.appendleft(video)

        await self._media_player.stop_video()
        await self.set_bot_presence()
        await self._bot.say('Stream paused at {}.'.format(self._media_player.convert_secs_to_str(video.seek_time)))

    @stream.command(name='resume', no_pm=True)
    async def resume_stream(self):
        if self._backup_queue is None:
            await self._bot.say('Stream not currently paused.')
            return

        self._media_queue.extend(self._backup_queue)
        self._backup_queue = None
        await self._bot.say('Resuming stream.')

    @stream.command(name='stop', no_pm=True)
    async def stop_stream(self):
        if not self._media_player.is_video_playing():
            await self._bot.say('Stream not currently playing.')
            return

        self._media_queue.clear()

        _, current_time, _ = await self._media_player.stop_video()
        await self.set_bot_presence()
        if current_time:
            await self._bot.say('Stream stopped at {}.'.format(self._media_player.convert_secs_to_str(current_time)))
        else:
            await self._bot.say('Stream stopped.')

    async def _seek_stream(self, time):
        if not self._media_player.is_video_playing():
            await self._bot.say('Stream not currently playing.')
            return

        await self._bot.say('Restarting stream at {}.'.format(self._media_player.convert_secs_to_str(time)))
        video = self._media_player.get_current_video()
        video.seek_time = time
        self._media_queue.appendleft(video)
        await self._media_player.stop_video()

    @stream.command(name='seek', no_pm=True)
    async def seek_stream(self, timestamp: str):
        time = parse_timestamp(timestamp)
        if time:
            await self._seek_stream(time)
        else:
            await self._bot.say('Invalid parameter.')

    @stream.command(name='ff', no_pm=True)
    async def ff_stream(self, length: str):
        time = parse_timestamp(length)
        if time:
            current, _ = self._media_player.get_video_time()
            await self._seek_stream(current + time)
        else:
            await self._bot.say('Invalid parameter.')

    @stream.command(name='rew', no_pm=True)
    async def rew_stream(self, length: str):
        time = parse_timestamp(length)
        if time:
            current, _ = self._media_player.get_video_time()

            if current + time < 0:
                current = time

            await self._seek_stream(current - time)
        else:
            await self._bot.say('Invalid parameter.')

    @commands.command(name='ls', no_pm=True)
    async def list_current_dir(self):
        output_str = ('```diff\n'
                      '=== Contents of {path} ===\n'
                      '```{dirs}{files}')

        dirs, files = self.get_sorted_files_and_dirs()

        dir_str = '\n'.join([format_dir_entry(i + 1, len(dirs), dir) for i, dir in enumerate(dirs)])
        if len(dir_str) > 0:
            dir_str = '```c\n' + dir_str + '```'

        files = self._file_explorer.get_files_in_current_dir(extensions=['.mkv', '.mp4', '.avi'])
        files.sort(key=lambda x: x.name)

        file_str = '\n'.join([format_file_entry(i + 1, len(files), entry) for i, entry in enumerate(files)])
        if len(file_str) > 0:
            file_str = '```c\n' + file_str + '```'

        await self._bot.say(output_str.format(
            path=self._file_explorer.get_current_path(),
            dirs=dir_str,
            files=file_str
        ))

        self._last_ls_cache = (dirs, files)

    def get_sorted_files_and_dirs(self):
        dirs = self._file_explorer.get_dirs_in_current_dir()
        dirs.sort(key=lambda x: x.name)

        files = self._file_explorer.get_files_in_current_dir(extensions=['.mkv', '.mp4', '.avi'])
        files.sort(key=lambda x: x.name)

        self._last_ls_cache = (dirs, files)
        return self._last_ls_cache

    async def _change_directory(self, path: str):
        if path[0] == '/':
            path = self._file_explorer.build_absolute_path(path[1:])
            res = self._file_explorer.change_directory(path, relative=False)
        else:
            res = self._file_explorer.change_directory(path)

        self._last_ls_cache = (None, None)

        if res:
            send_str = 'Changed directory to `{}`'.format(escape_code_block(self._file_explorer.get_current_path()))
        else:
            send_str = 'Failed to change directory.'

        await self._bot.say(send_str)

    @commands.command(name='cd', no_pm=True)
    async def change_directory(self, path: str):
        await self._change_directory(path)

    @commands.command(name='ezcd', no_pm=True)
    async def change_directory_ez(self, num: int):
        dirs, _ = self._last_ls_cache

        if dirs is None:
            dirs, _ = self.get_sorted_files_and_dirs()

        if num < 1 or num > len(dirs):
            await self._bot.say('Invalid option.')
            return

        await self._change_directory(dirs[num - 1].name)
