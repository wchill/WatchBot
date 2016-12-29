import os
import re

import discord

from utils import escape_msg, ask_for_int, parse_timestamp
import media_player
import file_explorer


class CytubeBot(discord.Client):
    def __init__(self, stream_url, rtmp_endpoint, media_directory, channel_whitelist):
        super().__init__()

        self._stream_url = stream_url
        self._rtmp_endpoint = rtmp_endpoint
        self._channel_whitelist = channel_whitelist

        self._file_explorer = file_explorer.FileExplorer(media_directory)
        self._media_player = media_player.DiscordMediaPlayer(self._rtmp_endpoint)

        self._commands = {
            'stream': self.start_stream,
            'streamstop': self.stop_stream,
            'streamff': self.ff_stream,
            'streamrew': self.rew_stream,
            'streamseek': self.seek_stream,
            'listdirs': self.list_dirs,
            'listfiles': self.list_files,
            'cd': self.change_directory
        }

    async def set_bot_presence(self, path):
        bot_game = None

        if path:
            filename = os.path.basename(path)
            filename_no_ext = os.path.splitext(filename)[0]
            bot_game = discord.Game(name=filename_no_ext, url=self._stream_url, type=1)

        await self.change_presence(game=bot_game, status=None, afk=False)

    async def on_ready(self):
        print('Logged in as {} ({})'.format(self.user.name, self.user.id))
        print('--------------')

    async def on_message(self, message):
        if not message.channel.is_private and message.channel.name in self._channel_whitelist and message.content.startswith('!'):
            command = message.content.split(' ')[0][1:]
            if command in self._commands:
                await self._commands[command](message)

    async def start_stream(self, message):
        relative_path = message.content.partition(' ')[2]

        if not self._file_explorer.file_exists(relative_path):
            await self.send_message(message.channel, 'File does not exist.')
            return

        absolute_path = self._file_explorer.get_complete_path(relative_path)

        audio_tracks, subtitle_tracks = self._media_player.get_human_readable_track_info(absolute_path)
        audio_track = 1
        subtitle_track = 1 if len(subtitle_tracks) > 0 else None

        # Ask user to select audio track if multiple present
        if len(audio_tracks) > 1:
            ask_str = 'Please select an audio track:\n' + '\n'.join(audio_tracks)
            audio_track = await ask_for_int(self, escape_msg(ask_str), message.channel, message.author, lower_bound=1,
                                            upper_bound=len(audio_tracks) + 1, default=1)

        # Ask user to select subtitle track if multiple present
        if len(subtitle_tracks) > 1:
            ask_str = 'Please select a subtitle track:\n' + '\n'.join(subtitle_tracks)
            subtitle_track = await ask_for_int(self, escape_msg(ask_str), message.channel, message.author, lower_bound=1,
                                               upper_bound=len(subtitle_tracks) + 1, default=1)

        await self.set_bot_presence(absolute_path)
        await self.send_message(message.channel, 'Stream started.')

        await self._media_player.play_video(absolute_path, audio_track, subtitle_track, 0.0)

        await self.set_bot_presence(None)

    async def stop_stream(self, message):
        if not self._media_player.is_video_playing():
            await self.send_message(message.channel, 'Stream not currently playing.')
            return

        _, current_time, _ = await self._media_player.stop_video()
        await self.set_bot_presence(None)
        if current_time:
            await self.send_message(message.channel, 'Stream stopped at {}.'.format(self._media_player.convert_secs_to_str(current_time)))
        else:
            await self.send_message(message.channel, 'Stream stopped.')

    async def _seek_stream(self, channel, time):
        if not self._media_player.is_video_playing():
            await self.send_message(channel, 'Stream not currently playing.')
            return

        await self.send_message(channel, 'Restarting stream at {}.'.format(self._media_player.convert_secs_to_str(time)))
        video, audio, sub = self._media_player.get_video_info()
        await self._media_player.stop_video()
        await self._media_player.play_video(video, audio, sub, time)

    async def seek_stream(self, message):
        time = parse_timestamp(message.content.partition(' ')[2])
        if time:
            await self._seek_stream(message.channel, time)
        else:
            await self.send_message(message.channel, 'Invalid parameter.')

    async def ff_stream(self, message):
        time = parse_timestamp(message.content.partition(' ')[2])
        if time:
            current, _ = self._media_player.get_video_time()
            await self._seek_stream(message.channel, current + time)
        else:
            await self.send_message(message.channel, 'Invalid parameter.')

    async def rew_stream(self, message):
        time = parse_timestamp(message.content.partition(' ')[2])
        if time:
            current, _ = self._media_player.get_video_time()

            if current + time < 0:
                current = time

            await self._seek_stream(message.channel, current - time)
        else:
            await self.send_message(message.channel, 'Invalid parameter.')

    async def list_dirs(self, message):
        dir_names = self._file_explorer.list_nonhidden_dirnames_in_current_dir()
        dir_names.sort()
        dir_str = 'List of directories in {dirname}:\n{dirs}'.format(
            dirname=self._file_explorer.get_current_path(),
            dirs='\n'.join(dir_names)
        )
        await self.send_message(message.channel, escape_msg(dir_str))

    async def list_files(self, message):
        file_names = self._file_explorer.list_nonhidden_filenames_in_current_dir()
        filtered_file_names = self._file_explorer.filter_filenames_by_ext(file_names, ['.mkv', '.mp4', '.avi'])
        filtered_file_names.sort()
        dir_str = 'List of files in {dirname}:\n{files}'.format(
            dirname=self._file_explorer.get_current_path(),
            files='\n'.join(filtered_file_names)
        )
        await self.send_message(message.channel, escape_msg(dir_str))

    async def change_directory(self, message):
        path = message.content.partition(' ')[2]
        if path[0] == '/':
            path = self._file_explorer.build_absolute_path(path[1:])
            res = self._file_explorer.change_directory(path, relative=False)
        else:
            res = self._file_explorer.change_directory(path)

        if res:
            send_str = 'Changed directory to {}'.format(self._file_explorer.get_current_path())
        else:
            send_str = 'Failed to change directory.'
        await self.send_message(message.channel, escape_msg(send_str))
