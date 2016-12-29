import os

import discord

from utils import is_safe_path, ask_for_int
import media_player

class CytubeBot(discord.Client):

    def __init__(self, stream_url, rtmp_endpoint, media_directory, channel_whitelist, loop=None, **options):
        super().__init__()

        self._stream_url = stream_url
        self._rtmp_endpoint = rtmp_endpoint
        self._media_directory = media_directory
        self._channel_whitelist = channel_whitelist

        self._media_player = media_player.DiscordMediaPlayer(self._rtmp_endpoint)


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
        if not message.channel.is_private and message.channel.name in self._channel_whitelist:
            if message.content.startswith('!stream '):
                params = message.content.partition(' ')[2]
                file_path = os.path.join(self._media_directory, params)

                # prevent path traversal
                if not is_safe_path(self._media_directory, file_path, follow_symlinks=False):
                    await self.send_message(message.channel, 'Nice try')
                    return

                if not os.path.exists(file_path):
                    await self.send_message(message.channel, 'File does not exist.')
                    return

                audio_tracks, subtitle_tracks = self._media_player.get_human_readable_track_info(file_path)
                audio_track = 1
                subtitle_track = 1 if len(subtitle_tracks) > 0 else None

                # Ask user to select audio track if multiple present
                if len(audio_tracks) > 1:
                    ask_str = 'Please select an audio track:\n' + '\n'.join(audio_tracks)
                    audio_track = await ask_for_int(self, ask_str, message.channel, message.author, lower_bound=1, upper_bound=len(audio_tracks)+1, default=1)

                # Ask user to select subtitle track if multiple present
                if len(subtitle_tracks) > 1:
                    ask_str = 'Please select a subtitle track:\n' + '\n'.join(subtitle_tracks)
                    subtitle_track = await ask_for_int(self, ask_str, message.channel, message.author, lower_bound=1, upper_bound=len(subtitle_tracks)+1, default=1)

                await self.set_bot_presence(file_path)
                await self.send_message(message.channel, 'Stream started.')

                exitcode = await self._media_player.play_video(file_path, audio_track, subtitle_track, 0.0)

                if exitcode == 0:
                    await self.set_bot_presence(None)
                    await self.send_message(message.channel, 'Stream finished.')
            elif message.content == '!stopstream':
                if not self._media_player.is_video_playing():
                    await self.send_message(message.channel, 'Stream not currently playing.')
                    return

                await self._media_player.stop_video()
                await self.set_bot_presence(None)
                await self.send_message(message.channel, 'Stream stopped.')