import os

import discord
from discord.ext import commands

from utils import escape_msg, ask_for_int, parse_timestamp, escape_code_block, format_file_entry, format_dir_entry
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

    async def set_bot_presence(self, path):
        bot_game = None

        if path:
            filename = os.path.basename(path)
            filename_no_ext = os.path.splitext(filename)[0]
            bot_game = discord.Game(name=filename_no_ext, url=self._stream_url, type=1)

        await self._bot.change_presence(game=bot_game, status=None, afk=False)

    async def on_ready(self):
        print('Logged in as {}'.format(self._bot.user.name))
        print('--------------')

    async def _start_stream(self, ctx, relative_path: str):
        absolute_path = self._file_explorer.get_complete_path(relative_path)

        audio_tracks, subtitle_tracks = self._media_player.get_human_readable_track_info(absolute_path)
        audio_track = 1
        subtitle_track = 1 if len(subtitle_tracks) > 0 else None

        # Ask user to select audio track if multiple present
        if len(audio_tracks) > 1:
            ask_str = 'Please select an audio track:\n' + '\n'.join(audio_tracks)
            audio_track = await ask_for_int(self._bot, escape_msg(ask_str), ctx.message.author, lower_bound=1,
                                            upper_bound=len(audio_tracks) + 1, default=1)

        # Ask user to select subtitle track if multiple present
        if len(subtitle_tracks) > 1:
            ask_str = 'Please select a subtitle track:\n' + '\n'.join(subtitle_tracks)
            subtitle_track = await ask_for_int(self._bot, escape_msg(ask_str), ctx.message.author, lower_bound=1,
                                               upper_bound=len(subtitle_tracks) + 1, default=1)

        await self.set_bot_presence(absolute_path)
        await self._bot.say('Stream started.')

        await self._media_player.play_video(absolute_path, audio_track, subtitle_track, 0.0)

        await self.set_bot_presence(None)


    @commands.command(name='stream', pass_context=True, no_pm=True)
    async def start_stream(self, ctx, relative_path: str):
        if not self._file_explorer.file_exists(relative_path):
            await self._bot.say('File does not exist.')
            return
        await self._start_stream(ctx, relative_path)

    @commands.command(name='ezstream', pass_context=True, no_pm=True)
    async def start_stream(self, ctx, num: int):
        _, files = self._last_ls_cache

        if files is None:
            _, files = self.get_sorted_files_and_dirs()

        if num < 1 or num > len(files):
            await self._bot.say('Invalid option.')
            return

        relative_path = files[num-1].name

        if not self._file_explorer.file_exists(relative_path):
            await self._bot.say('File does not exist.')
            return

        await self._start_stream(ctx, relative_path)

    @commands.command(name='streamstop', no_pm=True)
    async def stop_stream(self):
        if not self._media_player.is_video_playing():
            await self._bot.say('Stream not currently playing.')
            return

        _, current_time, _ = await self._media_player.stop_video()
        await self.set_bot_presence(None)
        if current_time:
            await self._bot.say('Stream stopped at {}.'.format(self._media_player.convert_secs_to_str(current_time)))
        else:
            await self._bot.say('Stream stopped.')

    async def _seek_stream(self, time):
        if not self._media_player.is_video_playing():
            await self._bot.say('Stream not currently playing.')
            return

        await self._bot.say('Restarting stream at {}.'.format(self._media_player.convert_secs_to_str(time)))
        video, audio, sub = self._media_player.get_video_info()
        await self._media_player.stop_video()
        await self._media_player.play_video(video, audio, sub, time)

    @commands.command(name='streamseek', no_pm=True)
    async def seek_stream(self, timestamp: str):
        time = parse_timestamp(timestamp)
        if time:
            await self._seek_stream(time)
        else:
            await self._bot.say('Invalid parameter.')

    @commands.command(name='streamff', no_pm=True)
    async def ff_stream(self, length: str):
        time = parse_timestamp(length)
        if time:
            current, _ = self._media_player.get_video_time()
            await self._seek_stream(current + time)
        else:
            await self._bot.say('Invalid parameter.')

    @commands.command(name='streamrew', no_pm=True)
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

        dir_str = '\n'.join([format_dir_entry(i+1, len(dirs), dir) for i, dir in enumerate(dirs)])
        if len(dir_str) > 0:
            dir_str = '```c\n' + dir_str + '```'

        files = self._file_explorer.get_files_in_current_dir(extensions=['.mkv', '.mp4', '.avi'])
        files.sort(key=lambda x: x.name)

        file_str = '\n'.join([format_file_entry(i+1, len(files), entry) for i, entry in enumerate(files)])
        if len(file_str) > 0:
            file_str = '```c\n' + file_str + '```'

        await self._bot.say(output_str.format(
            path = self._file_explorer.get_current_path(),
            dirs = dir_str,
            files = file_str
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
            send_str = 'Changed directory to {}'.format(self._file_explorer.get_current_path())
        else:
            send_str = 'Failed to change directory.'

        await self._bot.say(escape_msg(send_str))

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

        await self._change_directory(dirs[num-1].name)